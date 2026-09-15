"""A live Plow Chat incident, turned into regression tests.

Joust proposed `cat /var/lib/hermes/.env`, `env | grep ...`, and
`find /etc/ssl ...` while diagnosing an unreachable competition URL. The
user's `/deny` was answered "No pending command to deny," and the agent kept
going. Every test name here is the property that incident violated.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from hackathon_competitor.capabilities.network_diagnostics import diagnose
from hackathon_competitor.command_approval import (
    CategoryBlocked,
    CommandApprovalService,
    CommandNotFound,
    CommandNotGranted,
    CommandNotPending,
)
from hackathon_competitor.models import ApprovalStatus, Mission
from hackathon_competitor.security_policy import ForbiddenCommand, classify_command
from hackathon_competitor.storage import Database


def _service(tmp_path) -> tuple[CommandApprovalService, object]:
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    return CommandApprovalService(database), mission


def test_network_failure_must_not_trigger_secret_inspection(tmp_path):
    """The actual live commands must be classified forbidden, and the safe
    network diagnostic must be able to answer the same underlying question
    (why is this host unreachable) without ever reading a secret."""

    for dangerous in (
        "cat /var/lib/hermes/.env",
        "env | grep TOKEN",
        "find /etc/ssl -name '*.key'",
        "cat ~/.ssh/id_rsa",
        "printenv | grep -i secret",
    ):
        verdict = classify_command(dangerous)
        assert verdict.allowed is False, f"{dangerous!r} must be forbidden"

    # The safe path answers the real question instead.
    result = diagnose("this-host-genuinely-does-not-exist.invalid")
    assert result.dns_resolved is False
    assert "secret" not in result.to_evidence_text().lower()
    assert "token" not in result.to_evidence_text().lower()


def test_denied_approval_must_not_execute(tmp_path):
    service, mission = _service(tmp_path)
    proposed = service.propose(mission.id, "curl -sI https://example.com", "Check reachability")
    service.deny(proposed.id)

    executed = []
    with pytest.raises(CommandNotGranted):
        service.execute_if_granted(proposed.id, lambda: executed.append(True))
    assert executed == []


def test_approval_request_must_remain_durable_until_resolved(tmp_path):
    """A fresh service instance (a new process, a new chat turn) must still
    find the same PENDING request — durability, not in-memory session state."""

    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    first_service = CommandApprovalService(database)
    proposed = first_service.propose(
        mission.id, "curl -sI https://example.com", "Check reachability"
    )

    second_service = CommandApprovalService(database)
    reread = second_service.get(proposed.id)
    assert reread.status == ApprovalStatus.PENDING
    assert reread.id == proposed.id

    denied = second_service.deny(proposed.id)
    assert denied.status == ApprovalStatus.DENIED
    assert first_service.get(proposed.id).status == ApprovalStatus.DENIED


def test_no_pending_command_race(tmp_path):
    """The exact incident: a user's /deny must never answer "no pending
    command" for a request that genuinely exists and is genuinely pending.
    A denial that names a request that truly does not exist, or that was
    already resolved, must say which — never a generic, ambiguous failure
    a caller could mistake for "nothing to do here"."""

    service, mission = _service(tmp_path)
    proposed = service.propose(mission.id, "curl -sI https://example.com", "Check reachability")

    # The request that exists and is pending must be denyable.
    denied = service.deny(proposed.id)
    assert denied.status == ApprovalStatus.DENIED

    # A denial naming a request that never existed is a distinct, named
    # failure (CommandNotFound) — not a silent "no pending command" the
    # caller could confuse with "already handled."
    with pytest.raises(CommandNotFound):
        service.deny(uuid4())

    # A request that expired before anyone decided is a distinct, named
    # failure too (CommandNotPending, with the EXPIRED status attached) —
    # not the same ambiguous message as "does not exist".
    expiring = service.propose(
        mission.id, "curl -sI https://example.com", "Check reachability", ttl_seconds=0
    )
    time.sleep(0.01)
    with pytest.raises(CommandNotPending) as excinfo:
        service.grant(expiring.id)
    assert excinfo.value.status == ApprovalStatus.EXPIRED

    # Denying an already-denied request is idempotent, not an error: a
    # second /deny must never look like a failure to the user who sent it.
    again = service.deny(proposed.id)
    assert again.status == ApprovalStatus.DENIED


def test_denial_must_block_equivalent_fallback_action(tmp_path):
    """Once a category has been denied, proposing "the same underlying
    diagnostic, attempted a different way" in that category must be
    refused before it ever becomes a new approval request — a denial is
    authoritative, not a suggestion the agent can route around."""

    service, mission = _service(tmp_path)
    first = service.propose(
        mission.id,
        "cat /var/log/nginx/error.log",
        "Check the reachability logs",
        category="network",
    )
    service.deny(first.id)

    # A fallback attempt in the SAME category — a different command,
    # genuinely reachable and genuinely allowed on its own — must still be
    # refused, because the category was already denied this mission.
    with pytest.raises(CategoryBlocked) as excinfo:
        service.propose_unless_blocked(
            mission.id,
            "curl -sI https://example.com",
            "Try reachability a different way",
            category="network",
        )
    assert excinfo.value.blocking.status == ApprovalStatus.DENIED
    # And nothing new was actually created by the blocked attempt.
    assert len(service.database.list_proposed_commands(mission.id)) == 1

    # A DIFFERENT category is unaffected — the block is scoped, not global.
    unrelated = service.propose_unless_blocked(
        mission.id, "curl -sI https://example.com", "Check a different thing", category="build"
    )
    assert unrelated.status == ApprovalStatus.PENDING


def test_forbidden_command_never_becomes_an_approvable_request(tmp_path):
    """Point 1 of the policy: a forbidden command is rejected before
    approval UI exists at all, not shown as something to allow or deny."""

    service, mission = _service(tmp_path)
    with pytest.raises(ForbiddenCommand):
        service.propose(mission.id, "cat /var/lib/hermes/.env", "Read a config file")
    assert service.database.list_proposed_commands(mission.id) == []


def test_expired_request_does_not_silently_continue(tmp_path):
    service, mission = _service(tmp_path)
    proposed = service.propose(
        mission.id, "curl -sI https://example.com", "Check reachability", ttl_seconds=0
    )
    time.sleep(0.01)
    assert service.is_granted(proposed.id) is False
    assert service.was_denied_or_expired(proposed.id) is True
    with pytest.raises(CommandNotGranted):
        service.execute_if_granted(proposed.id, lambda: (_ for _ in ()).throw(AssertionError()))
