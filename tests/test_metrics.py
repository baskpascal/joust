from datetime import UTC, datetime

import pytest

from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.competition_intelligence import CompetitionIntelligence
from hackathon_competitor.metrics import MetricsUnavailable, PlowMetricsIngestor, PlowMetricsReader
from hackathon_competitor.models import Mission
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import Database


class FakeHttp:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append((url, timeout))
        return self.responses[url]


def payloads(base="https://index.test"):
    return {
        f"{base}/v1/agents": {
            "agents": [
                {"agent_id": "winner", "users": 5, "blessed_at": "2026-09-14T00:00:00Z"},
                {"agent_id": "galahad-hackathon", "users": 1, "blessed_at": ""},
            ]
        },
        f"{base}/v1/agent?agent_id=galahad-hackathon": {
            "agent_id": "galahad-hackathon",
            "installs": {"attempted": 3, "succeeded": 0, "rate": 0},
        },
        f"{base}/v1/usage?agent_id=galahad-hackathon": {
            "agent_id": "galahad-hackathon",
            "daily": [
                {
                    "date": "2026-09-12",
                    "models": [
                        {
                            "model": "claude",
                            "input": 10,
                            "output": 20,
                            "cache_read": 30,
                            "cache_write": 40,
                        }
                    ],
                },
                {"date": "2026-09-13", "models": []},
            ],
            "users": [{"tokens": 100}],
        },
    }


def test_metrics_reader_uses_structured_endpoints_and_preserves_unverified_rank():
    def clock():
        return datetime(2026, 9, 13, 20, tzinfo=UTC)

    http = FakeHttp(payloads())
    snapshot = PlowMetricsReader(
        "galahad-hackathon", base_url="https://index.test", http=http, clock=clock
    ).snapshot()

    assert snapshot.rank is None
    assert snapshot.users == 1
    assert snapshot.successful_installs == 0
    assert snapshot.token_usage == 100
    assert snapshot.active_days == 1
    assert snapshot.verified is False
    assert len(http.calls) == 3


def test_metrics_reader_computes_rank_only_among_verified_agents():
    responses = payloads()
    responses["https://index.test/v1/agents"]["agents"][1]["blessed_at"] = "2026-09-14T01:00:00Z"
    snapshot = PlowMetricsReader(
        "galahad-hackathon", base_url="https://index.test", http=FakeHttp(responses)
    ).snapshot()

    assert snapshot.verified is True
    assert snapshot.rank == 2


def test_metrics_ingestion_links_raw_api_payload_to_current_state(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="win", workspace_path=str(tmp_path))
    database.save_mission(mission)
    intelligence = CompetitionIntelligence(database)
    reader = PlowMetricsReader(
        "galahad-hackathon",
        base_url="https://index.test",
        http=FakeHttp(payloads()),
        clock=lambda: datetime(2026, 9, 13, 20, tzinfo=UTC),
    )

    state, snapshot = PlowMetricsIngestor(intelligence).ingest(mission.id, reader)

    assert state.metrics["token_usage"] == 100
    assert state.metrics["successful_installs"] == 0
    assert state.leaderboard[snapshot.agent_id]["rank"] is None
    signals = database.list_structured_signals(mission.id)
    observation = database.list_source_observations(mission.id)[0]
    assert all(signal.source_evidence_id == observation.evidence_id for signal in signals)
    assert "v1/usage?agent_id=galahad-hackathon" in observation.raw_text


def test_observer_ingests_metrics_before_capturing_score_signals(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Joust", objective="win", workspace_path=str(tmp_path))
    database.save_mission(mission)
    reader = PlowMetricsReader(
        "galahad-hackathon",
        base_url="https://index.test",
        http=FakeHttp(payloads()),
        clock=lambda: datetime(2026, 9, 13, 20, tzinfo=UTC),
    )
    ingestor = PlowMetricsIngestor(CompetitionIntelligence(database), reader)
    cycle = CompeteLoop(database).create_cycle(mission.id)

    observation = CompetitionObserver(database, metrics=ingestor).collect(cycle.id)

    assert observation.score_signals["token_usage"] == 100
    assert observation.score_signals["leaderboard.galahad-hackathon.users"] == 1


def test_missing_dynamic_usage_is_failure_not_zero():
    responses = payloads()
    responses["https://index.test/v1/usage?agent_id=galahad-hackathon"] = {
        "agent_id": "galahad-hackathon"
    }

    with pytest.raises(MetricsUnavailable, match="no daily list"):
        PlowMetricsReader(
            "galahad-hackathon", base_url="https://index.test", http=FakeHttp(responses)
        ).snapshot()
