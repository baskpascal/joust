"""The durable half of "a user must be able to say no and have it stick."

A live incident is what this closes: a user sent `/deny` to a proposed
command and was told "No pending command to deny" while the agent kept
going. Whatever produced that message treated "pending" as transient session
state rather than a durable fact — if the record of a request can be lost or
never was one, a denial has nothing to attach to.

This service makes a command's approval state a row, not a variable: a
durable id, a `PENDING` state a later reader can still find, an explicit
expiry so a stale request cannot be granted or denied as if it were still
live, and a `grant`/`deny` that fail loudly and specifically — never a silent
no-op — when the request they name is not the request they can act on.
Nothing this service governs may execute except through `execute_if_granted`,
so "must not continue until approved" is a property of the code path, not a
convention someone has to remember to follow.

`security_policy.classify_command` runs first, in `propose`: a forbidden
command never becomes a `ProposedCommand` at all, so a user is never shown
something they'd have to recognise as dangerous themselves.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import TypeVar
from uuid import UUID

from .models import ApprovalStatus, ProposedCommand, utcnow
from .security_policy import ForbiddenCommand, classify_command
from .storage import Database

T = TypeVar("T")

DEFAULT_TTL_SECONDS = 300


class CommandApprovalError(RuntimeError):
    pass


class CommandNotFound(CommandApprovalError, LookupError):
    pass


class CommandNotPending(CommandApprovalError):
    """The request exists, but is not in a state a decision can be made on.

    Carries the actual status so a caller — or a chat reply — can say
    something specific ("that request already expired") instead of the
    ambiguous message that caused the live incident this module fixes.
    """

    def __init__(self, command_id: UUID, status: ApprovalStatus):
        self.command_id = command_id
        self.status = status
        super().__init__(f"command {command_id} is {status.value}, not PENDING")


class CommandNotGranted(CommandApprovalError):
    def __init__(self, command_id: UUID, status: ApprovalStatus):
        self.command_id = command_id
        self.status = status
        super().__init__(f"command {command_id} is {status.value}, refusing to execute")


class CategoryBlocked(CommandApprovalError):
    """A denial (or a still-pending request) in this category is authoritative.

    Raised by `propose_unless_blocked` so that "the user said no, try it a
    different way" cannot happen by construction: the second attempt never
    reaches a fresh approval request, let alone execution.
    """

    def __init__(self, category: str, blocking: ProposedCommand):
        self.category = category
        self.blocking = blocking
        super().__init__(
            f"refusing to propose another {category!r} command: an existing request "
            f"in that category is {blocking.status.value} ({blocking.id})"
        )


class CommandApprovalService:
    def __init__(self, database: Database):
        self.database = database

    def propose(
        self,
        mission_id: UUID,
        command: str | Sequence[str],
        intent_summary: str,
        *,
        category: str = "diagnostic",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> ProposedCommand:
        """Classify, then durably record, one command awaiting a decision.

        Raises `ForbiddenCommand` and creates nothing if the command targets
        a secret, a key, or a full environment dump — that class of command
        is never something a user is asked to approve at all.
        """

        verdict = classify_command(command)
        if not verdict.allowed:
            raise ForbiddenCommand(verdict)
        text = command if isinstance(command, str) else " ".join(command)
        proposed = ProposedCommand(
            mission_id=mission_id,
            command=text,
            intent_summary=intent_summary,
            category=category,
            expires_at=utcnow() + timedelta(seconds=ttl_seconds),
        )
        self.database.save_proposed_command(proposed)
        self.database.append_event(
            mission_id,
            "COMMAND_APPROVAL_REQUESTED",
            {
                "command_id": str(proposed.id),
                "intent_summary": intent_summary,
                "category": category,
                "expires_at": proposed.expires_at.isoformat(),
            },
        )
        return proposed

    def get(self, command_id: UUID) -> ProposedCommand:
        """Read current state, resolving a stale PENDING to EXPIRED first.

        Expiry is checked here rather than only at decision time so a
        request that has quietly gone stale is never treated as live by a
        caller who only reads it (`is_granted`, an approval-status display).
        """

        try:
            proposed = self.database.get_proposed_command(command_id)
        except KeyError as error:
            raise CommandNotFound(f"no such command approval request: {command_id}") from error
        if proposed.status == ApprovalStatus.PENDING and utcnow() >= proposed.expires_at:
            proposed.status = ApprovalStatus.EXPIRED
            proposed.decided_at = utcnow()
            proposed.decision_note = "expired without a decision"
            self.database.save_proposed_command(proposed)
            self.database.append_event(
                proposed.mission_id,
                "COMMAND_APPROVAL_EXPIRED",
                {"command_id": str(proposed.id)},
            )
        return proposed

    def grant(self, command_id: UUID, *, note: str | None = None) -> ProposedCommand:
        proposed = self.get(command_id)
        if proposed.status != ApprovalStatus.PENDING:
            raise CommandNotPending(command_id, proposed.status)
        proposed.status = ApprovalStatus.GRANTED
        proposed.decided_at = utcnow()
        proposed.decision_note = note
        self.database.save_proposed_command(proposed)
        self.database.append_event(
            proposed.mission_id, "COMMAND_APPROVAL_GRANTED", {"command_id": str(proposed.id)}
        )
        return proposed

    def deny(self, command_id: UUID, *, note: str | None = None) -> ProposedCommand:
        """Deny a pending request. Denying an already-denied one is a no-op,
        not an error: the user's actual intent — this must not run — is
        already satisfied, and a second `/deny` should never look like a
        failure. Any other non-pending state still raises: granting-then-
        denying, or denying-after-expiry, are decisions on a request that no
        longer has one to make.
        """

        proposed = self.get(command_id)
        if proposed.status == ApprovalStatus.DENIED:
            return proposed
        if proposed.status != ApprovalStatus.PENDING:
            raise CommandNotPending(command_id, proposed.status)
        proposed.status = ApprovalStatus.DENIED
        proposed.decided_at = utcnow()
        proposed.decision_note = note
        self.database.save_proposed_command(proposed)
        self.database.append_event(
            proposed.mission_id, "COMMAND_APPROVAL_DENIED", {"command_id": str(proposed.id)}
        )
        return proposed

    def is_granted(self, command_id: UUID) -> bool:
        return self.get(command_id).status == ApprovalStatus.GRANTED

    def was_denied_or_expired(self, command_id: UUID) -> bool:
        return self.get(command_id).status in {ApprovalStatus.DENIED, ApprovalStatus.EXPIRED}

    def execute_if_granted(self, command_id: UUID, executor: Callable[[], T]) -> T:
        """The only sanctioned way to act on a proposed command.

        A command cannot run through this service except by passing through
        here with a GRANTED status read at the moment of the call — there is
        no code path from `propose` to execution that skips this check.
        """

        proposed = self.get(command_id)
        if proposed.status != ApprovalStatus.GRANTED:
            raise CommandNotGranted(command_id, proposed.status)
        return executor()

    def has_active_or_denied_request(
        self, mission_id: UUID, category: str
    ) -> ProposedCommand | None:
        """Find the most recent still-relevant request in this category.

        Used to enforce that a denial is authoritative: before proposing a
        new command in the same category (a fallback diagnostic reached for
        after a denial), a caller must check this and refuse to route around
        a PENDING or DENIED request the same way `execute_if_granted` refuses
        to route around a decision at execution time.
        """

        candidates = [
            item
            for item in self.database.list_proposed_commands(mission_id)
            if item.category == category
        ]
        if not candidates:
            return None
        latest = candidates[-1]
        latest = self.get(latest.id)  # resolve expiry before reporting it
        if latest.status in {ApprovalStatus.PENDING, ApprovalStatus.DENIED}:
            return latest
        return None

    def propose_unless_blocked(
        self,
        mission_id: UUID,
        command: str | Sequence[str],
        intent_summary: str,
        *,
        category: str = "diagnostic",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> ProposedCommand:
        """`propose`, but refusing outright if this category was already
        denied (or is still pending) this mission. This is the enforced
        form of "user denial is authoritative": a repair loop or a
        diagnosis step that reaches for "the same underlying check, a
        different way" after a denial must call this, not `propose`, so the
        block is a property of the code path rather than something every
        caller has to remember to check.
        """

        blocking = self.has_active_or_denied_request(mission_id, category)
        if blocking is not None:
            raise CategoryBlocked(category, blocking)
        return self.propose(
            mission_id, command, intent_summary, category=category, ttl_seconds=ttl_seconds
        )


def format_approval_prompt(proposed: ProposedCommand) -> str:
    """What a user actually sees: intent, not shell.

    The raw command is available (`proposed.command`) for an optional
    "technical details" disclosure a chat surface can render collapsed —
    it is never the primary text, because a non-technical user should never
    have to read or understand a shell command to decide whether to allow
    something.
    """

    return (
        f"{proposed.intent_summary}\n\n"
        "ALLOW ONCE   CANCEL\n\n"
        f"(technical details: {proposed.command})"
    )


__all__ = [
    "CategoryBlocked",
    "CommandApprovalError",
    "CommandApprovalService",
    "CommandNotFound",
    "CommandNotGranted",
    "CommandNotPending",
    "format_approval_prompt",
]
