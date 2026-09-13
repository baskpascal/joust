from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from .models import (
    ActionCandidate,
    CompeteStage,
    CompetitionCycle,
    MissionStatus,
    utcnow,
)
from .storage import Database


class CompeteLoopError(ValueError):
    pass


class CompeteLoop:
    """Persistent deterministic controller for Joust's competition loop."""

    def __init__(self, database: Database):
        self.database = database

    def create_cycle(self, mission_id: UUID) -> CompetitionCycle:
        mission = self.database.get_mission(mission_id)
        if mission.status != MissionStatus.ACTIVE:
            raise CompeteLoopError(f"mission is terminal: {mission.status.value}")
        existing = self.database.list_competition_cycles(mission_id)
        if existing and existing[-1].completed_at is None:
            raise CompeteLoopError("mission already has an incomplete competition cycle")
        cycle = CompetitionCycle(mission_id=mission_id, sequence=len(existing) + 1)
        self.database.save_competition_cycle(cycle)
        self.database.append_event(
            mission_id,
            "COMPETE_CYCLE_STARTED",
            {"cycle_id": str(cycle.id), "sequence": cycle.sequence},
        )
        return cycle

    def _require_stage(self, cycle_id: UUID, expected: CompeteStage) -> CompetitionCycle:
        cycle = self.database.get_competition_cycle(cycle_id)
        if cycle.stage != expected:
            raise CompeteLoopError(
                f"competition cycle requires {expected.value}, got {cycle.stage.value}"
            )
        return cycle

    def _advance(self, cycle: CompetitionCycle, stage: CompeteStage) -> CompetitionCycle:
        prior = cycle.stage
        cycle.stage = stage
        cycle.updated_at = utcnow()
        self.database.save_competition_cycle(cycle)
        self.database.append_event(
            cycle.mission_id,
            "COMPETE_STAGE_CHANGED",
            {
                "cycle_id": str(cycle.id),
                "from": prior.value,
                "to": stage.value,
            },
        )
        return cycle

    def observe(
        self,
        cycle_id: UUID,
        observation: str,
        *,
        evidence_ids: Sequence[UUID] = (),
    ) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.OBSERVE)
        if not observation.strip():
            raise CompeteLoopError("observation cannot be empty")
        cycle.observation = observation.strip()
        cycle.observation_evidence_ids = list(evidence_ids)
        return self._advance(cycle, CompeteStage.ASSESS)

    def assess(
        self,
        cycle_id: UUID,
        *,
        bottleneck: str,
        candidates: Sequence[ActionCandidate],
    ) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.ASSESS)
        if not bottleneck.strip():
            raise CompeteLoopError("assessment bottleneck cannot be empty")
        if not candidates:
            raise CompeteLoopError("assessment requires at least one candidate action")
        if len({candidate.name for candidate in candidates}) != len(candidates):
            raise CompeteLoopError("candidate action names must be unique")
        cycle.bottleneck = bottleneck.strip()
        cycle.candidate_actions = list(candidates)
        mission = self.database.get_mission(cycle.mission_id)
        mission.current_bottleneck = cycle.bottleneck
        self.database.save_mission(mission)
        return self._advance(cycle, CompeteStage.STRATEGIZE)

    def strategize(self, cycle_id: UUID) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.STRATEGIZE)
        if not cycle.candidate_actions:
            raise CompeteLoopError("strategy selection requires candidate actions")
        selected = min(
            cycle.candidate_actions,
            key=lambda item: (
                -item.utility,
                -item.expected_outcome_improvement,
                item.time_cost,
                item.name,
            ),
        )
        cycle.selected_action = selected
        mission = self.database.get_mission(cycle.mission_id)
        mission.current_best_action = selected.name
        self.database.save_mission(mission)
        return self._advance(cycle, CompeteStage.EXECUTE)

    def record_execution(
        self,
        cycle_id: UUID,
        *,
        result: str,
        succeeded: bool,
    ) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.EXECUTE)
        if not result.strip():
            raise CompeteLoopError("execution result cannot be empty")
        cycle.execution_result = result.strip()
        cycle.execution_succeeded = succeeded
        return self._advance(cycle, CompeteStage.VERIFY)

    def verify(
        self,
        cycle_id: UUID,
        *,
        verified: bool,
        finding: str,
        evidence_ids: Sequence[UUID] = (),
    ) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.VERIFY)
        if not finding.strip():
            raise CompeteLoopError("verification finding cannot be empty")
        if verified and not evidence_ids:
            raise CompeteLoopError("verified results require authoritative evidence")
        cycle.verified = verified
        cycle.verification_finding = finding.strip()
        cycle.verification_evidence_ids = list(evidence_ids)
        return self._advance(cycle, CompeteStage.MEASURE)

    def measure(self, cycle_id: UUID, *, before: float, after: float) -> CompetitionCycle:
        cycle = self._require_stage(cycle_id, CompeteStage.MEASURE)
        cycle.metric_before = before
        cycle.metric_after = after
        cycle.measured_delta = after - before
        return self._advance(cycle, CompeteStage.ADAPT)

    def adapt(
        self,
        cycle_id: UUID,
        *,
        next_bottleneck: str | None = None,
        next_best_action: str | None = None,
        mission_score: float | None = None,
        confidence: float | None = None,
        terminal_status: MissionStatus | None = None,
    ) -> CompetitionCycle | None:
        cycle = self._require_stage(cycle_id, CompeteStage.ADAPT)
        if terminal_status == MissionStatus.ACTIVE:
            raise CompeteLoopError("ACTIVE is not a terminal status")
        mission = self.database.get_mission(cycle.mission_id)
        mission.current_bottleneck = next_bottleneck
        mission.current_best_action = next_best_action
        if mission_score is not None:
            mission.mission_score = mission_score
        if confidence is not None:
            mission.confidence = confidence
        if terminal_status is not None:
            mission.status = terminal_status
        self.database.save_mission(mission)
        cycle.completed_at = utcnow()
        cycle.updated_at = cycle.completed_at
        self.database.save_competition_cycle(cycle)
        self.database.append_event(
            cycle.mission_id,
            "COMPETE_CYCLE_COMPLETED",
            {
                "cycle_id": str(cycle.id),
                "sequence": cycle.sequence,
                "measured_delta": cycle.measured_delta,
                "terminal_status": terminal_status.value if terminal_status else None,
            },
        )
        if terminal_status is not None:
            return None
        return self.create_cycle(cycle.mission_id)
