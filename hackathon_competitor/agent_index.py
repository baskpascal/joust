from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import UUID

from .approvals import ExternalActionService
from .metrics import JsonReader, MetricsUnavailable, UrllibJsonReader
from .models import (
    AgentIndexEligibility,
    ApprovalLevel,
    ExternalActionKind,
    ExternalActionRisk,
    ObservedExternalResult,
    ProposedExternalAction,
)
from .storage import Database
from .tool_gateway import LocalShellTool

# The public page stores exactly these publisher-settable fields. Anything the
# server drops is reported back rather than assumed stored.
METADATA_FIELDS = ("name", "blurb", "repo", "runtime", "install_url")

DEFAULT_INDEX_API = "https://agent-index-server.vercel.app"
DEFAULT_CLIENT_PATH = "/opt/plow/agent-index-client.py"


class AgentIndexError(RuntimeError):
    pass


class VerificationDelivery(Protocol):
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


def _blessed(record: dict[str, Any]) -> bool:
    # The Index marks verification with a timestamp and uses "" for "not yet".
    # Presence of the key is not the signal; a non-empty value is.
    value = record.get("blessed_at")
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
        verified = _blessed(record)
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
        deliver: VerificationDelivery,
    ) -> dict[str, Any]:
        proposed = self.database.get_external_action(action_id)
        agent_id = proposed.target
        contact_route = proposed.payload.get("contact_route")
        if not isinstance(contact_route, str) or not contact_route.strip():
            raise AgentIndexError("the verification proposal has no contact route")

        def execute(_key: str) -> dict[str, Any]:
            receipt = deliver(agent_id, dict(proposed.payload))
            if not isinstance(receipt, dict) or not str(receipt.get("reference", "")).strip():
                raise AgentIndexError(
                    "verification delivery returned no reference to observe against"
                )
            return receipt

        def observe(result: Any) -> ObservedExternalResult:
            record = self.reader.read(agent_id)
            verified = _blessed(record)
            actual = {
                "agent_id": agent_id,
                "verified": verified,
                "blessed_at": record.get("blessed_at") or None,
                "delivery": result.get("reference") if isinstance(result, dict) else None,
            }
            return ObservedExternalResult(
                actual_state=actual,
                matches_expected=verified,
                pending_external=not verified,
                source_uri=self.reader.public_url(agent_id),
                summary=(
                    f"the Agent Index marks {agent_id} Verified"
                    if verified
                    else (
                        f"the verification request for {agent_id} is delivered; "
                        "the Agent Index has not marked it Verified yet"
                    )
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

