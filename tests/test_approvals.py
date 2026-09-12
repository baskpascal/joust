import pytest

from hackathon_competitor.approvals import ApprovalRequired, ApprovalService, ExternalActionService
from hackathon_competitor.models import ApprovalLevel, ApprovalStatus, Mission
from hackathon_competitor.storage import Database


def test_consequential_action_needs_explicit_confirmation(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
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
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    approval = ApprovalService(database).request(mission.id, "run tests", ApprovalLevel.AUTO)
    assert approval.status == ApprovalStatus.GRANTED


def test_external_action_requires_approval_and_is_idempotent(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    service = ExternalActionService(database)
    approval = service.request(mission.id, "publish", ApprovalLevel.CONFIRM)
    with pytest.raises(ApprovalRequired, match="pending"):
        service.execute(approval.id, idempotency_key="publish-1", action=lambda: "sent")
    ApprovalService(database).decide(
        approval.id, granted=True, explicit_confirmation=True, note="publish now"
    )
    calls = []

    def action():
        calls.append("called")
        return "sent"

    assert service.execute(approval.id, idempotency_key="publish-1", action=action) == "sent"
    assert service.execute(approval.id, idempotency_key="publish-1", action=action) == "sent"
    assert calls == ["called"]
    assert (
        sum(event["event_type"] == "EXTERNAL_ACTION" for event in database.events(mission.id)) == 1
    )


def test_external_action_cannot_be_auto_approved(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    with pytest.raises(ApprovalRequired, match="AUTO"):
        ExternalActionService(database).request(mission.id, "publish", ApprovalLevel.AUTO)


def test_external_action_does_not_reuse_key_for_a_different_action(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    service = ExternalActionService(database)
    first = service.request(mission.id, "publish", ApprovalLevel.CONFIRM)
    ApprovalService(database).decide(first.id, granted=True, explicit_confirmation=True)
    service.execute(first.id, idempotency_key="same-key", action=lambda: "sent")
    second = service.request(mission.id, "send-message", ApprovalLevel.CONFIRM)
    ApprovalService(database).decide(second.id, granted=True, explicit_confirmation=True)
    with pytest.raises(ApprovalRequired, match="another action"):
        service.execute(second.id, idempotency_key="same-key", action=lambda: "sent")
