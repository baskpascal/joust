from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_model: type[BaseModel] | None = None,
        reasoning_depth: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Any: ...
