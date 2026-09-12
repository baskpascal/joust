from pathlib import Path

from hackathon_competitor.capabilities.strategy import (
    cluster_ideas,
    deep_candidate_analysis,
    evaluate_top_ideas,
    generate_ideas,
    opportunity_map,
    screen_ideas,
)
from hackathon_competitor.models import HackathonSpec


def test_opportunity_map_and_deep_analysis_are_evidence_linked(tmp_path: Path):
    spec = HackathonSpec(
        mission_id="14a97d51-8235-4a9a-9371-b7f08dfd72bd",
        name="Fixture",
        canonical_url=str(tmp_path / "official.html"),
        evidence_ids=["f58afe58-edbd-4bad-b712-4f250e795e1a"],
    )
    ideas = generate_ideas(spec)
    mapping = opportunity_map(cluster_ideas(ideas))
    assert set(mapping) == {"general", "contrarian", "ambitious", "demoable", "sponsor-native"}
    finalists = screen_ideas(ideas)
    analysis = deep_candidate_analysis(finalists, evaluate_top_ideas(spec.mission_id, finalists))
    assert len(analysis) == 3
    assert all(item["evidence_ids"] for item in analysis)
    assert all(item["prototype_question"] for item in analysis)
