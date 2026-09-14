import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hackathon_competitor.models import (
    Decision,
    HackathonSpec,
    Idea,
    MissionState,
    ProjectMode,
    ProjectTarget,
    Requirement,
    TaskStatus,
)
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import (
    build_project_for_mission,
    prepare_project_submission,
)
from hackathon_competitor.storage import Database


class Implementer:
    def implement(self, project_root: Path, specification: str, failure=None) -> str:
        (project_root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (project_root / "main.py").write_text("print('competition project')\n", encoding="utf-8")
        (project_root / "test_main.py").write_text(
            "def test_main():\n    import main\n", encoding="utf-8"
        )
        return "implemented"


def _planned_app(tmp_path, *, include_run: bool = True):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = app.create_mission(
        title="competition",
        objective="build and submit",
        source_inputs=["brief"],
        workspace_path=str(tmp_path / "workspace"),
    )
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.NEW_REPO,
        local_path=str(tmp_path / "project"),
        repository_url="owner/project",
        language="Python",
        test_commands=[[sys.executable, "-c", "print('test-ok')"]],
        run_commands=([[sys.executable, "-c", "print('demo-ok')"]] if include_run else []),
    )
    app.attach_project_target(target)
    mission = database.get_mission(mission.id)
    for state in (
        MissionState.INTAKE,
        MissionState.DISCOVERY,
        MissionState.RULES_LOCK,
        MissionState.LANDSCAPE_ANALYSIS,
        MissionState.IDEATION,
        MissionState.STRATEGY_SELECTION,
        MissionState.PLANNING,
    ):
        mission = app.transition_state(mission, state)
    spec = HackathonSpec(
        mission_id=mission.id,
        name="Fixture competition",
        deadline_at=datetime.now(UTC) + timedelta(days=1),
        required_technologies=["Python"],
        submission_requirements=[Requirement(id="repo", text="Provide a repository")],
        eligibility_requirements=[Requirement(id="license", text="Use MIT license")],
    )
    database.save_spec(spec)
    idea = Idea(
        title="Useful project",
        summary="A useful competition project.",
        batch="first",
        dimensions={"feasibility": 1.0},
    )
    database.save_idea(mission.id, idea)
    database.save_decision(
        Decision(
            mission_id=mission.id,
            question="Which project?",
            options=[{"id": str(idea.id), "title": idea.title}],
            selected_option=str(idea.id),
            rationale="Evidence-backed choice.",
            confidence=0.9,
            depth_level=3,
            reversible=True,
        )
    )
    return app, mission, target


def test_project_submission_pack_is_bound_to_validated_target(tmp_path):
    app, mission, target = _planned_app(tmp_path)
    change_set = build_project_for_mission(
        app, mission.id, Implementer(), specification="Build the useful project."
    )

    prepared = prepare_project_submission(app, mission.id)

    assert change_set.status == "validated"
    assert prepared.state == MissionState.READY_FOR_SUBMISSION
    artifacts = app.database.list_artifacts(mission.id)
    readme = next(item for item in artifacts if item.kind == "project_submission_readme")
    content = Path(readme.path).read_text(encoding="utf-8")
    assert target.repository_url in content
    assert change_set.commit_sha in content
    assert any(
        event["event_type"] == "PROJECT_SUBMISSION_READY"
        for event in app.database.events(mission.id)
    )


def test_project_submission_blocks_without_reproduced_demo(tmp_path):
    app, mission, _ = _planned_app(tmp_path, include_run=False)
    build_project_for_mission(
        app, mission.id, Implementer(), specification="Build the useful project."
    )

    prepared = prepare_project_submission(app, mission.id)

    assert prepared.state == MissionState.BLOCKED
    task = next(
        item
        for item in app.database.list_tasks(mission.id)
        if item.type == "project_submission_pack"
    )
    assert task.status == TaskStatus.FAILED_PERMANENT
    blocked = [
        event
        for event in app.database.events(mission.id)
        if event["event_type"] == "PROJECT_SUBMISSION_BLOCKED"
    ]
    assert "primary demo path is untested" in blocked[-1]["payload"]["findings"]
