import asyncio

import pytest

from hackathon_competitor.models import MetaJudgeResult
from hackathon_competitor.llm import TelemetryLLMClient
from hackathon_competitor.models import Mission
from hackathon_competitor.storage import Database
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


class FailingClient:
    async def complete(self, messages, **kwargs):
        raise ConnectionError("provider unavailable")


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


def test_llm_telemetry_records_calls_and_provider_usage_without_budgeting(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    wrapped = TelemetryLLMClient(
        FakeClient([{"value": "ok", "usage": {"total_tokens": 321}}]),
        database,
        mission.id,
        "judge",
    )
    result = asyncio.run(wrapped.complete([{"role": "user", "content": "review"}]))
    assert result["value"] == "ok"
    totals = {}
    for metric in database.metrics(mission.id):
        totals[metric["metric"]] = totals.get(metric["metric"], 0) + metric["value"]
    assert totals["llm_calls"] == 1
    assert totals["tokens"] == 321
    assert totals["tokens:judge"] == 321


def test_llm_telemetry_preserves_provider_failure_and_records_call(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    wrapped = TelemetryLLMClient(FailingClient(), database, mission.id, "research")
    with pytest.raises(ConnectionError, match="provider unavailable"):
        asyncio.run(wrapped.complete([]))
    assert (
        sum(
            metric["value"]
            for metric in database.metrics(mission.id)
            if metric["metric"] == "llm_calls"
        )
        == 1
    )
