from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from .models import (
    Approval,
    ApprovalLevel,
    ApprovalStatus,
    Evidence,
    ExternalActionKind,
    ExternalActionObservation,
    ExternalActionRisk,
    ExternalActionStatus,
    ObservedExternalResult,
    ProposedExternalAction,
    utcnow,
)
from .storage import Database


class ApprovalRequired(PermissionError):
    pass


class ExternalActionVerificationError(RuntimeError):
    pass


class ExternalActionService:
    """Persist, authorize, execute, observe, and verify every remote mutation."""

    def __init__(self, database: Database):
        self.database = database
        self.approvals = ApprovalService(database)

    def propose(
        self,
        mission_id: UUID,
        *,
        kind: ExternalActionKind,
        target: str,
        description: str,
        risk: ExternalActionRisk,
        approval_level: ApprovalLevel,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        expected_state: dict[str, Any] | None = None,
    ) -> ProposedExternalAction:
        key = idempotency_key.strip()
        if approval_level == ApprovalLevel.AUTO:
            raise ApprovalRequired("external actions cannot use AUTO approval")
        if not key:
            raise ValueError("external action requires an idempotency key")
        proposed_payload = payload or {}
        proposed_expected = expected_state or {}
        prior = self.database.get_external_action_by_idempotency_key(key)
        if prior is not None:
            same_intent = (
                prior.mission_id == mission_id
                and prior.kind == kind
                and prior.target == target
                and prior.description == description
                and prior.risk == risk
                and prior.approval_level == approval_level
                and prior.payload == proposed_payload
                and prior.expected_state == proposed_expected
            )
            if not same_intent:
                raise ApprovalRequired("idempotency key is already bound to another action")
            return prior
        approval = self.approvals.request(mission_id, description, approval_level)
        action = ProposedExternalAction(
            mission_id=mission_id,
            kind=kind,
            target=target,
            description=description,
            risk=risk,
            approval_level=approval_level,
            idempotency_key=key,
            payload=proposed_payload,
            expected_state=proposed_expected,
            approval_id=approval.id,
        )
        self.database.save_external_action(action)
        self.database.append_event(
            mission_id,
            "EXTERNAL_ACTION_PROPOSED",
            {
                "action_id": str(action.id),
                "approval_id": str(approval.id),
                "kind": kind.value,
                "target": target,
                "risk": risk.value,
                "idempotency_key": key,
            },
        )
        return action

    def execute(
        self,
        action_id: UUID,
        *,
        executor: Callable[[str], Any],
        observer: Callable[[Any], ObservedExternalResult],
    ) -> ExternalActionObservation:
        action = self.database.get_external_action(action_id)
        observations = self.database.list_external_action_observations(action.id)
        verified = [item for item in observations if item.matches_expected]
        if verified:
            return verified[-1]

        approval = self.database.get_approval(action.approval_id)
        if approval.status in {ApprovalStatus.DENIED, ApprovalStatus.EXPIRED}:
            action.status = ExternalActionStatus.DENIED
            action.updated_at = utcnow()
            self.database.save_external_action(action)
        self.approvals.require_granted(action.approval_id)

        resume_observation = action.execution_result is not None and action.status in {
            ExternalActionStatus.EXECUTED,
            ExternalActionStatus.FAILED,
        }
        try:
            if resume_observation:
                result: Any = action.execution_result
                self.database.append_event(
                    action.mission_id,
                    "EXTERNAL_ACTION_OBSERVATION_RESUMED",
                    {"action_id": str(action.id)},
                )
            else:
                previous_status = action.status
                action.status = ExternalActionStatus.APPROVED
                action.updated_at = utcnow()
                self.database.save_external_action(action)
                if previous_status == ExternalActionStatus.EXECUTING:
                    action.last_error = "previous execution was interrupted before observation"
                action.status = ExternalActionStatus.EXECUTING
                action.updated_at = utcnow()
                self.database.save_external_action(action)
                self.database.append_event(
                    action.mission_id,
                    "EXTERNAL_ACTION_EXECUTING",
                    {
                        "action_id": str(action.id),
                        "approval_id": str(approval.id),
                        "kind": action.kind.value,
                        "idempotency_key": action.idempotency_key,
                    },
                )
                result = executor(action.idempotency_key)
                action.execution_result = (
                    result if isinstance(result, dict) else {"result": str(result)}
                )
                action.status = ExternalActionStatus.EXECUTED
                action.last_error = None
                action.updated_at = utcnow()
                self.database.save_external_action(action)
            observed = observer(result)
        except BaseException as exc:
            action.status = ExternalActionStatus.FAILED
            action.last_error = str(exc) or type(exc).__name__
            action.updated_at = utcnow()
            self.database.save_external_action(action)
            self.database.append_event(
                action.mission_id,
                "EXTERNAL_ACTION_FAILED",
                {"action_id": str(action.id), "error": action.last_error},
            )
            raise

        evidence = Evidence(
            mission_id=action.mission_id,
            claim=(
                f"External action {action.kind.value} observed and verified"
                if observed.matches_expected
                else f"External action {action.kind.value} remote state did not match"
            ),
            source_type="external_action_observation",
            source_uri=observed.source_uri,
            excerpt=json.dumps(observed.actual_state, sort_keys=True),
            confidence=1.0,
            authority="remote-observation",
            retrieved_at=observed.observed_at,
        )
        self.database.save_evidence(evidence)
        observation = ExternalActionObservation(
            mission_id=action.mission_id,
            action_id=action.id,
            evidence_id=evidence.id,
            **observed.model_dump(),
        )
        self.database.save_external_action_observation(observation)
        action.status = (
            ExternalActionStatus.VERIFIED
            if observed.matches_expected
            else ExternalActionStatus.FAILED
        )
        action.last_error = None if observed.matches_expected else observed.summary
        action.updated_at = utcnow()
        self.database.save_external_action(action)
        self.database.append_event(
            action.mission_id,
            "EXTERNAL_ACTION_VERIFIED" if observed.matches_expected else "EXTERNAL_ACTION_MISMATCH",
            {
                "action_id": str(action.id),
                "evidence_id": str(evidence.id),
                "summary": observed.summary,
            },
        )
        if not observed.matches_expected:
            raise ExternalActionVerificationError(observed.summary)
        return observation


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
