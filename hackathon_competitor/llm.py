from __future__ import annotations

import time
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from .storage import Database


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_model: type[BaseModel] | None = None,
        reasoning_depth: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Any: ...


class TelemetryLLMClient:
    """Provider-neutral observability wrapper; it never enforces a token budget."""

    def __init__(
        self,
        client: LLMClient,
        database: Database,
        mission_id: UUID,
        capability: str,
    ):
        self.client = client
        self.database = database
        self.mission_id = mission_id
        self.capability = capability

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_model: type[BaseModel] | None = None,
        reasoning_depth: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        started = time.monotonic()
        result: Any = None
        try:
            result = await self.client.complete(
                messages,
                response_model=response_model,
                reasoning_depth=reasoning_depth,
                metadata=metadata,
            )
        finally:
            self.database.record_metric(self.mission_id, "llm_calls", 1.0)
            self.database.record_metric(
                self.mission_id,
                f"llm_seconds:{self.capability}",
                time.monotonic() - started,
            )
        total_tokens = 0
        if isinstance(result, dict):
            usage = result.get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                total_tokens = usage["total_tokens"]
        if total_tokens:
            self.database.record_metric(self.mission_id, "tokens", float(total_tokens))
            self.database.record_metric(
                self.mission_id, f"tokens:{self.capability}", float(total_tokens)
            )
        return result
