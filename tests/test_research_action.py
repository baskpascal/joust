import pytest

from hackathon_competitor.competition_actions import RealResearchActionExecutor
from hackathon_competitor.models import (
    ActionCandidate,
    CompetitionActionType,
    CompetitionSpec,
    Mission,
)
from hackathon_competitor.storage import Database


class Fetcher:
    def __init__(
        self,
        content="<html><body><h1>Rules</h1><p>Entries must use the client.</p></body></html>",
    ):
        self.content = content
        self.calls = []

    def fetch(self, uri):
        self.calls.append(uri)
        return self.content


def _setup(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Research", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    spec = CompetitionSpec(
        mission_id=mission.id,
        name="Competition",
        canonical_url="https://competition.invalid/rules",
        rules_locked=True,
    )
    database.save_spec(spec)
    mission.hackathon_spec_id = spec.id
    mission.competition_id = spec.id
    database.save_mission(mission)
    action = ActionCandidate(
        name="Confirm rules",
        description="Read the official page",
        action_type=CompetitionActionType.RESEARCH,
        parameters={"sources": ["https://competition.invalid/rules"]},
        expected_outcome_improvement=0.2,
        time_cost=1.0,
        technical_risk=0.0,
        regression_probability=0.0,
    )
    return database, mission, action


def test_research_action_persists_source_evidence(tmp_path):
    database, mission, action = _setup(tmp_path)
    fetcher = Fetcher()

    result = RealResearchActionExecutor(database, fetcher=fetcher).execute(mission, None, action)

    assert result.summary == "Captured 1 competition research source(s)"
    assert fetcher.calls == ["https://competition.invalid/rules"]
    evidence = next(
        item for item in database.list_evidence(mission.id) if item.id == result.evidence_ids[0]
    )
    assert evidence.source_uri == "https://competition.invalid/rules"
    assert "must use the client" in evidence.excerpt


def test_research_action_fails_without_readable_evidence(tmp_path):
    database, mission, action = _setup(tmp_path)

    with pytest.raises(RuntimeError, match="no verifiable source evidence"):
        RealResearchActionExecutor(database, fetcher=Fetcher("<html></html>")).execute(
            mission, None, action
        )


def test_research_action_excludes_script_and_style_content(tmp_path):
    database, mission, action = _setup(tmp_path)
    content = """
    <html><style>.secret { color: red; }</style><script>fakeRule()</script>
    <body><p>Visible official requirement.</p></body></html>
    """

    result = RealResearchActionExecutor(database, fetcher=Fetcher(content)).execute(
        mission, None, action
    )

    evidence = next(
        item for item in database.list_evidence(mission.id) if item.id == result.evidence_ids[0]
    )
    assert evidence.excerpt == "Visible official requirement."
