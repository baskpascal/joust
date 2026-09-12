from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from .models import Approval, ApprovalLevel, ApprovalStatus, utcnow
from .storage import Database


class ApprovalRequired(PermissionError):
    pass


class ExternalActionService:
    """Single gate for publish, message, deploy, and final submission adapters."""

    def __init__(self, database: Database):
        self.database = database
        self.approvals = ApprovalService(database)

    def request(self, mission_id: UUID, action: str, level: ApprovalLevel) -> Approval:
        if level == ApprovalLevel.AUTO:
            raise ApprovalRequired("external actions cannot use AUTO approval")
        return self.approvals.request(mission_id, action, level)

    def execute(
        self,
        approval_id: UUID,
        *,
        idempotency_key: str,
        action: Callable[[], str],
    ) -> str:
        if not idempotency_key.strip():
            raise ValueError("external action requires an idempotency key")
        approval = self.approvals.require_granted(approval_id)
        prior = [
            event
            for event in self.database.events(approval.mission_id)
            if event["event_type"] == "EXTERNAL_ACTION"
            and event["payload"].get("idempotency_key") == idempotency_key
        ]
        if prior:
            if any(event["payload"].get("action") != approval.action for event in prior):
                raise ApprovalRequired("idempotency key is already bound to another action")
            return str(prior[-1]["payload"].get("result", ""))
        result = action()
        self.database.append_event(
            approval.mission_id,
            "EXTERNAL_ACTION",
            {
                "approval_id": str(approval.id),
                "action": approval.action,
                "idempotency_key": idempotency_key,
                "result": result,
            },
        )
        return result


class ApprovalService:
    def __init__(self, database: Database):
        self.database = database

    def request(self, mission_id: UUID, action: str, level: ApprovalLevel) -> Approval:
        approval = Approval(mission_id=mission_id, action=action, level=level)
        if level == ApprovalLevel.AUTO:
            approval.status = ApprovalStatus.GRANTED
            approval.decided_at = utcnow()
            approval.decision_note = "safe reversible local action"
        self.database.save_approval(approval)
        self.database.append_event(
            mission_id,
            "APPROVAL_REQUESTED",
            {"approval_id": str(approval.id), "action": action, "level": level.value},
        )
        if approval.status == ApprovalStatus.GRANTED:
            self.database.append_event(
                mission_id, "APPROVAL_GRANTED", {"approval_id": str(approval.id)}
            )
        return approval

    def decide(
        self,
        approval_id: UUID,
        *,
        granted: bool,
        explicit_confirmation: bool,
        note: str | None = None,
    ) -> Approval:
        approval = self.database.get_approval(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalRequired("approval is no longer pending")
        if not explicit_confirmation:
            raise ApprovalRequired("consequential actions require explicit confirmation")
        approval.status = ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED
        approval.decided_at = utcnow()
        approval.decision_note = note
        self.database.save_approval(approval)
        self.database.append_event(
            approval.mission_id,
            "APPROVAL_GRANTED" if granted else "APPROVAL_DENIED",
            {"approval_id": str(approval.id), "action": approval.action},
        )
        return approval

    def require_granted(self, approval_id: UUID) -> Approval:
        approval = self.database.get_approval(approval_id)
        if approval.status != ApprovalStatus.GRANTED:
            raise ApprovalRequired(f"approval is {approval.status.value.lower()}")
        return approval
