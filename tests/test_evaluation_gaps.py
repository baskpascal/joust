from uuid import uuid4

from hackathon_competitor.capabilities.evaluation import evaluate_test_gaps


def test_test_gap_analysis_is_a_real_independent_evaluator():
    result = evaluate_test_gaps(
        uuid4(), uuid4(), "exit_code=0\nMission: x\nState: y\nEvidence: 1\nSelected strategy: z"
    )
    assert result.evaluator_role == "test_gap_reviewer"
    assert result.blocking_findings == []
    assert result.scores["coverage"] == 1.0
