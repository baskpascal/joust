from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .compete_loop import CompeteLoop, CompeteLoopError
from .competition_actions import CompetitionActionDispatcher
from .models import (
    ActionExecution,
    ActionExecutionStatus,
    AdaptationPlan,
    AssessmentPlan,
    CompeteStage,
    CompetitionCycle,
    CompetitionObservation,
    Measurement,
    Mission,
    MissionStatus,
    MissionState,
)
from .observation import CompetitionObserver
from .storage import Database


class CompetitionPlanner(Protocol):
    def assess(
        self,
        mission: Mission,
        observation: CompetitionObservation,
    ) -> AssessmentPlan: ...

    def adapt(
        self,
        mission: Mission,
        cycle: CompetitionCycle,
        execution: ActionExecution,
        measurement: Measurement,
    ) -> AdaptationPlan: ...


class CompetitionMeasurer(Protocol):
    def measure(
        self,
        mission: Mission,
        observation: CompetitionObservation,
        execution: ActionExecution,
    ) -> Measurement: ...


class CompetitionIterationRunner:
    """Resume and finish one durable COMPETE iteration.

    Hermes cron owns scheduling. This runner owns deterministic stage
    progression and can be called again after a process restart.
    """

    def __init__(
        self,
        database: Database,
        observer: CompetitionObserver,
        planner: CompetitionPlanner,
        dispatcher: CompetitionActionDispatcher,
        measurer: CompetitionMeasurer,
    ):
        self.database = database
        self.observer = observer
        self.planner = planner
        self.dispatcher = dispatcher
        self.measurer = measurer
        self.loop = CompeteLoop(database)

    def run(self, mission_id: UUID) -> CompetitionCycle | None:
        mission = self.database.get_mission(mission_id)
        if mission.status != MissionStatus.ACTIVE or mission.state in {MissionState.PAUSED, MissionState.CANCELLED}:
            return None
        cycles = self.database.list_competition_cycles(mission.id)
        cycle = cycles[-1] if cycles and cycles[-1].completed_at is None else None
        if cycle is None:
            cycle = self.loop.create_cycle(mission.id)

        observation = self._observation(cycle)
        cycle = self.database.get_competition_cycle(cycle.id)
        if observation.deadline_state == "expired":
            return self.loop.terminate(
                cycle.id,
                status=MissionStatus.EXPIRED,
                reason="authoritative mission deadline elapsed",
            )

        if cycle.stage == CompeteStage.ASSESS:
            try:
                plan = self.planner.assess(mission, observation)
            except Exception as exc:
                self._record_failure(cycle, CompeteStage.ASSESS, exc)
                raise
            cycle = self.loop.assess(
                cycle.id,
                bottleneck=plan.bottleneck,
                candidates=plan.candidates,
            )
        if cycle.stage == CompeteStage.STRATEGIZE:
            cycle = self.loop.strategize(cycle.id)
        if cycle.stage == CompeteStage.EXECUTE:
            execution = self.dispatcher.execute_selected(cycle.id)
            cycle = self.database.get_competition_cycle(cycle.id)
        else:
            execution = self._execution(cycle)
        if cycle.stage == CompeteStage.VERIFY:
            succeeded = execution.status == ActionExecutionStatus.SUCCEEDED
            evidence_ids = (
                execution.result.evidence_ids if succeeded and execution.result is not None else []
            )
            finding = (
                execution.result.summary
                if succeeded and execution.result is not None
                else execution.error or "competition action failed without a recorded error"
            )
            cycle = self.loop.verify(
                cycle.id,
                verified=succeeded,
                finding=finding,
                evidence_ids=evidence_ids,
            )
        if cycle.stage == CompeteStage.MEASURE:
            measurement = self.measurer.measure(mission, observation, execution)
            cycle = self.loop.measure(
                cycle.id,
                before=measurement.before,
                after=measurement.after,
            )
            self.database.append_event(
                mission.id,
                "COMPETITION_MEASUREMENT_RECORDED",
                {
                    "cycle_id": str(cycle.id),
                    "metric": measurement.metric,
                    "before": measurement.before,
                    "after": measurement.after,
                },
            )
        else:
            measurement = self._measurement(cycle)
        if cycle.stage != CompeteStage.ADAPT:
            raise CompeteLoopError(f"cannot adapt competition cycle from {cycle.stage.value}")
        refreshed_mission = self.database.get_mission(mission.id)
        try:
            adaptation = self.planner.adapt(
                refreshed_mission,
                cycle,
                execution,
                measurement,
            )
        except Exception as exc:
            self._record_failure(cycle, CompeteStage.ADAPT, exc)
            raise
        return self.loop.adapt(
            cycle.id,
            next_bottleneck=adaptation.next_bottleneck,
            next_best_action=adaptation.next_best_action,
            mission_score=adaptation.mission_score,
            confidence=adaptation.confidence,
            terminal_status=adaptation.terminal_status,
        )

    def _observation(self, cycle: CompetitionCycle) -> CompetitionObservation:
        observations = [
            item
            for item in self.database.list_competition_observations(cycle.mission_id)
            if item.cycle_id == cycle.id
        ]
        if observations:
            return observations[-1]
        if cycle.stage != CompeteStage.OBSERVE:
            raise CompeteLoopError("cycle advanced without a durable observation")
        return self.observer.capture(cycle.id)

    def _execution(self, cycle: CompetitionCycle) -> ActionExecution:
        executions = [
            item
            for item in self.database.list_action_executions(cycle.mission_id)
            if item.cycle_id == cycle.id
        ]
        if not executions:
            raise CompeteLoopError("cycle advanced without a durable action execution")
        return executions[-1]

    def _measurement(self, cycle: CompetitionCycle) -> Measurement:
        events = [
            item
            for item in self.database.events(cycle.mission_id)
            if item["event_type"] == "COMPETITION_MEASUREMENT_RECORDED"
            and item["payload"].get("cycle_id") == str(cycle.id)
        ]
        if not events:
            raise CompeteLoopError("cycle advanced without a durable measurement")
        payload = events[-1]["payload"]
        return Measurement(
            metric=str(payload["metric"]),
            before=float(payload["before"]),
            after=float(payload["after"]),
        )

    def _record_failure(
        self,
        cycle: CompetitionCycle,
        stage: CompeteStage,
        error: Exception,
    ) -> None:
        self.database.append_event(
            cycle.mission_id,
            "COMPETITION_ITERATION_FAILED",
            {
                "cycle_id": str(cycle.id),
                "stage": stage.value,
                "error_type": type(error).__name__,
                "error": str(error)[:1000],
            },
        )
