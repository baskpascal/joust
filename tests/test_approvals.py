import pytest

from hackathon_competitor.approvals import (
    ApprovalRequired,
    ApprovalService,
    ExternalActionService,
    ExternalActionVerificationError,
)
from hackathon_competitor.models import (
    ApprovalLevel,
    ApprovalStatus,
    ExternalActionKind,
    ExternalActionRisk,
    ExternalActionStatus,
    Mission,
    ObservedExternalResult,
)
from hackathon_competitor.storage import Database


def _setup(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    return database, mission, ExternalActionService(database)


def _propose(service, mission, *, key="publish-1", kind=ExternalActionKind.FINAL_SUBMISSION):
    return service.propose(
        mission.id,
        kind=kind,
        target="https://competition.example/entry",
        description="publish the final entry",
        risk=ExternalActionRisk.IRREVERSIBLE_SUBMISSION,
        approval_level=ApprovalLevel.HUMAN_ONLY,
        idempotency_key=key,
        payload={"entry": "joust"},
        expected_state={"published": True},
    )


def _observed(*, matches=True):
    return ObservedExternalResult(
        actual_state={"published": matches},
        matches_expected=matches,
        source_uri="https://competition.example/entry",
        summary="remote state matches" if matches else "remote state mismatch",
    )


def test_consequential_action_needs_explicit_confirmation(tmp_path):
    database, mission, _ = _setup(tmp_path)
    service = ApprovalService(database)
    approval = service.request(mission.id, "final submission", ApprovalLevel.HUMAN_ONLY)
    assert approval.status == ApprovalStatus.PENDING
    with pytest.raises(ApprovalRequired, match="explicit"):
        service.decide(approval.id, granted=True, explicit_confirmation=False)
    granted = service.decide(
        approval.id, granted=True, explicit_confirmation=True, note="user said submit now"
    )
    assert service.require_granted(granted.id).status == ApprovalStatus.GRANTED


def test_safe_local_action_is_auto_granted(tmp_path):
    database, mission, _ = _setup(tmp_path)
    approval = ApprovalService(database).request(mission.id, "run tests", ApprovalLevel.AUTO)
    assert approval.status == ApprovalStatus.GRANTED


def test_external_action_requires_approval_observation_and_is_idempotent(tmp_path):
    database, mission, service = _setup(tmp_path)
    action = _propose(service, mission)
    calls = []

    assert database.list_external_actions(mission.id) == [action]

    with pytest.raises(ApprovalRequired, match="pending"):
        service.execute(
            action.id,
            executor=lambda key: calls.append(key),
            observer=lambda result: _observed(),
        )
    assert calls == []

    ApprovalService(database).decide(
        action.approval_id, granted=True, explicit_confirmation=True, note="publish now"
    )
    first = service.execute(
        action.id,
        executor=lambda key: calls.append(key) or {"accepted": True},
        observer=lambda result: _observed(),
    )
    second = service.execute(
        action.id,
        executor=lambda key: calls.append(key) or {"accepted": True},
        observer=lambda result: _observed(),
    )

    assert first.id == second.id
    assert calls == ["publish-1"]
    assert database.get_external_action(action.id).status == ExternalActionStatus.VERIFIED
    assert database.list_evidence(mission.id)[-1].source_type == "external_action_observation"


def test_external_action_cannot_be_auto_approved(tmp_path):
    _, mission, service = _setup(tmp_path)
    with pytest.raises(ApprovalRequired, match="AUTO"):
        service.propose(
            mission.id,
            kind=ExternalActionKind.DEPLOY,
            target="preview",
            description="deploy preview",
            risk=ExternalActionRisk.REMOTE_MUTATION,
            approval_level=ApprovalLevel.AUTO,
            idempotency_key="deploy-1",
        )


@pytest.mark.parametrize("kind", list(ExternalActionKind))
def test_every_supported_external_action_kind_uses_the_same_pending_gate(tmp_path, kind):
    database, mission, service = _setup(tmp_path)
    action = service.propose(
        mission.id,
        kind=kind,
        target="remote-target",
        description=f"perform {kind.value}",
        risk=ExternalActionRisk.REMOTE_MUTATION,
        approval_level=ApprovalLevel.CONFIRM,
        idempotency_key=f"{kind.value}-1",
    )
    assert action.status == ExternalActionStatus.PROPOSED
    assert database.get_approval(action.approval_id).status == ApprovalStatus.PENDING


def test_external_action_does_not_reuse_key_for_a_different_action(tmp_path):
    _, mission, service = _setup(tmp_path)
    first = _propose(service, mission, key="same-key")
    assert _propose(service, mission, key="same-key").id == first.id
    with pytest.raises(ApprovalRequired, match="another action"):
        _propose(service, mission, key="same-key", kind=ExternalActionKind.VERIFICATION_REQUEST)


def test_denied_action_never_calls_executor(tmp_path):
    database, mission, service = _setup(tmp_path)
    action = _propose(service, mission)
    ApprovalService(database).decide(
        action.approval_id, granted=False, explicit_confirmation=True, note="do not publish"
    )
    calls = []
    with pytest.raises(ApprovalRequired, match="denied"):
        service.execute(
            action.id,
            executor=lambda key: calls.append(key),
            observer=lambda result: _observed(),
        )
    assert calls == []
    assert database.get_external_action(action.id).status == ExternalActionStatus.DENIED


def test_remote_mismatch_is_evidenced_but_not_verified(tmp_path):
    database, mission, service = _setup(tmp_path)
    action = _propose(service, mission)
    ApprovalService(database).decide(action.approval_id, granted=True, explicit_confirmation=True)
    with pytest.raises(ExternalActionVerificationError, match="mismatch"):
        service.execute(
            action.id,
            executor=lambda key: {"accepted": True},
            observer=lambda result: _observed(matches=False),
        )
    assert database.get_external_action(action.id).status == ExternalActionStatus.FAILED
    assert not database.list_external_action_observations(action.id)[0].matches_expected


def test_interrupted_action_retries_with_the_same_external_idempotency_key(tmp_path):
    database, mission, service = _setup(tmp_path)
    action = _propose(service, mission)
    ApprovalService(database).decide(action.approval_id, granted=True, explicit_confirmation=True)
    keys = []

    def interrupted(key):
        keys.append(key)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        service.execute(action.id, executor=interrupted, observer=lambda result: _observed())
    observation = service.execute(
        action.id,
        executor=lambda key: keys.append(key) or {"accepted": True},
        observer=lambda result: _observed(),
    )
    assert observation.matches_expected
    assert keys == ["publish-1", "publish-1"]


def test_interrupted_observation_resumes_without_repeating_external_mutation(tmp_path):
    database, mission, service = _setup(tmp_path)
    action = _propose(service, mission)
    ApprovalService(database).decide(action.approval_id, granted=True, explicit_confirmation=True)
    executions = []
    observations = []

    def interrupted_observer(result):
        observations.append(result)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        service.execute(
            action.id,
            executor=lambda key: executions.append(key) or {"accepted": True},
            observer=interrupted_observer,
        )
    result = service.execute(
        action.id,
        executor=lambda key: executions.append(key) or {"accepted": True},
        observer=lambda value: observations.append(value) or _observed(),
    )

    assert result.matches_expected
    assert executions == ["publish-1"]
    assert observations == [{"accepted": True}, {"accepted": True}]
