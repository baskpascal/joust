import shutil
from pathlib import Path

from hackathon_competitor.models import MissionState
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import complete_v0, run_vertical_slice
from hackathon_competitor.rule_updates import refresh_official_rules
from hackathon_competitor.storage import Database

FIXTURE = Path(__file__).parent / "fixtures/hackathon"


def test_official_rule_change_versions_spec_stales_descendants_and_blocks(tmp_path):
    fixture = tmp_path / "hackathon"
    shutil.copytree(FIXTURE, fixture)
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(fixture / "official.html"))
    mission = complete_v0(app, mission.id)
    assert mission.state == MissionState.READY_FOR_SUBMISSION

    rules_path = fixture / "rules.html"
    rules_path.write_text(
        rules_path.read_text().replace(
            "Provide an installable public repository.",
            "Provide an installable public repository and an architecture diagram.",
        )
    )
    updated = refresh_official_rules(app, mission.id, str(fixture / "official.html"))

    assert updated.version == 2
    assert database.get_mission(mission.id).state == MissionState.BLOCKED
    stale_kinds = {item.kind for item in database.list_artifacts(mission.id) if item.stale}
    assert {
        "candidate_ideas",
        "prd",
        "architecture",
        "demo_script",
        "pitch",
        "claims_map",
    }.issubset(stale_kinds)
    tasks = database.list_tasks(mission.id)
    assert any(task.type == "review_stale_prd" for task in tasks)
    assert any(
        event["event_type"] == "OFFICIAL_RULES_UPDATED" for event in database.events(mission.id)
    )


def test_unchanged_rule_check_does_not_create_new_version(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(FIXTURE / "official.html"))
    unchanged = refresh_official_rules(app, mission.id, str(FIXTURE / "official.html"))
    assert unchanged.version == 1
    assert database.get_mission(mission.id).state == MissionState.PLANNING
    assert any(
        event["event_type"] == "RULES_CHECKED_NO_CHANGE" for event in database.events(mission.id)
    )
