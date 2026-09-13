from datetime import UTC, datetime

from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.competition_intelligence import CompetitionIntelligence
from hackathon_competitor.models import CompetitionRuleStatus, Mission
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import Database


def setup_intelligence(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Plow", objective="win", workspace_path=str(tmp_path))
    database.save_mission(mission)
    return database, mission, CompetitionIntelligence(database)


def test_organizer_announcement_supersedes_rule_and_builds_current_state(tmp_path):
    database, mission, intelligence = setup_intelligence(tmp_path)
    old = intelligence.observe_source(
        mission_id=mission.id,
        source_uri="https://example.test/rules",
        authority="OFFICIAL_RULES",
        raw_text="Top 10 receive human review.",
        observed_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    intelligence.extract(
        old.id,
        [
            {
                "signal_type": "RULE",
                "category": "JUDGING_MODEL",
                "statement": "Top 10 receive human review.",
                "normalized_constraint": "TOP_10_HUMAN_REVIEW",
                "confidence": 1.0,
            }
        ],
        extractor="fixture",
        extractor_version="1",
    )
    first = intelligence.reconcile(mission.id)

    announcement = intelligence.observe_source(
        mission_id=mission.id,
        source_uri="discord://organizer/update-2026-09-13",
        authority="ORGANIZER_ANNOUNCEMENT",
        raw_text="Human review is dropped. Leaderboard rank decides at Sep 23, 1pm PT.",
        observed_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    extraction = intelligence.extract(
        announcement.id,
        [
            {
                "signal_type": "RULE",
                "category": "JUDGING_MODEL",
                "statement": "Leaderboard rank decides; human review is removed.",
                "normalized_constraint": "LEADERBOARD_ONLY",
                "confidence": 1.0,
            },
            {
                "signal_type": "DEADLINE",
                "deadline_type": "FINAL_SNAPSHOT",
                "deadline_at": "2026-09-23T20:00:00Z",
                "confidence": 1.0,
            },
            {
                "signal_type": "LEADERBOARD",
                "agent_id": "galahad-hackathon",
                "rank": 7,
                "users": 31,
                "successful_installs": 24,
                "token_usage": 409299,
                "confidence": 1.0,
            },
        ],
        extractor="organizer-announcement-v1",
        extractor_version="1",
    )
    current = intelligence.reconcile(mission.id)

    rules = database.list_competition_rules(mission.id)
    assert first.version == 1
    assert current.version == 2
    assert rules[0].status == CompetitionRuleStatus.SUPERSEDED
    assert rules[1].status == CompetitionRuleStatus.ACTIVE
    assert rules[1].normalized_constraint == "LEADERBOARD_ONLY"
    assert current.deadlines["FINAL_SNAPSHOT"] == datetime(2026, 9, 23, 20, tzinfo=UTC)
    assert current.leaderboard["galahad-hackathon"]["successful_installs"] == 24
    assert set(extraction.signal_ids).issubset(current.signal_ids)
    signals = database.list_structured_signals(mission.id)
    assert all(signal.source_evidence_id == announcement.evidence_id for signal in signals[1:])
    assert database.get_source_observation(announcement.id).raw_text.startswith("Human review")
    observed = CompetitionObserver(database).collect(
        CompeteLoop(database).create_cycle(mission.id).id,
        now=datetime(2026, 9, 13, tzinfo=UTC),
    )
    assert observed.deadline_at == current.deadlines["FINAL_SNAPSHOT"]
    assert observed.score_signals["leaderboard.galahad-hackathon.rank"] == 7


def test_lower_authority_conflict_does_not_replace_active_rule(tmp_path):
    database, mission, intelligence = setup_intelligence(tmp_path)
    official = intelligence.observe_source(
        mission_id=mission.id,
        source_uri="https://example.test/rules",
        authority="OFFICIAL_RULES",
        raw_text="Agent Index client is required.",
        observed_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    intelligence.extract(
        official.id,
        [
            {
                "signal_type": "RULE",
                "category": "MANDATORY_INTEGRATION",
                "statement": "Every entry must use Agent Index client.",
                "normalized_constraint": "AGENT_INDEX_REQUIRED",
                "confidence": 1.0,
            }
        ],
        extractor="fixture",
        extractor_version="1",
    )
    intelligence.reconcile(mission.id)
    rumor = intelligence.observe_source(
        mission_id=mission.id,
        source_uri="https://forum.test/post",
        authority="THIRD_PARTY",
        raw_text="The client is optional.",
        observed_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    intelligence.extract(
        rumor.id,
        [
            {
                "signal_type": "RULE",
                "category": "MANDATORY_INTEGRATION",
                "statement": "Agent Index client is optional.",
                "normalized_constraint": "AGENT_INDEX_OPTIONAL",
                "confidence": 0.3,
            }
        ],
        extractor="fixture",
        extractor_version="1",
    )

    state = intelligence.reconcile(mission.id)

    rules = database.list_competition_rules(mission.id)
    assert [rule.status for rule in rules] == [
        CompetitionRuleStatus.ACTIVE,
        CompetitionRuleStatus.CONFLICTED,
    ]
    assert state.active_rule_ids == [rules[0].id]
    assert state.conflicts == ["MANDATORY_INTEGRATION: Agent Index client is optional."]


def test_reconciliation_prefers_authority_then_recency_for_metrics(tmp_path):
    _, mission, intelligence = setup_intelligence(tmp_path)
    for uri, authority, observed_at, value in [
        ("https://third.test", "THIRD_PARTY", datetime(2026, 9, 13, tzinfo=UTC), 99),
        ("https://official.test", "PLATFORM_METADATA", datetime(2026, 9, 12, tzinfo=UTC), 31),
    ]:
        source = intelligence.observe_source(
            mission_id=mission.id,
            source_uri=uri,
            authority=authority,
            raw_text=f"Users: {value}",
            observed_at=observed_at,
        )
        intelligence.extract(
            source.id,
            [
                {
                    "signal_type": "METRIC",
                    "metric": "users",
                    "value": value,
                    "unit": "count",
                    "confidence": 0.9,
                }
            ],
            extractor="fixture",
            extractor_version="1",
        )

    state = intelligence.reconcile(mission.id)

    assert state.metrics["users"] == 31
