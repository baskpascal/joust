from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from .llm import LLMClient


class StructuredOutputError(ValueError):
    pass


def _validate(value: Any, model: type[BaseModel]) -> BaseModel:
    if isinstance(value, model):
        return value
    if isinstance(value, str):
        return model.model_validate_json(value)
    return model.model_validate(value)


class StructuredLLMRunner:
    def __init__(self, client: LLMClient):
        self.client = client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_model: type[BaseModel],
        reasoning_depth: int,
        metadata: dict[str, Any] | None = None,
    ) -> BaseModel:
        raw = await self.client.complete(
            messages,
            response_model=response_model,
            reasoning_depth=reasoning_depth,
            metadata=metadata,
        )
        try:
            return _validate(raw, response_model)
        except (ValidationError, json.JSONDecodeError, ValueError) as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": str(raw)},
                {
                    "role": "user",
                    "content": (
                        "Repair the prior output so it is valid JSON for this schema. "
                        f"Return JSON only. Validation error: {first_error}. "
                        f"Schema: {response_model.model_json_schema()}"
                    ),
                },
            ]
            repaired = await self.client.complete(
                repair_messages,
                response_model=response_model,
                reasoning_depth=reasoning_depth,
                metadata={**(metadata or {}), "repair": True},
            )
            try:
                return _validate(repaired, response_model)
            except (ValidationError, json.JSONDecodeError, ValueError) as second_error:
                raise StructuredOutputError(
                    f"structured output invalid after one repair: {second_error}"
                ) from second_error


async def independent_passes(
    clients: list[LLMClient],
    messages: list[dict[str, Any]],
    *,
    response_model: type[BaseModel],
    reasoning_depth: int,
) -> list[BaseModel]:
    if len(clients) < 2:
        raise ValueError("independent passes require at least two calls")
    return await asyncio.gather(
        *[
            StructuredLLMRunner(client).complete(
                list(messages),
                response_model=response_model,
                reasoning_depth=reasoning_depth,
                metadata={"independent_pass": index},
            )
            for index, client in enumerate(clients)
        ]
    )
