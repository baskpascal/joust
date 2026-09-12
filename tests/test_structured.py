import asyncio

import pytest

from hackathon_competitor.models import MetaJudgeResult
from hackathon_competitor.structured import (
    StructuredLLMRunner,
    StructuredOutputError,
    independent_passes,
)


VALID = {
    "consensus": ["x"],
    "unresolved_disagreement": [],
    "confidence": 0.8,
    "recommended_next_action": "continue",
    "more_evidence_required": False,
}


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.replies.pop(0)


def test_invalid_json_gets_exactly_one_repair():
    client = FakeClient(["not json", VALID])
    result = asyncio.run(
        StructuredLLMRunner(client).complete(
            [{"role": "user", "content": "judge"}],
            response_model=MetaJudgeResult,
            reasoning_depth=5,
        )
    )
    assert result.confidence == 0.8
    assert len(client.calls) == 2
    assert client.calls[1][1]["metadata"]["repair"] is True


def test_second_invalid_result_fails_visibly():
    client = FakeClient(["bad", "still bad"])
    with pytest.raises(StructuredOutputError, match="after one repair"):
        asyncio.run(
            StructuredLLMRunner(client).complete(
                [{"role": "user", "content": "judge"}],
                response_model=MetaJudgeResult,
                reasoning_depth=5,
            )
        )
    assert len(client.calls) == 2


def test_independent_passes_use_isolated_calls():
    clients = [FakeClient([VALID]), FakeClient([VALID])]
    results = asyncio.run(
        independent_passes(
            clients,
            [{"role": "user", "content": "judge"}],
            response_model=MetaJudgeResult,
            reasoning_depth=4,
        )
    )
    assert len(results) == 2
    assert clients[0].calls[0][1]["metadata"]["independent_pass"] == 0
    assert clients[1].calls[0][1]["metadata"]["independent_pass"] == 1
