from hackathon_competitor.capabilities.planning import (
    ARCHITECTURE_CRITERIA,
    architecture_tournament,
)
from hackathon_competitor.capabilities.submission import _tournament


def test_architecture_tournament_scores_three_distinct_shapes():
    candidates = architecture_tournament()
    assert len(candidates) == 3
    assert len(ARCHITECTURE_CRITERIA) == 10
    assert candidates[0]["name"] == "Durable modular monolith"
    assert candidates[0]["score"] > candidates[1]["score"]


def test_demo_and_pitch_tournaments_compare_alternatives():
    demo_winner, demos = _tournament("demo")
    pitch_winner, pitches = _tournament("pitch")
    assert len(demos) == len(pitches) == 3
    assert demo_winner == "Evidence-to-outcome"
    assert pitch_winner == "The competition lead"
