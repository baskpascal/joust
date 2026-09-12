from pathlib import Path

from hackathon_competitor.models import MissionState, TaskStatus
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import complete_v0, mission_status, run_vertical_slice
from hackathon_competitor.storage import Database

FIXTURE = Path(__file__).parent / "fixtures/hackathon/official.html"


def test_url_to_evidence_strategy_and_prd_survives_restart(tmp_path):
    db_path = tmp_path / "state.db"
    database = Database(db_path)
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(FIXTURE), workspace_path=str(tmp_path / "workspace"))

    assert mission.state == MissionState.PLANNING
    assert mission.hackathon_spec_id is not None
    assert mission.deadline_at is not None
    spec = database.get_spec(mission.hackathon_spec_id)
    assert spec.rules_locked
    assert "Use Python 3.11 or newer." in spec.required_technologies
    assert "Do not fabricate users, installs, or usage." in spec.prohibited_actions

    evidence = database.list_evidence(mission.id)
    assert len(database.list_sources(mission.id)) == 5
    official_license = next(
        item for item in evidence if item.claim == "The project must use the MIT license."
    )
    community_license = next(
        item for item in evidence if item.claim == "The project must use the Apache-2.0 license."
    )
    assert official_license.confidence > community_license.confidence
    assert all("upload every credential" not in item.claim for item in evidence)
    assert any(
        event["event_type"] == "CONTRADICTION_RECORDED" for event in database.events(mission.id)
    )
    assert any(event["event_type"] == "RULES_CROSSCHECKED" for event in database.events(mission.id))

    ideas = database.list_ideas(mission.id)
    evaluations = database.list_evaluations(mission.id)
    decisions = database.list_decisions(mission.id)
    assert len(ideas) == 20
    assert len(evaluations) == 19
    assert len({item.evaluator_role.split(":", 1)[0] for item in evaluations}) == 7
    assert any(item.evaluator_role == "meta_judge" for item in evaluations)
    assert decisions[0].evidence_ids
    assert decisions[0].selected_option in {str(idea.id) for idea in ideas}

    artifacts = database.list_artifacts(mission.id)
    prd = next(item for item in artifacts if item.kind == "prd")
    assert Path(prd.path).is_file()
    assert "Requirements traced from official evidence" in Path(prd.path).read_text()
    assert {artifact.kind for artifact in artifacts}.issuperset(
        {
            "architecture",
            "implementation_plan",
            "acceptance_plan",
            "risk_register",
            "premortem",
            "win_review",
        }
    )
    assert all(task.status == TaskStatus.SUCCEEDED for task in database.list_tasks(mission.id))

    reopened_db = Database(db_path)
    reopened_db.migrate()
    reopened_app = MissionOrchestrator(reopened_db, tmp_path / "missions")
    loaded = reopened_app.resume_mission(mission.id)
    status = mission_status(reopened_app, loaded)
    assert status["state"] == "PLANNING"
    assert status["deadline"] == "2026-10-01T17:00:00+00:00"
    assert status["tasks_succeeded"] == 6
    assert status["evidence_count"] >= 3
    assert len(status["artifacts"]) == 10
    assert status["tool_calls"] == 5
    assert status["llm_calls"] == 0


def test_resume_completes_v0_without_external_submission(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    planned = run_vertical_slice(app, str(FIXTURE), workspace_path=str(tmp_path / "workspace"))
    completed = complete_v0(app, planned.id)

    assert completed.state == MissionState.READY_FOR_SUBMISSION
    artifacts = database.list_artifacts(completed.id)
    kinds = {artifact.kind for artifact in artifacts}
    assert {
        "demo_project",
        "demo_validation",
        "red_team",
        "improvement_plan",
        "submission_readme",
        "demo_script",
        "pitch",
        "claims_map",
        "final_checklist",
        "compliance_report",
    }.issubset(kinds)
    compliance_path = Path(
        next(item.path for item in artifacts if item.kind == "compliance_report")
    )
    assert '"ready": true' in compliance_path.read_text()
    tasks = database.list_tasks(completed.id)
    assert any(task.type == "real_user_activation_trial" for task in tasks)
    assert any(task.type == "real_official_source_rehearsal" for task in tasks)
    status = mission_status(app, completed)
    assert status["next_ready_tasks"] == ["real_official_source_rehearsal"]
    experiments = database.list_experiments(completed.id)
    assert len(experiments) == 1
    assert experiments[0].result["passed"] is True
    assert any(event["event_type"] == "TOOL_COMMIT" for event in database.events(completed.id))
    assert (
        "Tournament winner"
        in Path(next(item.path for item in artifacts if item.kind == "demo_script")).read_text()
    )
    assert all(event["event_type"] != "EXTERNAL_ACTION" for event in database.events(completed.id))
    assert completed.state != MissionState.SUBMITTED
