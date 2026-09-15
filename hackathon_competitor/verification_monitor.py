from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from .agent_index import AgentIndexError, AgentIndexService
from .approvals import ExternalObservationUnavailable
from .metrics import MetricsUnavailable
from .models import (
    ExternalActionKind,
    ExternalActionStatus,
    MissionStatus,
    MonitorOutcome,
    MonitorRunResult,
    utcnow,
)
from .monitoring import BackoffPolicy
from .storage import Database

MONITOR_TYPE = "verification_status"


class VerificationMonitor:
    """A deliberately dumb watch on one public flag.

    It exists to answer exactly one question while a verification request sits
    with the hosts: has the Agent Index marked this agent Verified? It never
    reads the leaderboard, never plans, and never acts on anything else. The
    full Compete Loop is not worth its tokens until the agent is eligible to
    win, and this monitor is what detects that moment.
    """

    monitor_type = MONITOR_TYPE

    def __init__(
        self,
        database: Database,
        service: AgentIndexService,
        *,
        agent_id: str,
        # Supplied by the caller so the eligibility recomputation observes the
        # same inputs the CLI does rather than inventing its own.
        license_spdx: str | None = None,
        reporting_active_days: int | None = None,
        lease_duration: timedelta = timedelta(minutes=10),
        backoff: BackoffPolicy | None = None,
        random_unit: Callable[[], float] = random.random,
    ):
        self.database = database
        self.service = service
        self.agent_id = agent_id
        self.license_spdx = license_spdx
        self.reporting_active_days = reporting_active_days
        self.lease_duration = lease_duration
        self.backoff = backoff or BackoffPolicy()
        self.random_unit = random_unit

    def fingerprint(self, observed_status: str) -> str:
        normalized = f"verification:{self.agent_id}:{observed_status}"
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _pending_action(self, mission_id: UUID) -> UUID | None:
        for action in self.database.list_external_actions(mission_id):
            if (
                action.kind == ExternalActionKind.VERIFICATION_REQUEST
                and action.status == ExternalActionStatus.AWAITING_EXTERNAL
            ):
                return action.id
        return None

    def run(
        self,
        mission_id: UUID,
        *,
        holder: str,
        now: datetime | None = None,
    ) -> MonitorRunResult:
        captured_at = now or utcnow()
        mission = self.database.get_mission(mission_id)
        inert = MonitorRunResult(
            outcome=MonitorOutcome.UNCHANGED,
            mission_id=mission.id,
            monitor_type=self.monitor_type,
        )
        if mission.status != MissionStatus.ACTIVE or mission.state.value in {"PAUSED", "CANCELLED"}:
            return inert
        # Nothing to watch until a handoff has actually been delivered. This is
        # what makes the monitor safe to schedule before the request is sent.
        action_id = self._pending_action(mission.id)
        if action_id is None:
            return inert

        state = self.database.get_monitor_backoff(mission.id, self.monitor_type)
        if state.next_attempt_at is not None and captured_at < state.next_attempt_at:
            return MonitorRunResult(
                outcome=MonitorOutcome.BACKING_OFF,
                mission_id=mission.id,
                monitor_type=self.monitor_type,
                next_attempt_at=state.next_attempt_at,
            )

        lease_key = f"verification-monitor:{mission.id}"
        if not self.database.acquire_monitor_lease(
            lease_key=lease_key,
            mission_id=mission.id,
            holder=holder,
            acquired_at=captured_at,
            expires_at=captured_at + self.lease_duration,
        ):
            return MonitorRunResult(
                outcome=MonitorOutcome.LEASED_OUT,
                mission_id=mission.id,
                monitor_type=self.monitor_type,
            )
        try:
            return self._run_acquired(mission.id, action_id, captured_at)
        except (
            ExternalObservationUnavailable,
            MetricsUnavailable,
            AgentIndexError,
            OSError,
        ) as exc:
            # A source that could not be read is not an agent that is still
            # unverified. Collapsing the two would let an outage read as a
            # steady, healthy "not yet".
            return self._record_failure(mission.id, captured_at, exc)
        finally:
            self.database.release_monitor_lease(lease_key=lease_key, holder=holder)

    def _run_acquired(
        self,
        mission_id: UUID,
        action_id: UUID,
        captured_at: datetime,
    ) -> MonitorRunResult:
        mission = self.database.get_mission(mission_id)
        if mission.state.value in {"PAUSED", "CANCELLED"}:
            return MonitorRunResult(
                outcome=MonitorOutcome.UNCHANGED,
                mission_id=mission_id,
                monitor_type=self.monitor_type,
            )
        observed = self.service.poll_handoff(action_id)
        verified = bool(observed.get("verified"))
        fingerprint = self.fingerprint("VERIFIED" if verified else "UNVERIFIED")
        # The shared fingerprint table is what makes a repeated "still pending"
        # cheap: the first one is recorded, every later one is a no-op.
        first_time = self.database.reserve_observation_fingerprint(
            fingerprint=fingerprint,
            mission_id=mission_id,
            monitor_type=self.monitor_type,
            observation_id=None,
            first_seen_at=captured_at,
        )

        if not verified:
            # Persist the observation and stop. No planning, no strategy, no
            # tokens spent on a race this agent cannot yet win.
            self._record_success(mission_id)
            if first_time:
                self.database.append_event(
                    mission_id,
                    "VERIFICATION_STILL_PENDING",
                    {"agent_id": self.agent_id, "fingerprint": fingerprint},
                )
            return MonitorRunResult(
                outcome=MonitorOutcome.CHANGED if first_time else MonitorOutcome.UNCHANGED,
                mission_id=mission_id,
                monitor_type=self.monitor_type,
                fingerprint=fingerprint,
            )

        eligibility = self.service.eligibility(
            self.agent_id,
            license_spdx=self.license_spdx,
            reporting_active_days=self.reporting_active_days,
        )
        self.database.append_event(
            mission_id,
            "ELIGIBILITY_ACHIEVED" if eligibility.eligible_to_win else "VERIFICATION_OBSERVED",
            {
                "agent_id": self.agent_id,
                "action_id": str(action_id),
                "verified": True,
                "eligible_to_win": eligibility.eligible_to_win,
                "blockers": eligibility.blockers,
                "observed_at": captured_at.isoformat(),
            },
        )
        self._record_success(mission_id)
        return MonitorRunResult(
            outcome=MonitorOutcome.CHANGED,
            mission_id=mission_id,
            monitor_type=self.monitor_type,
            fingerprint=fingerprint,
        )

    def _record_success(self, mission_id: UUID) -> None:
        state = self.database.get_monitor_backoff(mission_id, self.monitor_type)
        state.consecutive_failures = 0
        state.next_attempt_at = None
        state.last_error = None
        state.updated_at = utcnow()
        self.database.save_monitor_backoff(state)

    def _record_failure(
        self,
        mission_id: UUID,
        captured_at: datetime,
        error: BaseException,
    ) -> MonitorRunResult:
        state = self.database.get_monitor_backoff(mission_id, self.monitor_type)
        state.consecutive_failures += 1
        state.last_error = str(error) or type(error).__name__
        # The last successful observation is deliberately preserved: it is how
        # an operator tells a quiet source from an unreachable one.
        state.next_attempt_at = captured_at + self.backoff.delay(
            state.consecutive_failures, self.random_unit()
        )
        self.database.save_monitor_backoff(state)
        return MonitorRunResult(
            outcome=MonitorOutcome.FAILED,
            mission_id=mission_id,
            monitor_type=self.monitor_type,
            next_attempt_at=state.next_attempt_at,
        )
