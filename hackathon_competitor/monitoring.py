from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from .compete_loop import CompeteLoop
from .competition_runner import CompetitionIterationRunner
from .models import (
    CompeteStage,
    CompetitionObservation,
    MissionStatus,
    MonitorOutcome,
    MonitorRunResult,
    utcnow,
)
from .storage import Database


class ObservationUnavailable(RuntimeError):
    """The source could not be observed; this is not an unchanged result."""


@dataclass(frozen=True)
class BackoffPolicy:
    schedule_seconds: tuple[int, ...] = (60, 120, 300, 900, 3600)
    jitter_ratio: float = 0.2

    def delay(self, consecutive_failures: int, random_unit: float) -> timedelta:
        index = min(max(consecutive_failures, 1) - 1, len(self.schedule_seconds) - 1)
        base = self.schedule_seconds[index]
        factor = 1.0 + ((random_unit * 2.0) - 1.0) * self.jitter_ratio
        return timedelta(seconds=max(1, round(base * factor)))


def observation_fingerprint(
    mission_id: UUID,
    monitor_type: str,
    observation: CompetitionObservation,
) -> str:
    """Hash stable observed state, excluding capture ids and timestamps."""

    normalized = {
        "mission_id": str(mission_id),
        "monitor_type": monitor_type,
        "deadline_at": observation.deadline_at.isoformat() if observation.deadline_at else None,
        "deadline_state": observation.deadline_state,
        "active_rule_ids": sorted(str(item) for item in observation.active_rule_ids),
        "project_target_id": (
            str(observation.project_target_id) if observation.project_target_id else None
        ),
        "repository_exists": observation.repository_exists,
        "repository_revision": observation.repository_revision,
        "repository_dirty": observation.repository_dirty,
        "latest_change_status": observation.latest_change_status,
        "build_summary": observation.build_summary,
        "github_checks": observation.github_checks,
        "deployment_health": observation.deployment_health,
        "submission_state": observation.submission_state,
        "score_signals": observation.score_signals,
        "findings": sorted(observation.findings),
        "uncertainties": sorted(observation.uncertainties),
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class MonitoredCompetitionRunner:
    """Cron-safe gate around one competition iteration."""

    def __init__(
        self,
        database: Database,
        runner: CompetitionIterationRunner,
        *,
        monitor_type: str = "competition_state",
        lease_duration: timedelta = timedelta(minutes=5),
        backoff: BackoffPolicy | None = None,
        random_unit: Callable[[], float] = random.random,
    ):
        self.database = database
        self.runner = runner
        self.monitor_type = monitor_type
        self.lease_duration = lease_duration
        self.backoff = backoff or BackoffPolicy()
        self.random_unit = random_unit

    def run(
        self,
        mission_id: UUID,
        *,
        holder: str,
        now: datetime | None = None,
    ) -> MonitorRunResult:
        captured_at = now or utcnow()
        mission = self.database.get_mission(mission_id)
        if mission.status != MissionStatus.ACTIVE:
            return MonitorRunResult(
                outcome=MonitorOutcome.UNCHANGED,
                mission_id=mission.id,
                monitor_type=self.monitor_type,
            )
        state = self.database.get_monitor_backoff(mission.id, self.monitor_type)
        if state.next_attempt_at is not None and captured_at < state.next_attempt_at:
            return MonitorRunResult(
                outcome=MonitorOutcome.BACKING_OFF,
                mission_id=mission.id,
                monitor_type=self.monitor_type,
                next_attempt_at=state.next_attempt_at,
            )

        lease_key = f"mission:{mission.id}:{self.monitor_type}"
        acquired = self.database.acquire_monitor_lease(
            lease_key=lease_key,
            mission_id=mission.id,
            holder=holder,
            acquired_at=captured_at,
            expires_at=captured_at + self.lease_duration,
        )
        if not acquired:
            return MonitorRunResult(
                outcome=MonitorOutcome.LEASED_OUT,
                mission_id=mission.id,
                monitor_type=self.monitor_type,
            )

        try:
            return self._run_acquired(mission.id, captured_at)
        except Exception as exc:  # noqa: BLE001 - cron boundary converts failure to durable state
            return self._record_failure(mission.id, captured_at, exc)
        finally:
            self.database.release_monitor_lease(lease_key=lease_key, holder=holder)

    def _run_acquired(self, mission_id: UUID, now: datetime) -> MonitorRunResult:
        cycles = self.database.list_competition_cycles(mission_id)
        cycle = cycles[-1] if cycles and cycles[-1].completed_at is None else None
        if cycle is None:
            cycle = CompeteLoop(self.database).create_cycle(mission_id)

        observations = [
            item
            for item in self.database.list_competition_observations(mission_id)
            if item.cycle_id == cycle.id
        ]
        fingerprint = None
        if cycle.stage == CompeteStage.OBSERVE and not observations:
            try:
                observation = self.runner.observer.collect(cycle.id, now=now)
            except Exception as exc:
                raise ObservationUnavailable(str(exc)) from exc
            failures = [
                item for item in observation.uncertainties if " observation failed:" in item
            ]
            if failures:
                raise ObservationUnavailable("; ".join(failures))
            fingerprint = observation_fingerprint(mission_id, self.monitor_type, observation)
            if self.database.has_observation_fingerprint(fingerprint):
                self._record_success(mission_id, last_observation_id=None)
                self.database.append_event(
                    mission_id,
                    "COMPETITION_OBSERVATION_UNCHANGED",
                    {"cycle_id": str(cycle.id), "fingerprint": fingerprint},
                )
                return MonitorRunResult(
                    outcome=MonitorOutcome.UNCHANGED,
                    mission_id=mission_id,
                    monitor_type=self.monitor_type,
                    cycle_id=cycle.id,
                    fingerprint=fingerprint,
                )
            observation = self.runner.observer.record(observation)
            self.database.reserve_observation_fingerprint(
                fingerprint=fingerprint,
                mission_id=mission_id,
                monitor_type=self.monitor_type,
                observation_id=observation.id,
                first_seen_at=now,
            )
            self._record_success(mission_id, last_observation_id=observation.id)
        elif observations:
            observation = observations[-1]
            fingerprint = observation_fingerprint(mission_id, self.monitor_type, observation)
            self.database.reserve_observation_fingerprint(
                fingerprint=fingerprint,
                mission_id=mission_id,
                monitor_type=self.monitor_type,
                observation_id=observation.id,
                first_seen_at=observation.observed_at,
            )
        else:
            raise RuntimeError("advanced competition cycle has no durable observation")

        self.runner.run(mission_id)
        self._record_success(mission_id, last_observation_id=observation.id)
        return MonitorRunResult(
            outcome=MonitorOutcome.CHANGED,
            mission_id=mission_id,
            monitor_type=self.monitor_type,
            cycle_id=cycle.id,
            observation_id=observation.id,
            fingerprint=fingerprint,
        )

    def _record_success(self, mission_id: UUID, last_observation_id: UUID | None) -> None:
        current = self.database.get_monitor_backoff(mission_id, self.monitor_type)
        current.consecutive_failures = 0
        current.next_attempt_at = None
        current.last_error = None
        if last_observation_id is not None:
            current.last_successful_observation_id = last_observation_id
        current.updated_at = utcnow()
        self.database.save_monitor_backoff(current)

    def _record_failure(
        self, mission_id: UUID, now: datetime, error: Exception
    ) -> MonitorRunResult:
        state = self.database.get_monitor_backoff(mission_id, self.monitor_type)
        state.consecutive_failures += 1
        state.next_attempt_at = now + self.backoff.delay(
            state.consecutive_failures, self.random_unit()
        )
        state.last_error = f"{type(error).__name__}: {str(error)[:900]}"
        state.updated_at = now
        self.database.save_monitor_backoff(state)
        event_type = (
            "COMPETITION_OBSERVATION_FAILED"
            if isinstance(error, ObservationUnavailable)
            else "COMPETITION_MONITOR_RUN_FAILED"
        )
        self.database.append_event(
            mission_id,
            event_type,
            {
                "monitor_type": self.monitor_type,
                "error_type": type(error).__name__,
                "error": str(error)[:1000],
                "consecutive_failures": state.consecutive_failures,
                "next_attempt_at": state.next_attempt_at.isoformat(),
                "last_successful_observation_id": (
                    str(state.last_successful_observation_id)
                    if state.last_successful_observation_id
                    else None
                ),
            },
        )
        return MonitorRunResult(
            outcome=MonitorOutcome.FAILED,
            mission_id=mission_id,
            monitor_type=self.monitor_type,
            next_attempt_at=state.next_attempt_at,
        )
