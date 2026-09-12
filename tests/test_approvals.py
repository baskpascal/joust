import pytest

from hackathon_competitor.approvals import ApprovalRequired, ApprovalService
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
