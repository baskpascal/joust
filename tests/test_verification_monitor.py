from datetime import timedelta

import pytest

from hackathon_competitor.agent_index import AgentIndexError, AgentIndexReader, AgentIndexService
from hackathon_competitor.metrics import MetricsUnavailable
from hackathon_competitor.models import (
    ExternalActionStatus,
    Mission,
    MissionStatus,
    MonitorOutcome,
    utcnow,
)
from hackathon_competitor.storage import Database
from hackathon_competitor.verification_monitor import VerificationMonitor

from test_agent_index import FakeClient, FakeHttp


class FlakyHttp(FakeHttp):
    def __init__(self, record):
        super().__init__(record)
        self.fail = False

    def get(self, url, *, timeout):
        if self.fail:
            raise MetricsUnavailable("Agent Index request failed: TimeoutError")
        return super().get(url, timeout=timeout)


def _setup(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="plow", objective="compete", workspace_path=str(tmp_path))
    mission.status = MissionStatus.ACTIVE
    database.save_mission(mission)
    http = FlakyHttp({"agent_id": "galahad-hackathon", "name": "Joust", "blessed_at": ""})
    reader = AgentIndexReader(base_url="https://index.invalid", http=http)
    service = AgentIndexService(database, client=FakeClient(http), reader=reader)
    monitor = VerificationMonitor(
        database,
        service,
        agent_id="galahad-hackathon",
        license_spdx="MIT",
        reporting_active_days=2,
        random_unit=lambda: 0.5,
    )
    return database, mission, service, monitor, http


def _delivered_request(service, mission):
    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    action = service.request_verification(
        mission.id,
        agent_id="galahad-hackathon",
        eligibility=report,
        contact_route="Plow Discord",
        repository_url="https://github.com/baskpascal/joust",
        commit_sha="fb7a22e",
        idempotency_key="verification:galahad-hackathon:fb7a22e",
    )
    service.external.approvals.decide(
        action.approval_id, granted=True, explicit_confirmation=True
    )
    service.deliver_verification_request(action.id, deliver=lambda _a, _h: {"reference": "t1"})
    return action


def test_monitor_is_inert_until_a_handoff_is_delivered(tmp_path):
    database, mission, service, monitor, http = _setup(tmp_path)
    # Safe to schedule before anything is sent: nothing is read, nothing acts.
    result = monitor.run(mission.id, holder="worker-1")
    assert result.outcome == MonitorOutcome.UNCHANGED
    assert http.reads == 0

    _delivered_request(service, mission)
    before = http.reads
    monitor.run(mission.id, holder="worker-1")
    assert http.reads > before


def test_pending_observations_are_cheap_and_take_no_action(tmp_path):
    database, mission, service, monitor, _http = _setup(tmp_path)
    _delivered_request(service, mission)

    first = monitor.run(mission.id, holder="worker-1")
    assert first.outcome == MonitorOutcome.CHANGED
    second = monitor.run(mission.id, holder="worker-1")
    assert second.outcome == MonitorOutcome.UNCHANGED
    assert second.fingerprint == first.fingerprint

    events = [item["event_type"] for item in database.events(mission.id)]
    assert events.count("VERIFICATION_STILL_PENDING") == 1
    assert "ELIGIBILITY_ACHIEVED" not in events


def test_observed_verification_emits_eligibility_achieved(tmp_path):
    database, mission, service, monitor, http = _setup(tmp_path)
    action = _delivered_request(service, mission)
    monitor.run(mission.id, holder="worker-1")

    http.record["blessed_at"] = "2026-09-15T10:00:00Z"
    result = monitor.run(mission.id, holder="worker-1")
    assert result.outcome == MonitorOutcome.CHANGED

    events = [item["event_type"] for item in database.events(mission.id)]
    assert "ELIGIBILITY_ACHIEVED" in events
    assert (
        database.get_external_action(action.id).status == ExternalActionStatus.VERIFIED
    )


def test_an_unreadable_source_is_a_failure_not_a_quiet_pending(tmp_path):
    database, mission, service, monitor, http = _setup(tmp_path)
    _delivered_request(service, mission)
    monitor.run(mission.id, holder="worker-1")

    http.fail = True
    failed = monitor.run(mission.id, holder="worker-1")
    assert failed.outcome == MonitorOutcome.FAILED
    assert failed.next_attempt_at is not None

    state = database.get_monitor_backoff(mission.id, monitor.monitor_type)
    assert state.consecutive_failures == 1
    assert "Agent Index request failed" in state.last_error

    # Backed off: it does not hammer the Index on the next tick.
    assert monitor.run(mission.id, holder="worker-1").outcome == MonitorOutcome.BACKING_OFF

    # A later success clears the backoff without losing the record of it.
    http.fail = False
    later = utcnow() + timedelta(hours=2)
    assert monitor.run(mission.id, holder="worker-1", now=later).outcome in {
        MonitorOutcome.CHANGED,
        MonitorOutcome.UNCHANGED,
    }
    assert database.get_monitor_backoff(mission.id, monitor.monitor_type).consecutive_failures == 0


def test_one_worker_at_a_time(tmp_path):
    database, mission, service, monitor, _http = _setup(tmp_path)
    _delivered_request(service, mission)
    database.acquire_monitor_lease(
        lease_key=f"verification-monitor:{mission.id}",
        mission_id=mission.id,
        holder="worker-other",
        acquired_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    assert monitor.run(mission.id, holder="worker-1").outcome == MonitorOutcome.LEASED_OUT


def test_polling_can_never_re_deliver_a_handoff(tmp_path):
    _database, mission, service, _monitor, _http = _setup(tmp_path)
    action = _delivered_request(service, mission)
    # The delivered action resumes at observation, so the executor is
    # unreachable; an undelivered one is refused outright.
    assert service.poll_handoff(action.id)["verified"] is False

    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    undelivered = service.request_verification(
        mission.id,
        agent_id="galahad-hackathon",
        eligibility=report,
        contact_route="Plow Discord",
        repository_url="https://github.com/baskpascal/joust",
        commit_sha="deadbee",
        idempotency_key="verification:galahad-hackathon:deadbee",
    )
    with pytest.raises(AgentIndexError, match="only a delivered handoff"):
        service.poll_handoff(undelivered.id)


def test_a_failed_poll_keeps_the_action_waiting(tmp_path):
    database, mission, service, monitor, http = _setup(tmp_path)
    action = _delivered_request(service, mission)

    http.fail = True
    assert monitor.run(mission.id, holder="worker-1").outcome == MonitorOutcome.FAILED
    # The third party has not acted and has not refused; one unreadable minute
    # must not end the wait.
    assert (
        database.get_external_action(action.id).status
        == ExternalActionStatus.AWAITING_EXTERNAL
    )
    events = [item["event_type"] for item in database.events(mission.id)]
    assert "EXTERNAL_ACTION_OBSERVATION_UNAVAILABLE" in events
