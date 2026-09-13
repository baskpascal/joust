import sys
from pathlib import Path

from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.competition_actions import (
    CompetitionActionDispatcher,
    RealBuildActionExecutor,
)
from hackathon_competitor.models import (
    ActionCandidate,
    ActionExecution,
    ActionExecutionStatus,
    CompetitionActionType,
    Mission,
    ProjectMode,
    ProjectTarget,
)
from hackathon_competitor.storage import Database


class TinyImplementer:
    def implement(self, project_root: Path, specification: str, failure=None):
        (project_root / "entry.py").write_text("print('competitive')\n", encoding="utf-8")
        return "implemented"


class FailingExecutor:
    def execute(self, mission, target, action):
        raise RuntimeError("executor unavailable")


def _selected_cycle(database, mission, action):
    loop = CompeteLoop(database)
    cycle = loop.create_cycle(mission.id)
    loop.observe(cycle.id, "Project needs implementation")
    loop.assess(cycle.id, bottleneck="No working entry", candidates=[action])
    return loop.strategize(cycle.id)


def test_selected_build_action_runs_real_build_loop_and_records_evidence(tmp_path):
    database = Database(tmp_path / "state.db")
    assert database.migrate() == 11
    mission = Mission(
        title="Build competition entry",
        objective="win",
        workspace_path=str(tmp_path / "entry"),
    )
    database.save_mission(mission)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.NEW_REPO,
        local_path=mission.workspace_path,
        test_commands=[[sys.executable, "-c", "import entry"]],
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)
    action = ActionCandidate(
        name="Build the entry",
        description="Create the first working slice",
        action_type=CompetitionActionType.BUILD_PROJECT,
        parameters={"specification": "Create a runnable competition entry", "max_repairs": 0},
        expected_outcome_improvement=1.0,
        time_cost=1.0,
        technical_risk=0.1,
        regression_probability=0.1,
    )
    cycle = _selected_cycle(database, mission, action)
    dispatcher = CompetitionActionDispatcher(
        database,
        {
            CompetitionActionType.BUILD_PROJECT: RealBuildActionExecutor(
                database,
                tmp_path / "artifacts",
                TinyImplementer(),
            )
        },
    )

    execution = dispatcher.execute_selected(cycle.id)

    assert execution.status == ActionExecutionStatus.SUCCEEDED
    assert execution.result is not None
    assert execution.result.change_set_id is not None
    assert execution.result.evidence_ids
    assert database.get_competition_cycle(cycle.id).stage.value == "VERIFY"
    assert database.list_change_sets(mission.id)[-1].status == "validated"
    assert database.export_mission(mission.id)["action_executions"][0]["status"] == "SUCCEEDED"
    assert dispatcher.execute_selected(cycle.id).id == execution.id
    assert len(database.list_action_executions(mission.id)) == 1


def test_failed_action_is_durable_and_advances_to_verification(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Failure", objective="win", workspace_path=str(tmp_path))
    database.save_mission(mission)
    action = ActionCandidate(
        name="Research",
        description="Inspect the competition",
        action_type=CompetitionActionType.RESEARCH,
        expected_outcome_improvement=0.5,
        time_cost=1.0,
        technical_risk=0.1,
        regression_probability=0.1,
    )
    cycle = _selected_cycle(database, mission, action)

    execution = CompetitionActionDispatcher(
        database,
        {CompetitionActionType.RESEARCH: FailingExecutor()},
    ).execute_selected(cycle.id)

    assert execution.status == ActionExecutionStatus.FAILED
    assert execution.error == "executor unavailable"
    stored_cycle = database.get_competition_cycle(cycle.id)
    assert stored_cycle.stage.value == "VERIFY"
    assert stored_cycle.execution_succeeded is False


def test_running_action_from_interrupted_process_is_closed_durably(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Interrupted", objective="win", workspace_path=str(tmp_path))
    database.save_mission(mission)
    action = ActionCandidate(
        name="Build",
        description="Verify project",
        action_type=CompetitionActionType.BUILD_PROJECT,
        parameters={"specification": "verify"},
        expected_outcome_improvement=0.5,
        time_cost=1.0,
        technical_risk=0.1,
        regression_probability=0.1,
    )
    cycle = _selected_cycle(database, mission, action)
    running = ActionExecution(
        mission_id=mission.id,
        cycle_id=cycle.id,
        action=action,
    )
    database.save_action_execution(running)

    execution = CompetitionActionDispatcher(database, {}).execute_selected(cycle.id)

    assert execution.status == ActionExecutionStatus.FAILED
    assert "ended before a durable result" in execution.error
    assert database.get_competition_cycle(cycle.id).stage.value == "VERIFY"
    assert any(
        event["event_type"] == "COMPETITION_ACTION_INTERRUPTED"
        for event in database.events(mission.id)
    )
