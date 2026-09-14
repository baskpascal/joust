from datetime import UTC, datetime, timedelta

import pytest

from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.competition_actions import CompetitionActionDispatcher
from hackathon_competitor.competition_runner import CompetitionIterationRunner
from hackathon_competitor.models import (
    ActionCandidate,
    ActionResult,
    AdaptationPlan,
    AssessmentPlan,
    CompetitionActionType,
    Measurement,
    Mission,
    MissionStatus,
)
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import Database


class Planner:
    def assess(self, mission, observation):
        return AssessmentPlan(
            bottleneck="Missing competitive implementation",
            candidates=[
                ActionCandidate(
                    name="Implement entry",
                    description="Build the competitive slice",
                    action_type=CompetitionActionType.CUSTOM,
                    expected_outcome_improvement=1.0,
                    time_cost=1.0,
                    technical_risk=0.1,
                    regression_probability=0.1,
                )
            ],
        )

    def adapt(self, mission, cycle, execution, measurement):
        return AdaptationPlan(
            next_bottleneck="Observe adoption",
            next_best_action="Measure usage",
            mission_score=measurement.after,
            confidence=0.8,
        )


class Executor:
    def execute(self, mission, target, action):
        return ActionResult(summary="Entry implemented")


class Measurer:
    def measure(self, mission, observation, execution):
        return Measurement(before=0.0, after=0.6, metric="readiness")


class FailingPlanner(Planner):
    def assess(self, mission, observation):
        raise TimeoutError("planner timed out")


def _runner(database):
    return CompetitionIterationRunner(
        database,
        CompetitionObserver(database),
        Planner(),
        CompetitionActionDispatcher(
            database,
            {CompetitionActionType.CUSTOM: Executor()},
        ),
        Measurer(),
    )


def test_iteration_runner_completes_and_starts_next_cycle(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Persistent", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)

    next_cycle = _runner(database).run(mission.id)

    assert next_cycle is not None
    assert next_cycle.sequence == 2
    assert next_cycle.stage.value == "OBSERVE"
    completed = database.list_competition_cycles(mission.id)[0]
    assert completed.completed_at is not None
    assert completed.verified is True
    assert completed.measured_delta == 0.6
    loaded = database.get_mission(mission.id)
    assert loaded.status == MissionStatus.ACTIVE
    assert loaded.mission_score == 0.6
    assert any(
        event["event_type"] == "COMPETITION_MEASUREMENT_RECORDED"
        for event in database.events(mission.id)
    )


def test_iteration_runner_resumes_after_execution_without_duplicate(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Resume", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    runner = _runner(database)
    cycle = CompeteLoop(database).create_cycle(mission.id)
    observation = runner.observer.capture(cycle.id)
    plan = runner.planner.assess(mission, observation)
    runner.loop.assess(cycle.id, bottleneck=plan.bottleneck, candidates=plan.candidates)
    runner.loop.strategize(cycle.id)
    runner.dispatcher.execute_selected(cycle.id)

    next_cycle = runner.run(mission.id)

    assert next_cycle is not None
    assert len(database.list_action_executions(mission.id)) == 1
    assert database.list_competition_cycles(mission.id)[0].completed_at is not None


def test_iteration_runner_expires_mission_from_observed_deadline(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(
        title="Expired",
        objective="compete",
        workspace_path=str(tmp_path),
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    database.save_mission(mission)

    cycle = _runner(database).run(mission.id)

    assert cycle is not None
    assert cycle.completed_at is not None
    assert database.get_mission(mission.id).status == MissionStatus.EXPIRED
    assert database.list_action_executions(mission.id) == []


def test_iteration_runner_leaves_future_deadline_active(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(
        title="Active",
        objective="compete",
        workspace_path=str(tmp_path),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )
    database.save_mission(mission)

    assert _runner(database).run(mission.id) is not None
    assert database.get_mission(mission.id).status == MissionStatus.ACTIVE


def test_iteration_runner_records_planner_failure_and_remains_resumable(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Resume", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    runner = _runner(database)
    runner.planner = FailingPlanner()

    with pytest.raises(TimeoutError, match="planner timed out"):
        runner.run(mission.id)

    cycle = database.list_competition_cycles(mission.id)[0]
    assert cycle.stage.value == "ASSESS"
    failures = [
        event
        for event in database.events(mission.id)
        if event["event_type"] == "COMPETITION_ITERATION_FAILED"
    ]
    assert failures[-1]["payload"]["stage"] == "ASSESS"
    assert failures[-1]["payload"]["error_type"] == "TimeoutError"
