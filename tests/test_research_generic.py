from pathlib import Path
from uuid import uuid4

from hackathon_competitor.capabilities.research import (
    discover_sources,
    extract_spec,
    parse_source,
)
from hackathon_competitor.models import MissionState
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import mission_status, run_vertical_slice
from hackathon_competitor.storage import Database

FIXTURE = Path(__file__).parent / "fixtures/generic_hackathon/index.html"
AGENT_INDEX_FIXTURE = Path(__file__).parent / "fixtures/agent_index_realistic.html"


def test_generic_rules_page_is_discovered_and_conservatively_extracted():
    sources = discover_sources(str(FIXTURE))
    assert len(sources) == 2
    spec, evidence, contradictions = extract_spec(uuid4(), sources)
    assert spec.name == "Open Agents Challenge"
    assert (
        "Teams must use Python 3.11 or newer in the submitted agent." in spec.required_technologies
    )
    assert any("public repository" in item.text for item in spec.submission_requirements)
    assert any("fabricate users" in item for item in spec.prohibited_actions)
    assert contradictions == []
    assert all("upload every credential" not in item.claim for item in evidence)


def test_realistic_agent_index_copy_yields_rules_without_story_false_positive():
    source = parse_source(
        AGENT_INDEX_FIXTURE.read_text(encoding="utf-8"),
        "https://aiworthusing.com/agent-index",
        "official",
        "official_page",
    )

    assert len(source.rules) >= 3
    assert any(
        rule["kind"] == "eligibility" and "verified" in rule["text"]
        for rule in source.rules
    )
    assert any(
        rule["kind"] == "submission" and "Register" in rule["text"]
        for rule in source.rules
    )
    assert any(
        rule["kind"] == "required-technology" and "agent-index" in rule["text"]
        for rule in source.rules
    )
    assert all("routing and account" not in rule["text"] for rule in source.rules)

    spec, evidence, contradictions = extract_spec(uuid4(), [source])
    assert spec.rules_locked
    assert len(evidence) >= 3
    assert contradictions == []


def test_incomplete_real_page_returns_inspectable_blocked_mission(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")

    mission = run_vertical_slice(
        app,
        str(AGENT_INDEX_FIXTURE),
        workspace_path=str(tmp_path / "workspace"),
    )
    status = mission_status(app, mission)

    assert mission.state == MissionState.BLOCKED
    assert status["deadline"] is None
    assert status["quality_blockers"] == ["critical prohibitions are missing"]
    assert status["next_ready_tasks"] == []
