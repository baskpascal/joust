from uuid import uuid4

import pytest

from hackathon_competitor.compete_loop import CompeteLoop, CompeteLoopError
from hackathon_competitor.models import (
    ActionCandidate,
    CompeteStage,
    Mission,
    MissionStatus,
)
from hackathon_competitor.storage import Database


def _candidate(name: str, improvement: float, time_cost: float) -> ActionCandidate:
    return ActionCandidate(
        name=name,
        description=f"Execute {name}",
        expected_outcome_improvement=improvement,
        time_cost=time_cost,
        technical_risk=0.1,
        regression_probability=0.1,
    )


def _active_loop(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    return database, mission, CompeteLoop(database)


def test_compete_loop_persists_cycle_and_starts_next_observation(tmp_path):
    database, mission, loop = _active_loop(tmp_path)
    observation_evidence = uuid4()
    verification_evidence = uuid4()

    cycle = loop.create_cycle(mission.id)
    loop.observe(cycle.id, "Leaderboard growth stalled", evidence_ids=[observation_evidence])
    loop.assess(
        cycle.id,
        bottleneck="Activation",
        candidates=[
            _candidate("Improve onboarding", 0.8, 1.0),
            _candidate("Add another feature", 0.5, 2.0),
        ],
    )
    selected = loop.strategize(cycle.id)
    assert selected.selected_action is not None
    assert selected.selected_action.name == "Improve onboarding"
    loop.record_execution(cycle.id, result="Onboarding changed", succeeded=True)
    loop.verify(
        cycle.id,
        verified=True,
        finding="Clean-clone test passed",
        evidence_ids=[verification_evidence],
    )
    loop.measure(cycle.id, before=0.4, after=0.7)
    next_cycle = loop.adapt(
        cycle.id,
        next_bottleneck="Retention",
        next_best_action="Measure repeat usage",
        mission_score=0.7,
        confidence=0.8,
    )

    assert next_cycle is not None
    assert next_cycle.sequence == 2
    assert next_cycle.stage == CompeteStage.OBSERVE
    completed = database.get_competition_cycle(cycle.id)
    assert completed.completed_at is not None
    assert completed.measured_delta == pytest.approx(0.3)
    loaded_mission = database.get_mission(mission.id)
    assert loaded_mission.current_bottleneck == "Retention"
    assert loaded_mission.current_best_action == "Measure repeat usage"
    assert len(database.export_mission(mission.id)["competition_cycles"]) == 2


def test_terminal_mission_does_not_start_another_cycle(tmp_path):
    database, mission, loop = _active_loop(tmp_path)
    evidence_id = uuid4()
    cycle = loop.create_cycle(mission.id)
    loop.observe(cycle.id, "Deadline reached", evidence_ids=[evidence_id])
    loop.assess(
        cycle.id,
        bottleneck="No remaining time",
        candidates=[_candidate("Finalize", 0.1, 0.1)],
    )
    loop.strategize(cycle.id)
    loop.record_execution(cycle.id, result="Final state recorded", succeeded=True)
    loop.verify(
        cycle.id,
        verified=True,
        finding="Final evidence recorded",
        evidence_ids=[evidence_id],
    )
    loop.measure(cycle.id, before=1.0, after=1.0)

    assert loop.adapt(cycle.id, terminal_status=MissionStatus.COMPLETED) is None
    assert database.get_mission(mission.id).status == MissionStatus.COMPLETED
    with pytest.raises(CompeteLoopError, match="mission is terminal"):
        loop.create_cycle(mission.id)


def test_compete_loop_enforces_stage_and_evidence_contracts(tmp_path):
    _, mission, loop = _active_loop(tmp_path)
    cycle = loop.create_cycle(mission.id)

    with pytest.raises(CompeteLoopError, match="requires ASSESS"):
        loop.assess(
            cycle.id,
            bottleneck="Too early",
            candidates=[_candidate("Act", 0.1, 0.1)],
        )
    loop.observe(cycle.id, "Observed")
    loop.assess(
        cycle.id,
        bottleneck="Known",
        candidates=[_candidate("Act", 0.1, 0.1)],
    )
    loop.strategize(cycle.id)
    loop.record_execution(cycle.id, result="Acted", succeeded=True)
    with pytest.raises(CompeteLoopError, match="authoritative evidence"):
        loop.verify(cycle.id, verified=True, finding="Looks good")
