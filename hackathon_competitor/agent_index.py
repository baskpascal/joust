from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import UUID

from .approvals import ExternalActionService, ExternalObservationUnavailable
from .metrics import JsonReader, MetricsUnavailable, UrllibJsonReader
from .models import (
    AgentIndexEligibility,
    ApprovalLevel,
    ExternalActionKind,
    ExternalActionRisk,
    ExternalActionStatus,
    ObservedExternalResult,
    ProposedExternalAction,
)
from .storage import Database
from .tool_gateway import LocalShellTool

# The public page stores exactly these publisher-settable fields. Anything the
# server drops is reported back rather than assumed stored.
METADATA_FIELDS = ("name", "blurb", "repo", "runtime", "install_url")

DEFAULT_INDEX_API = "https://agent-index-server.vercel.app"

# Each handoff waits on one public timestamp. Keeping the shape in one table
# means a poll can never observe a different marker than its delivery did.
HANDOFF_MARKERS: dict[ExternalActionKind, dict[str, str]] = {
    ExternalActionKind.VERIFICATION_REQUEST: {
        "marker_field": "blessed_at",
        "state_key": "verified",
        "achieved": "the Agent Index marks {agent} Verified",
        "pending": "the verification request for {agent} is delivered; "
        "the Agent Index has not marked it Verified yet",
    },
    ExternalActionKind.DEPLOY: {
        "marker_field": "deployable_at",
        "state_key": "deployable",
        "achieved": "the Agent Index marks {agent} deployable",
        "pending": "the hosting handoff for {agent} is delivered; "
        "Plow has not enabled hosted deployment yet",
    },
}
DEFAULT_CLIENT_PATH = "/opt/plow/agent-index-client.py"


class AgentIndexError(RuntimeError):
    pass


class HandoffDelivery(Protocol):
    """Delivers a prepared handoff to a third party and returns a reference."""

    def __call__(self, agent_id: str, handoff: dict[str, Any]) -> dict[str, Any]: ...


class AgentIndexClient(Protocol):
    def register(self, agent_id: str, metadata: dict[str, str]) -> dict[str, Any]: ...


class PinnedCliAgentIndexClient:
    """Metadata writes through the pinned upstream Agent Index client."""

    def __init__(
        self,
        *,
        client_path: str | Path = DEFAULT_CLIENT_PATH,
        python_executable: str = "python3",
        workspace: str | Path = "/tmp",
        environment: dict[str, str] | None = None,
    ):
        self.client_path = Path(client_path)
        self.python_executable = python_executable
        self.shell = LocalShellTool(workspace, environment=environment)

    def register(self, agent_id: str, metadata: dict[str, str]) -> dict[str, Any]:
        if not self.client_path.is_file():
            raise AgentIndexError(
                f"the pinned Agent Index client is not installed at {self.client_path}"
            )
        argv = [self.python_executable, str(self.client_path), "--register", "--agent", agent_id]
        for field in METADATA_FIELDS:
            value = metadata.get(field)
            # An absent field means "leave the record alone" upstream, so only
            # fields this action actually decided are sent. "" is a real value:
            # it is how a publisher clears a bad link from a public page.
            if value is not None:
                argv.extend([f"--{field.replace('_', '-')}", value])
        output = self.shell.run(argv, timeout_seconds=120)
        return {"output": output}


class AgentIndexReader:
    """Read-only view of the public Agent Index record."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_INDEX_API,
        http: JsonReader | None = None,
        timeout: float = 20.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.http = http or UrllibJsonReader()
        self.timeout = timeout

    def public_url(self, agent_id: str) -> str:
        return f"{self.base_url}/v1/agent?{urlencode({'agent_id': agent_id})}"

    def read(self, agent_id: str) -> dict[str, Any]:
        url = self.public_url(agent_id)
        try:
            payload = self.http.get(url, timeout=self.timeout)
        except MetricsUnavailable:
            raise
        except (OSError, TimeoutError, ValueError) as exc:
            raise MetricsUnavailable(
                f"Agent Index request failed: {type(exc).__name__}"
            ) from exc
        if not isinstance(payload, dict) or payload.get("agent_id") != agent_id:
            raise MetricsUnavailable("Agent Index returned a record for a different agent")
        return payload


def _marked(record: dict[str, Any], field: str) -> bool:
    # The Index records these states as timestamps and uses "" for "not yet".
    # Presence of the key is not the signal; a non-empty value is.
    value = record.get(field)
    return isinstance(value, str) and bool(value.strip())


class AgentIndexService:
    """Approval-bound metadata updates and verification handoff for the Index."""

    def __init__(
        self,
        database: Database,
        *,
        client: AgentIndexClient,
        reader: AgentIndexReader | None = None,
    ):
        self.database = database
        self.client = client
        self.reader = reader or AgentIndexReader()
        self.external = ExternalActionService(database)

    # -- eligibility ----------------------------------------------------

    def eligibility(
        self,
        agent_id: str,
        *,
        license_spdx: str | None,
        reporting_active_days: int | None,
    ) -> AgentIndexEligibility:
        """Observed eligibility. Every unknown input stays unknown."""

        record = self.reader.read(agent_id)
        license_is_mit = license_spdx == "MIT" if license_spdx is not None else None
        reporting_healthy = (
            reporting_active_days > 0 if reporting_active_days is not None else None
        )
        verified = _marked(record, "blessed_at")
        registered = bool(str(record.get("name", "")).strip())
        blockers: list[str] = []
        if license_is_mit is None:
            blockers.append("license is unobserved")
        elif not license_is_mit:
            blockers.append(f"license is {license_spdx}, not MIT")
        if not registered:
            blockers.append("the agent has no registered Index record")
        if reporting_healthy is None:
            blockers.append("usage reporting is unobserved")
        elif not reporting_healthy:
            blockers.append("usage reporting has no active day")
        if not verified:
            blockers.append("the Agent Index has not marked this agent Verified")
        return AgentIndexEligibility(
            agent_id=agent_id,
            registered=registered,
            license_is_mit=license_is_mit,
            reporting_healthy=reporting_healthy,
            verified=verified,
            eligible_to_win=bool(license_is_mit and registered and reporting_healthy and verified),
            blockers=blockers,
            source_uri=self.reader.public_url(agent_id),
        )

    # -- metadata update ------------------------------------------------

    def request_metadata_update(
        self,
        mission_id: UUID,
        *,
        agent_id: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> ProposedExternalAction:
        unknown = sorted(set(metadata) - set(METADATA_FIELDS))
        if unknown:
            raise AgentIndexError(f"unsupported Agent Index metadata fields: {unknown}")
        if not metadata:
            raise AgentIndexError("an Agent Index update must change at least one field")
        rendered = ", ".join(f"{field}={metadata[field]!r}" for field in sorted(metadata))
        return self.external.propose(
            mission_id,
            kind=ExternalActionKind.AGENT_INDEX_UPDATE,
            target=agent_id,
            description=f"update the public Agent Index page for {agent_id}: {rendered}",
            risk=ExternalActionRisk.ACCOUNT_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={"metadata": dict(metadata)},
            expected_state={"agent_id": agent_id, **metadata},
        )

    def update_metadata(self, action_id: UUID) -> dict[str, Any]:
        proposed = self.database.get_external_action(action_id)
        metadata = proposed.payload.get("metadata")
        if not isinstance(metadata, dict) or not metadata:
            raise AgentIndexError("the Agent Index proposal carries no metadata")
        agent_id = proposed.target

        def execute(_key: str) -> dict[str, Any]:
            return self.client.register(agent_id, metadata)

        def observe(_result: Any) -> ObservedExternalResult:
            record = self.reader.read(agent_id)
            actual = {"agent_id": agent_id}
            mismatched: list[str] = []
            for field, expected in metadata.items():
                stored = record.get(field)
                actual[field] = stored
                if stored != expected:
                    mismatched.append(field)
            return ObservedExternalResult(
                actual_state=actual,
                matches_expected=not mismatched,
                source_uri=self.reader.public_url(agent_id),
                summary=(
                    "the public Agent Index page stores every approved field"
                    if not mismatched
                    else "the Index did not store: " + ", ".join(sorted(mismatched))
                ),
            )

        return self.external.execute(action_id, executor=execute, observer=observe).actual_state

    # -- verification handoff -------------------------------------------

    def request_verification(
        self,
        mission_id: UUID,
        *,
        agent_id: str,
        eligibility: AgentIndexEligibility,
        contact_route: str,
        repository_url: str,
        commit_sha: str,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        """Propose the handoff. Joust never claims it can bless itself."""

        if eligibility.agent_id != agent_id:
            raise AgentIndexError("the eligibility report describes a different agent")
        if eligibility.verified:
            raise AgentIndexError("the agent is already Verified")
        unmet = [
            item
            for item in eligibility.blockers
            if "Verified" not in item
        ]
        if unmet:
            # Asking a human to bless an agent that fails its own published
            # gate wastes the one review the competition gives it.
            raise AgentIndexError(
                "verification cannot be requested while eligibility is unmet: "
                + "; ".join(unmet)
            )
        return self.external.propose(
            mission_id,
            kind=ExternalActionKind.VERIFICATION_REQUEST,
            target=agent_id,
            description=(
                f"deliver the Agent Index verification handoff for {agent_id} via {contact_route}"
            ),
            risk=ExternalActionRisk.ACCOUNT_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={
                "contact_route": contact_route,
                "eligibility": eligibility.model_dump(mode="json"),
                # The durable proposal carries the complete handoff, so an
                # approver reads what will actually be delivered rather than
                # the words "needs verification".
                "handoff": render_handoff(
                    agent_id,
                    eligibility,
                    contact_route=contact_route,
                    repository_url=repository_url,
                    commit_sha=commit_sha,
                ),
            },
            expected_state={"agent_id": agent_id, "verified": True},
        )

    def deliver_verification_request(
        self,
        action_id: UUID,
        *,
        deliver: HandoffDelivery,
    ) -> dict[str, Any]:
        return self._deliver_handoff(
            action_id,
            deliver=deliver,
            **HANDOFF_MARKERS[ExternalActionKind.VERIFICATION_REQUEST],
        )

    # -- hosted deployment handoff --------------------------------------

    def request_hosting_handoff(
        self,
        mission_id: UUID,
        *,
        agent_id: str,
        image_digest: str,
        contact_route: str,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        """Propose hosted deployment. Only Plow can flip `deployable_at`."""

        if not image_digest.strip():
            raise AgentIndexError("a hosting handoff must name the image digest to deploy")
        record = self.reader.read(agent_id)
        if _marked(record, "deployable_at"):
            raise AgentIndexError("the agent is already marked deployable")
        return self.external.propose(
            mission_id,
            kind=ExternalActionKind.DEPLOY,
            target=agent_id,
            description=(
                f"deliver the Plow hosting handoff for {agent_id} "
                f"at {image_digest} via {contact_route}"
            ),
            risk=ExternalActionRisk.PRODUCTION_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={"contact_route": contact_route, "image_digest": image_digest},
            expected_state={"agent_id": agent_id, "deployable": True},
        )

    def deliver_hosting_handoff(
        self,
        action_id: UUID,
        *,
        deliver: HandoffDelivery,
    ) -> dict[str, Any]:
        return self._deliver_handoff(
            action_id,
            deliver=deliver,
            **HANDOFF_MARKERS[ExternalActionKind.DEPLOY],
        )

    def poll_handoff(self, action_id: UUID) -> dict[str, Any]:
        """Re-observe a delivered handoff. It can never re-deliver one.

        The action service treats AWAITING_EXTERNAL as a resumed observation, so
        the executor below is unreachable; it raises rather than returning a
        plausible receipt, because a handoff delivered twice is the one thing
        this path must never do.
        """

        action = self.database.get_external_action(action_id)
        if action.status != ExternalActionStatus.AWAITING_EXTERNAL:
            raise AgentIndexError(
                f"only a delivered handoff can be polled; this one is {action.status.value}"
            )
        marker = HANDOFF_MARKERS.get(action.kind)
        if marker is None:
            raise AgentIndexError(f"{action.kind.value} is not a handoff kind")

        def refuse(_agent_id: str, _handoff: dict[str, Any]) -> dict[str, Any]:
            raise AgentIndexError("polling must never re-deliver a handoff")

        return self._deliver_handoff(action_id, deliver=refuse, **marker)

    def _deliver_handoff(
        self,
        action_id: UUID,
        *,
        deliver: HandoffDelivery,
        marker_field: str,
        state_key: str,
        achieved: str,
        pending: str,
    ) -> dict[str, Any]:
        """Deliver a handoff Joust cannot complete, then observe the marker."""

        proposed = self.database.get_external_action(action_id)
        agent_id = proposed.target
        contact_route = proposed.payload.get("contact_route")
        if not isinstance(contact_route, str) or not contact_route.strip():
            raise AgentIndexError("the handoff proposal has no contact route")

        def execute(_key: str) -> dict[str, Any]:
            receipt = deliver(agent_id, dict(proposed.payload))
            # Without a reference there is nothing to tie the delivery to, and
            # an unreferenced handoff is indistinguishable from none at all.
            if not isinstance(receipt, dict) or not str(receipt.get("reference", "")).strip():
                raise AgentIndexError("handoff delivery returned no reference to observe against")
            return receipt

        def observe(result: Any) -> ObservedExternalResult:
            try:
                record = self.reader.read(agent_id)
            except MetricsUnavailable as exc:
                # Unreadable, not unblessed: keep the action waiting.
                raise ExternalObservationUnavailable(str(exc)) from exc
            done = _marked(record, marker_field)
            actual = {
                "agent_id": agent_id,
                state_key: done,
                marker_field: record.get(marker_field) or None,
                "delivery": result.get("reference") if isinstance(result, dict) else None,
            }
            return ObservedExternalResult(
                actual_state=actual,
                matches_expected=done,
                pending_external=not done,
                source_uri=self.reader.public_url(agent_id),
                summary=(
                    achieved.format(agent=agent_id) if done else pending.format(agent=agent_id)
                ),
            )

        return self.external.execute(action_id, executor=execute, observer=observe).actual_state

    # -- final submission -----------------------------------------------

    def request_final_submission(
        self,
        mission_id: UUID,
        *,
        agent_id: str,
        repository_url: str,
        install_url: str,
        commit_sha: str,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        if not commit_sha.strip():
            raise AgentIndexError("a final submission must name the candidate commit")
        return self.external.propose(
            mission_id,
            kind=ExternalActionKind.FINAL_SUBMISSION,
            target=agent_id,
            description=(
                f"submit {agent_id} at {commit_sha} with repo {repository_url} "
                f"and install {install_url}"
            ),
            risk=ExternalActionRisk.IRREVERSIBLE_SUBMISSION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={
                "metadata": {"repo": repository_url, "install_url": install_url},
                "commit_sha": commit_sha,
            },
            expected_state={
                "agent_id": agent_id,
                "repo": repository_url,
                "install_url": install_url,
            },
        )

    def submit(self, action_id: UUID) -> dict[str, Any]:
        """Publish the entry's public record and observe what the Index kept."""

        proposed = self.database.get_external_action(action_id)
        metadata = proposed.payload.get("metadata")
        commit_sha = proposed.payload.get("commit_sha")
        if not isinstance(metadata, dict) or not metadata:
            raise AgentIndexError("the submission proposal carries no public metadata")
        agent_id = proposed.target

        def execute(_key: str) -> dict[str, Any]:
            return self.client.register(agent_id, metadata)

        def observe(_result: Any) -> ObservedExternalResult:
            record = self.reader.read(agent_id)
            mismatched = [
                field for field, expected in metadata.items() if record.get(field) != expected
            ]
            actual = {
                "agent_id": agent_id,
                **{field: record.get(field) for field in metadata},
                "commit_sha": commit_sha,
                # Publication is not verification and not finalization. The
                # submission is an event in the mission, never its end.
                "verified": _marked(record, "blessed_at"),
            }
            return ObservedExternalResult(
                actual_state=actual,
                matches_expected=not mismatched,
                source_uri=self.reader.public_url(agent_id),
                summary=(
                    f"the public record for {agent_id} carries the submitted repo and install URL"
                    if not mismatched
                    else "the Index did not store: " + ", ".join(sorted(mismatched))
                ),
            )

        return self.external.execute(action_id, executor=execute, observer=observe).actual_state


def observe_license_spdx(repository_root: Path) -> str | None:
    """Read the SPDX id off the repository's own LICENSE, or stay unknown."""

    license_path = Path(repository_root) / "LICENSE"
    try:
        first_line = license_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    return "MIT" if first_line == "MIT License" else first_line or None


def render_handoff(
    agent_id: str,
    eligibility: AgentIndexEligibility,
    *,
    contact_route: str,
    repository_url: str,
    commit_sha: str,
) -> str:
    """The complete external handoff from SDD section 47, not 'needs verification'."""

    lines = [
        "EXTERNAL ACTION REQUIRED",
        "",
        "Provider:",
        "Plow / Agent Index",
        "",
        "Action:",
        f"Mark agent {agent_id} Verified on the Agent Index.",
        "",
        "Prepared and observed:",
        f"  repository: {repository_url}",
        f"  commit: {commit_sha}",
        f"  license MIT: {eligibility.license_is_mit}",
        f"  registered: {eligibility.registered}",
        f"  reporting healthy: {eligibility.reporting_healthy}",
        f"  public record: {eligibility.source_uri}",
        "",
        "Remaining blockers:",
    ]
    lines.extend(f"  - {item}" for item in eligibility.blockers or ["none"])
    lines.extend(["", "Contact:", f"  {contact_route}"])
    return "\n".join(lines)

