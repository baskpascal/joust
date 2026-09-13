from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from .competition_intelligence import CompetitionIntelligence
from .models import PlowMetricsSnapshot, utcnow


class MetricsUnavailable(RuntimeError):
    pass


class CompetitionMetricsReader(Protocol):
    def snapshot(self) -> PlowMetricsSnapshot: ...


class JsonReader(Protocol):
    def get(self, url: str, *, timeout: float) -> dict[str, Any]: ...


class UrllibJsonReader:
    def get(self, url: str, *, timeout: float) -> dict[str, Any]:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "Joust/0.1"})
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise MetricsUnavailable(f"Agent Index returned HTTP {response.status}")
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise MetricsUnavailable("Agent Index response exceeded 2000000 bytes")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MetricsUnavailable("Agent Index returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MetricsUnavailable("Agent Index response must be a JSON object")
        return payload


class PlowMetricsReader:
    """Read the structured API used by the public Agent Index page."""

    def __init__(
        self,
        agent_id: str,
        *,
        base_url: str = "https://agent-index-server.vercel.app",
        http: JsonReader | None = None,
        timeout: float = 20.0,
        clock=utcnow,
    ):
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.http = http or UrllibJsonReader()
        self.timeout = timeout
        self.clock = clock
        self.raw_sources: dict[str, dict[str, Any]] = {}

    def _get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        try:
            payload = self.http.get(url, timeout=self.timeout)
        except MetricsUnavailable:
            raise
        except (OSError, TimeoutError, ValueError) as exc:
            raise MetricsUnavailable(f"Agent Index request failed: {type(exc).__name__}") from exc
        self.raw_sources[url] = payload
        return payload

    def snapshot(self) -> PlowMetricsSnapshot:
        self.raw_sources = {}
        board = self._get("/v1/agents")
        detail = self._get("/v1/agent", {"agent_id": self.agent_id})
        usage = self._get("/v1/usage", {"agent_id": self.agent_id})
        agents = board.get("agents")
        if not isinstance(agents, list):
            raise MetricsUnavailable("Agent Index leaderboard has no agents list")
        target = next(
            (
                item
                for item in agents
                if isinstance(item, dict) and item.get("agent_id") == self.agent_id
            ),
            None,
        )
        if target is None:
            raise MetricsUnavailable(f"agent is absent from Agent Index: {self.agent_id}")
        if detail.get("agent_id") != self.agent_id or usage.get("agent_id") != self.agent_id:
            raise MetricsUnavailable("Agent Index endpoints returned mismatched agent identity")

        verified = bool(target.get("blessed_at"))
        eligible = [item for item in agents if isinstance(item, dict) and item.get("blessed_at")]
        rank = (
            next(
                (
                    index
                    for index, item in enumerate(eligible, start=1)
                    if item.get("agent_id") == self.agent_id
                ),
                None,
            )
            if verified
            else None
        )
        installs = detail.get("installs")
        successful_installs = installs.get("succeeded") if isinstance(installs, dict) else None
        daily = usage.get("daily")
        if not isinstance(daily, list):
            raise MetricsUnavailable("Agent Index usage response has no daily list")
        token_usage = 0
        active_days = 0
        for day in daily:
            if not isinstance(day, dict) or not isinstance(day.get("models"), list):
                raise MetricsUnavailable("Agent Index daily usage has an invalid shape")
            day_total = 0
            for model in day["models"]:
                if not isinstance(model, dict):
                    raise MetricsUnavailable("Agent Index model usage has an invalid shape")
                for field in ("input", "output", "cache_read", "cache_write"):
                    value = model.get(field, 0)
                    if not isinstance(value, int) or value < 0:
                        raise MetricsUnavailable(f"invalid token counter: {field}")
                    day_total += value
            token_usage += day_total
            if day_total > 0:
                active_days += 1
        users = target.get("users")
        if users is not None and (not isinstance(users, int) or users < 0):
            raise MetricsUnavailable("invalid Agent Index users count")
        if successful_installs is not None and (
            not isinstance(successful_installs, int) or successful_installs < 0
        ):
            raise MetricsUnavailable("invalid successful installs count")
        return PlowMetricsSnapshot(
            agent_id=self.agent_id,
            rank=rank,
            users=users,
            successful_installs=successful_installs,
            token_usage=token_usage,
            active_days=active_days,
            verified=verified,
            captured_at=self.clock(),
        )


class PlowMetricsIngestor:
    def __init__(
        self,
        intelligence: CompetitionIntelligence,
        reader: PlowMetricsReader | None = None,
    ):
        self.intelligence = intelligence
        self.reader = reader

    def ingest(self, mission_id: UUID, reader: PlowMetricsReader | None = None):
        reader = reader or self.reader
        if reader is None:
            raise ValueError("Plow metrics ingestion requires a reader")
        snapshot = reader.snapshot()
        raw = json.dumps(
            {"sources": reader.raw_sources, "snapshot": snapshot.model_dump(mode="json")},
            sort_keys=True,
        )
        observation = self.intelligence.observe_source(
            mission_id=mission_id,
            source_uri=f"{reader.base_url}/v1/agents",
            authority="PLATFORM_METADATA",
            raw_text=raw,
            observed_at=snapshot.captured_at,
        )
        signal_payloads: list[dict[str, Any]] = [
            {
                "signal_type": "LEADERBOARD",
                "agent_id": snapshot.agent_id,
                "rank": snapshot.rank,
                "users": snapshot.users,
                "successful_installs": snapshot.successful_installs,
                "token_usage": snapshot.token_usage,
                "confidence": 1.0,
            }
        ]
        for metric, value in (
            ("users", snapshot.users),
            ("successful_installs", snapshot.successful_installs),
            ("token_usage", snapshot.token_usage),
            ("active_days", snapshot.active_days),
            ("verified", float(snapshot.verified)),
        ):
            if value is not None:
                signal_payloads.append(
                    {
                        "signal_type": "METRIC",
                        "metric": metric,
                        "value": value,
                        "unit": "boolean" if metric == "verified" else "count",
                        "confidence": 1.0,
                    }
                )
        self.intelligence.extract(
            observation.id,
            signal_payloads,
            extractor="plow-agent-index-structured-api",
            extractor_version="1",
        )
        return self.intelligence.reconcile(mission_id), snapshot
