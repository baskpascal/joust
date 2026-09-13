from datetime import UTC, datetime

from hackathon_competitor.competition_rules import CompetitionRuleService
from hackathon_competitor.models import (
    CompetitionRule,
    CompetitionRuleStatus,
    CompetitionSpec,
    CompetitionType,
    EntrantProfile,
    Mission,
    MissionStatus,
)
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.storage import Database


def test_joust_contracts_extend_existing_missions_compatibly(tmp_path):
    mission = Mission.model_validate(
        {
            "title": "legacy mission",
            "objective": "compete",
            "workspace_path": str(tmp_path),
        }
    )
    spec = CompetitionSpec(
        mission_id=mission.id,
        name="Usage contest",
        competition_type=CompetitionType.AGENT_USAGE,
        final_snapshot_at=datetime(2026, 9, 23, 20, 0, tzinfo=UTC),
        leaderboard_model="installs plus token usage",
        mandatory_integrations=["Agent Index client"],
    )
    assert mission.status == MissionStatus.ACTIVE
    assert spec.competition_type == CompetitionType.AGENT_USAGE
    assert spec.final_snapshot_at is not None


def test_entrant_profile_is_persisted_attached_and_exported(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = app.create_mission(
        title="Joust mission",
        objective="compete",
        source_inputs=["brief"],
        workspace_path=str(tmp_path / "workspace"),
    )
    profile = EntrantProfile(
        display_name="Lucas",
        discord_identity="p_ascal",
        github_identity="baskpascal",
    )

    app.attach_entrant_profile(mission.id, profile)

    loaded = database.get_mission(mission.id)
    assert loaded.entrant_profile_id == profile.id
    exported = database.export_mission(mission.id)
    assert exported["entrant_profile"]["discord_identity"] == "p_ascal"


def test_critical_rule_supersession_triggers_strategy_reassessment(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Rules", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    rules = CompetitionRuleService(database)
    prior = rules.record(
        CompetitionRule(
            mission_id=mission.id,
            category="scoring",
            statement="Top ten receive human review.",
            normalized_constraint="top_10_human_review=true",
            authority="official rules",
            confidence=0.95,
        )
    )
    current = rules.record(
        CompetitionRule(
            mission_id=mission.id,
            category="scoring",
            statement="Leaderboard rank decides; human review is removed.",
            normalized_constraint="leaderboard_rank_decides=true",
            authority="new organizer announcement",
            confidence=1.0,
            supersedes_rule_id=prior.id,
        )
    )

    stored = database.list_competition_rules(mission.id)
    assert stored[0].status == CompetitionRuleStatus.SUPERSEDED
    assert stored[1].status == CompetitionRuleStatus.ACTIVE
    assert current.supersedes_rule_id == prior.id
    assert any(
        event["event_type"] == "STRATEGY_REASSESSMENT_REQUIRED"
        for event in database.events(mission.id)
    )
