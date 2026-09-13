import sys
from pathlib import Path

import pytest

from hackathon_competitor.build_loop import BuildLoopError, CommandImplementer, RealBuildLoop
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
    runs = database.list_build_runs(mission.id)
    assert len(runs) == 3
    assert {run.phase for run in runs} == {"test", "reproduce_test"}
    assert all(run.passed for run in runs[-2:])
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


def test_real_build_loop_requires_project_validation_commands(tmp_path):
    database, mission = _mission(tmp_path)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.NEW_REPO,
        local_path=str(tmp_path / "project"),
    )
    database.save_project_target(target)
    with pytest.raises(BuildLoopError, match="declare"):
        RealBuildLoop(database, tmp_path / "artifacts").run(target, "spec", FakeImplementer())


def test_command_implementer_includes_validation_failure_in_repair_prompt(tmp_path):
    implementer = CommandImplementer(
        [
            sys.executable,
            "-c",
            "import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text())",
        ]
    )
    output = implementer.repair(tmp_path, "Build the app.", "pytest failed")
    assert "pytest failed" in output
    assert "Repair the implementation" in output


class FakeBootstrap:
    def __init__(self):
        self.calls = []

    def clone(self, repository: str, destination: str) -> str:
        self.calls.append((repository, destination))
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        return "cloned"


def test_existing_github_target_bootstraps_missing_checkout(tmp_path):
    database, mission = _mission(tmp_path)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(tmp_path / "remote-project"),
        repository_url="owner/project",
        test_commands=[["python", "-c", "print('ok')"]],
    )
    database.save_project_target(target)
    bootstrap = FakeBootstrap()
    # The implementer creates the Git repository after the read-only clone step.
    class InitializingImplementer(FakeImplementer):
        def implement(self, project_root, specification, failure=None):
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=project_root, check=True)
            return super().implement(project_root, specification, failure)

    # A clone adapter is expected to return a real checkout; this fake models
    # the boundary and lets the test focus on the call contract.
    change_set = RealBuildLoop(database, tmp_path / "artifacts", github=bootstrap).run(
        target, "spec", InitializingImplementer(), max_repairs=0
    )
    assert change_set.status == "validated"
    assert bootstrap.calls == [("owner/project", str(Path(target.local_path).resolve()))]
