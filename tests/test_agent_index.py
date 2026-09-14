import pytest

from hackathon_competitor.agent_index import (
    AgentIndexError,
    AgentIndexReader,
    AgentIndexService,
)
from hackathon_competitor.approvals import ApprovalRequired, ExternalActionVerificationError
from hackathon_competitor.models import ExternalActionStatus, Mission
from hackathon_competitor.storage import Database


class FakeHttp:
    """Stands in for the public Agent Index read surface."""

    def __init__(self, record):
        self.record = dict(record)
        self.reads = 0

    def get(self, url, *, timeout):
        self.reads += 1
        return dict(self.record)


class FakeClient:
    def __init__(self, http, stored=None):
        self.http = http
        self.stored = stored
        self.calls = []

    def register(self, agent_id, metadata):
        self.calls.append((agent_id, dict(metadata)))
        # The upstream server decides what it keeps; the fake can be told to
        # keep something different so the observer has something to catch.
        self.http.record.update(self.stored if self.stored is not None else metadata)
        return {"output": "registered"}


def _setup(tmp_path, record=None):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="plow", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    http = FakeHttp(
        record
        if record is not None
        else {"agent_id": "galahad-hackathon", "name": "Joust", "blessed_at": ""}
    )
    reader = AgentIndexReader(base_url="https://index.invalid", http=http)
    client = FakeClient(http)
    service = AgentIndexService(database, client=client, reader=reader)
    return database, mission, service, client, http


def _grant(service, action):
    service.external.approvals.decide(
        action.approval_id, granted=True, explicit_confirmation=True, note="reviewed"
    )


def test_metadata_update_requires_approval_and_observed_storage(tmp_path):
    _database, mission, service, client, _http = _setup(tmp_path)
    action = service.request_metadata_update(
        mission.id,
        agent_id="galahad-hackathon",
        metadata={"blurb": "Drop a competition. Joust it."},
        idempotency_key="index-blurb-1",
    )

    with pytest.raises(ApprovalRequired):
        service.update_metadata(action.id)
    assert client.calls == []

    _grant(service, action)
    observed = service.update_metadata(action.id)
    assert observed["blurb"] == "Drop a competition. Joust it."
    assert len(client.calls) == 1

    # Idempotent: a repeat does not write the public page a second time.
    service.update_metadata(action.id)
    assert len(client.calls) == 1


def test_metadata_update_fails_when_the_index_drops_a_field(tmp_path):
    _database, mission, service, client, http = _setup(tmp_path)
    client.stored = {"blurb": ""}
    action = service.request_metadata_update(
        mission.id,
        agent_id="galahad-hackathon",
        metadata={"blurb": "Drop a competition. Joust it."},
        idempotency_key="index-blurb-2",
    )
    _grant(service, action)

    with pytest.raises(ExternalActionVerificationError, match="did not store"):
        service.update_metadata(action.id)
    assert http.record["blurb"] == ""


def test_metadata_update_rejects_unsupported_fields(tmp_path):
    _database, mission, service, _client, _http = _setup(tmp_path)
    with pytest.raises(AgentIndexError, match="unsupported"):
        service.request_metadata_update(
            mission.id,
            agent_id="galahad-hackathon",
            metadata={"rank": "1"},
            idempotency_key="index-rank",
        )


def test_eligibility_keeps_unobserved_inputs_unknown(tmp_path):
    _database, _mission, service, _client, _http = _setup(tmp_path)
    report = service.eligibility(
        "galahad-hackathon", license_spdx=None, reporting_active_days=None
    )
    assert report.license_is_mit is None
    assert report.reporting_healthy is None
    assert report.verified is False
    assert report.eligible_to_win is False
    assert "license is unobserved" in report.blockers
    assert "usage reporting is unobserved" in report.blockers


def test_eligibility_reports_verification_as_the_only_open_gate(tmp_path):
    _database, _mission, service, _client, _http = _setup(tmp_path)
    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    assert report.license_is_mit is True
    assert report.reporting_healthy is True
    assert report.eligible_to_win is False
    assert report.blockers == ["the Agent Index has not marked this agent Verified"]


def test_verification_is_refused_while_its_own_gate_is_unmet(tmp_path):
    _database, mission, service, _client, _http = _setup(tmp_path)
    report = service.eligibility(
        "galahad-hackathon", license_spdx="Apache-2.0", reporting_active_days=0
    )
    with pytest.raises(AgentIndexError, match="eligibility is unmet"):
        service.request_verification(
            mission.id,
            agent_id="galahad-hackathon",
            eligibility=report,
            contact_route="Plow Discord",
            repository_url="https://github.com/baskpascal/joust",
            commit_sha="abc123",
            idempotency_key="verify-1",
        )


def test_delivered_verification_stays_pending_until_the_index_blesses(tmp_path):
    _database, mission, service, _client, http = _setup(tmp_path)
    deliveries = []

    def deliver(agent_id, handoff):
        deliveries.append((agent_id, handoff))
        return {"reference": "discord-thread-1"}

    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    action = service.request_verification(
        mission.id,
        agent_id="galahad-hackathon",
        eligibility=report,
        contact_route="Plow Discord",
        repository_url="https://github.com/baskpascal/joust",
        commit_sha="abc123",
        idempotency_key="verify-2",
    )
    _grant(service, action)

    observed = service.deliver_verification_request(action.id, deliver=deliver)
    assert observed["verified"] is False
    stored = service.database.get_external_action(action.id)
    # Not VERIFIED, and emphatically not FAILED: Joust did its whole side.
    assert stored.status == ExternalActionStatus.AWAITING_EXTERNAL
    assert len(deliveries) == 1

    # Polling re-observes the remote without re-delivering the handoff.
    service.deliver_verification_request(action.id, deliver=deliver)
    assert len(deliveries) == 1

    http.record["blessed_at"] = "2026-09-20T00:00:00Z"
    final = service.deliver_verification_request(action.id, deliver=deliver)
    assert final["verified"] is True
    assert len(deliveries) == 1
    assert service.database.get_external_action(action.id).status == ExternalActionStatus.VERIFIED


def test_verification_delivery_without_a_reference_is_a_failure(tmp_path):
    _database, mission, service, _client, _http = _setup(tmp_path)
    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    action = service.request_verification(
        mission.id,
        agent_id="galahad-hackathon",
        eligibility=report,
        contact_route="Plow Discord",
        repository_url="https://github.com/baskpascal/joust",
        commit_sha="abc123",
        idempotency_key="verify-3",
    )
    _grant(service, action)

    with pytest.raises(AgentIndexError, match="no reference"):
        service.deliver_verification_request(action.id, deliver=lambda _a, _h: {})
    assert service.database.get_external_action(action.id).status == ExternalActionStatus.FAILED


def test_proposed_verification_carries_the_complete_handoff(tmp_path):
    _database, mission, service, _client, _http = _setup(tmp_path)
    report = service.eligibility(
        "galahad-hackathon", license_spdx="MIT", reporting_active_days=2
    )
    action = service.request_verification(
        mission.id,
        agent_id="galahad-hackathon",
        eligibility=report,
        contact_route="Plow Discord",
        repository_url="https://github.com/baskpascal/joust",
        commit_sha="abc123",
        idempotency_key="verify-4",
    )
    handoff = action.payload["handoff"]
    assert "EXTERNAL ACTION REQUIRED" in handoff
    assert "https://github.com/baskpascal/joust" in handoff
    assert "abc123" in handoff
    assert "Plow Discord" in handoff
    assert "license MIT: True" in handoff


def test_a_pending_result_can_never_also_be_a_match():
    from pydantic import ValidationError

    from hackathon_competitor.models import ObservedExternalResult

    with pytest.raises(ValidationError):
        ObservedExternalResult(
            actual_state={},
            matches_expected=True,
            pending_external=True,
            source_uri="https://index.invalid",
            summary="both at once",
        )


def test_license_observation_reads_the_repository_and_stays_unknown_when_absent(tmp_path):
    from hackathon_competitor.agent_index import observe_license_spdx

    assert observe_license_spdx(tmp_path) is None
    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026\n")
    assert observe_license_spdx(tmp_path) == "MIT"
    (tmp_path / "LICENSE").write_text("Apache License\n")
    assert observe_license_spdx(tmp_path) == "Apache License"
