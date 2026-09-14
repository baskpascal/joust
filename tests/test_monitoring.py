from datetime import UTC, datetime, timedelta

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
    MonitorOutcome,
)
from hackathon_competitor.monitoring import BackoffPolicy, MonitoredCompetitionRunner
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import Database


class Planner:
    def assess(self, mission, observation):
        return AssessmentPlan(
            bottleneck="usage",
            candidates=[
                ActionCandidate(
                    name="observe",
                    description="observe",
                    action_type=CompetitionActionType.CUSTOM,
                    expected_outcome_improvement=1,
                    time_cost=1,
                    technical_risk=0,
                    regression_probability=0,
                )
            ],
        )

    def adapt(self, mission, cycle, execution, measurement):
        return AdaptationPlan(mission_score=measurement.after)


class Executor:
    def execute(self, mission, target, action):
        return ActionResult(summary="observed")


class Measurer:
    def measure(self, mission, observation, execution):
        return Measurement(before=0, after=1, metric="readiness")


class BrokenObserver(CompetitionObserver):
    def collect(self, cycle_id, *, now=None, score_signals=None):
        raise OSError("source unavailable")


def make_runner(database, observer=None):
    observer = observer or CompetitionObserver(database)
    return CompetitionIterationRunner(
        database,
        observer,
        Planner(),
        CompetitionActionDispatcher(
            database,
            {CompetitionActionType.CUSTOM: Executor()},
        ),
        Measurer(),
    )


def test_monitor_skips_unchanged_observation_without_advancing_cycle(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    monitor = MonitoredCompetitionRunner(database, make_runner(database), random_unit=lambda: 0.5)
    now = datetime(2026, 9, 13, tzinfo=UTC)

    first = monitor.run(mission.id, holder="worker-1", now=now)
    second = monitor.run(mission.id, holder="worker-1", now=now + timedelta(minutes=1))

    assert first.outcome == MonitorOutcome.CHANGED
    assert second.outcome == MonitorOutcome.UNCHANGED
    active = database.list_competition_cycles(mission.id)[-1]
    assert active.stage.value == "OBSERVE"
    assert active.completed_at is None
    assert len(database.list_action_executions(mission.id)) == 1


def test_monitor_lease_allows_only_one_live_holder(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    now = datetime(2026, 9, 13, tzinfo=UTC)
    key = f"mission:{mission.id}:competition_state"

    assert database.acquire_monitor_lease(
        lease_key=key,
        mission_id=mission.id,
        holder="worker-1",
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert not database.acquire_monitor_lease(
        lease_key=key,
        mission_id=mission.id,
        holder="worker-2",
        acquired_at=now + timedelta(minutes=1),
        expires_at=now + timedelta(minutes=6),
    )
    assert database.acquire_monitor_lease(
        lease_key=key,
        mission_id=mission.id,
        holder="worker-2",
        acquired_at=now + timedelta(minutes=6),
        expires_at=now + timedelta(minutes=11),
    )


def test_backoff_policy_uses_capped_sequence_and_jitter():
    policy = BackoffPolicy()

    assert policy.delay(1, 0.5) == timedelta(minutes=1)
    assert policy.delay(2, 0.5) == timedelta(minutes=2)
    assert policy.delay(3, 0.5) == timedelta(minutes=5)
    assert policy.delay(4, 0.5) == timedelta(minutes=15)
    assert policy.delay(5, 0.5) == timedelta(hours=1)
    assert policy.delay(99, 0.5) == timedelta(hours=1)
    assert policy.delay(1, 0.0) == timedelta(seconds=48)
    assert policy.delay(1, 1.0) == timedelta(seconds=72)


def test_observation_failure_sets_backoff_without_erasing_last_success(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    previous = database.get_monitor_backoff(mission.id, "competition_state")
    previous.last_successful_observation_id = (
        CompetitionObserver(database).capture(CompeteLoop(database).create_cycle(mission.id).id).id
    )
    database.save_monitor_backoff(previous)
    # Complete that synthetic cycle so the failing run starts from OBSERVE.
    cycle = database.list_competition_cycles(mission.id)[-1]
    cycle.completed_at = datetime(2026, 9, 13, tzinfo=UTC)
    database.save_competition_cycle(cycle)
    broken = BrokenObserver(database)
    monitor = MonitoredCompetitionRunner(
        database,
        make_runner(database, broken),
        backoff=BackoffPolicy(jitter_ratio=0),
        random_unit=lambda: 0.5,
    )
    now = datetime(2026, 9, 13, tzinfo=UTC)

    failed = monitor.run(mission.id, holder="worker-1", now=now)
    blocked = monitor.run(mission.id, holder="worker-1", now=now + timedelta(seconds=30))
    state = database.get_monitor_backoff(mission.id, "competition_state")

    assert failed.outcome == MonitorOutcome.FAILED
    assert failed.next_attempt_at == now + timedelta(minutes=1)
    assert blocked.outcome == MonitorOutcome.BACKING_OFF
    assert state.last_successful_observation_id == previous.last_successful_observation_id
    assert state.consecutive_failures == 1
