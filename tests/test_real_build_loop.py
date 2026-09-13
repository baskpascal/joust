from pathlib import Path

import pytest

from hackathon_competitor.build_loop import BuildLoopError, RealBuildLoop
from hackathon_competitor.models import Mission, ProjectMode, ProjectTarget
from hackathon_competitor.storage import Database


class FakeImplementer:
    def __init__(self):
        self.repaired = False

    def implement(self, project_root: Path, specification: str, failure=None) -> str:
        (project_root / "app.py").write_text(
            "def answer():\n    return 'ready' if __import__('pathlib').Path('fixed.flag').exists() else 'broken'\n",
            encoding="utf-8",
        )
        (project_root / "test_app.py").write_text(
            "from app import answer\n\ndef test_answer():\n    assert answer() == 'ready'\n",
            encoding="utf-8",
        )
        return "implemented"

    def repair(self, project_root: Path, specification: str, failure: str) -> str:
        self.repaired = True
        (project_root / "fixed.flag").write_text("ok", encoding="utf-8")
        return "repaired"


def _mission(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="real build", objective="build", workspace_path=str(tmp_path / "project"))
    database.save_mission(mission)
    return database, mission


def test_real_build_loop_commits_runs_tests_and_repairs(tmp_path):
    database, mission = _mission(tmp_path)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.NEW_REPO,
        local_path=str(tmp_path / "project"),
        test_commands=[["python", "-m", "pytest", "-q"]],
    )
    database.save_project_target(target)
    implementer = FakeImplementer()

    change_set = RealBuildLoop(database, tmp_path / "artifacts").run(
        target, "Build a tiny tested project.", implementer
    )

    assert change_set.status == "validated"
    assert change_set.commit_sha
    assert implementer.repaired
    assert len(database.list_build_runs(mission.id)) == 2
    assert all(run.passed for run in database.list_build_runs(mission.id)[-1:])
    assert any(event["event_type"] == "PROJECT_BUILD_VALIDATED" for event in database.events(mission.id))


def test_real_build_loop_refuses_dirty_workspace(tmp_path):
    database, mission = _mission(tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    (root / "uncommitted.txt").write_text("keep", encoding="utf-8")
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(root),
        test_commands=[["python", "-m", "pytest", "-q"]],
    )
    database.save_project_target(target)
    with pytest.raises(BuildLoopError, match="dirty"):
        RealBuildLoop(database, tmp_path / "artifacts").run(target, "spec", FakeImplementer())
