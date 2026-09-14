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
        rule["kind"] == "eligibility" and "verified" in rule["text"] for rule in source.rules
    )
    assert any(rule["kind"] == "submission" and "Register" in rule["text"] for rule in source.rules)
    assert any(
        rule["kind"] == "required-technology" and "agent-index" in rule["text"]
        for rule in source.rules
    )
    assert all("routing and account" not in rule["text"] for rule in source.rules)

    spec, evidence, contradictions = extract_spec(uuid4(), [source])
    assert spec.rules_locked
    assert len(evidence) >= 3
    assert contradictions == []


def test_json_ld_event_metadata_keeps_a_date_only_deadline_unverified():
    source = parse_source(
        """
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Event",
          "name": "Useful Agents",
          "organizer": {"@type": "Organization", "name": "Organizer"},
          "startDate": "2026-09-09T13:00:00-07:00",
          "endDate": "2026-09-22T13:00:00-07:00"
        }
        </script>
        </head><body>
          <p>September 16th - Submission deadline on the agent index.</p>
          <p>September 23rd, 1pm PT - Leaderboard snapshot.</p>
        </body></html>
        """,
        "https://events.example/useful-agents",
        "official",
        "official_page",
    )

    assert source.title == "Useful Agents"
    assert source.organizer == "Organizer"
    assert source.start_at == "2026-09-09T13:00:00-07:00"
    assert source.deadlines == {"FINAL_SNAPSHOT": "2026-09-23T13:00:00-07:00"}
    assert "SUBMISSION_DEADLINE is published without a time" in source.uncertainty[0]


def test_real_page_without_prohibitions_can_advance_to_strategy(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")

    mission = run_vertical_slice(
        app,
        str(AGENT_INDEX_FIXTURE),
        workspace_path=str(tmp_path / "workspace"),
    )
    status = mission_status(app, mission)

    assert mission.state == MissionState.PLANNING
    assert status["deadline"] is None
    assert status["quality_blockers"] == []
    assert status["selected_strategy"] is not None
