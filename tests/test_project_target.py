from pathlib import Path

from hackathon_competitor.models import MissionState, ProjectMode, ProjectTarget
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import build_project_for_mission, mission_status
from hackathon_competitor.storage import Database


class Implementer:
    def implement(self, project_root: Path, specification: str, failure=None) -> str:
        (project_root / "main.py").write_text("print('competition project')\n", encoding="utf-8")
        (project_root / "test_main.py").write_text(
            "def test_main():\n    import main\n",
            encoding="utf-8",
        )
        return "implemented"


def test_project_target_is_persisted_and_attached(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = app.create_mission(
        title="competition",
        objective="build",
        source_inputs=["brief"],
        workspace_path=str(tmp_path / "workspace"),
    )
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(tmp_path / "project"),
    )
    app.attach_project_target(target)
    loaded = database.get_mission(mission.id)
    assert loaded.project_target_id == target.id
    assert database.get_project_target_for_mission(mission.id).local_path == str(tmp_path / "project")


def test_real_build_path_records_project_status(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = app.create_mission(
        title="competition",
        objective="build",
        source_inputs=["brief"],
        workspace_path=str(tmp_path / "workspace"),
    )
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.NEW_REPO,
        local_path=str(tmp_path / "project"),
        test_commands=[["python", "-m", "pytest", "-q"]],
    )
    app.attach_project_target(target)
    mission = database.get_mission(mission.id)
    mission = app.transition_state(mission, MissionState.INTAKE)
    # This helper is intended for a planned mission; seed the state directly through legal steps.
    for state in (
        MissionState.DISCOVERY,
        MissionState.RULES_LOCK,
        MissionState.LANDSCAPE_ANALYSIS,
        MissionState.IDEATION,
        MissionState.STRATEGY_SELECTION,
        MissionState.PLANNING,
    ):
        mission = app.transition_state(mission, state)
    change_set = build_project_for_mission(app, mission.id, Implementer(), specification="build it")
    assert change_set.status == "validated"
    status = mission_status(app, database.get_mission(mission.id))
    assert status["project_target"] == str(target.id)
    assert status["build_runs"] == 2
