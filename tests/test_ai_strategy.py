"""What has to be true for a strategy to count as a model's decision.

The contract these cases hold is narrow and deliberate: a real provider was
reached, its answer survived validation against the competition it was given,
and the call is on the record. When no provider answers, the mission stops with
a named boundary and stores nothing — which is the difference between an AI
product and a deterministic one wearing its name.
"""

import json
from uuid import uuid4

import pytest

from hackathon_competitor.ai import (
    InvocationRecorder,
    ModelUnavailable,
    UnavailableReasoner,
)
from hackathon_competitor.capabilities.ai_strategy import (
    StrategyRejected,
    generate_candidates,
    plan_project,
    select_candidate,
    strategize,
)
from hackathon_competitor.models import (
    Evidence,
    HackathonSpec,
    ModelInvocationStatus,
    Requirement,
)
from hackathon_competitor.storage import Database


class ScriptedReasoner:
    """A stand-in provider whose answers are the test's subject, not its result.

    It never stands in for a provider in the product path; it exists so the
    validation gates can be driven with answers a real model could plausibly
    return, including the bad ones.
    """

    provider = "scripted"
    model = "test"

    def __init__(self, *answers: object):
        self.answers = [
            answer if isinstance(answer, str) else json.dumps(answer) for answer in answers
        ]
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else "{}"


def _candidate(**overrides) -> dict:
    base = {
        "product_thesis": "A named product doing one concrete repeated job for one user",
        "target_user": "a release engineer",
        "recurring_job": "triage every red build",
        "winning_mechanism": "maximises the reported usage the leaderboard counts",
        "technical_plan": "a CLI plus a reporting client",
        "distribution_plan": "ship through the index listing",
        "assumptions": ["builds fail often"],
        "risks": ["nobody installs it"],
        "expected_competitive_advantage": "triggered by CI, not by a person remembering",
    }
    base.update(overrides)
    return base


def _generation(**per_candidate) -> dict:
    return {
        "winning_mechanism_analysis": "rank comes from reported usage",
        "candidates": [
            _candidate(target_user="a release engineer", winning_mechanism="usage volume"),
            _candidate(target_user="a reporter", winning_mechanism="install breadth"),
            _candidate(target_user="a solo builder", winning_mechanism="rides mandatory rules"),
        ],
        **per_candidate,
    }


@pytest.fixture
def mission_database(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    return database


@pytest.fixture
def spec_and_evidence():
    mission_id = uuid4()
    evidence = [
        Evidence(
            mission_id=mission_id,
            claim=f"rule {index}",
            source_type="official_page",
            source_uri="https://example.test/rules",
            excerpt=f"rule {index}",
            confidence=0.99,
            authority="official",
        )
        for index in range(3)
    ]
    spec = HackathonSpec(
        mission_id=mission_id,
        name="Test Cup",
        canonical_url="https://example.test/rules",
        submission_requirements=[Requirement(id="r1", text="publish a repository")],
        rules_locked=True,
    )
    return spec, evidence


def test_a_real_strategy_is_generated_selected_and_attributed(
    mission_database, spec_and_evidence
):
    spec, evidence = spec_and_evidence
    reasoner = ScriptedReasoner(
        _generation(),
        {"selected_index": 1, "rationale": "x" * 60, "rejected": [{"index": 0, "reason": "slow"}]},
    )
    recorder = InvocationRecorder(mission_database, spec.mission_id)

    candidates, selected, decision, analysis = strategize(spec, evidence, reasoner, recorder)

    assert len(candidates) == 3
    assert selected is candidates[1]
    assert analysis == "rank comes from reported usage"
    assert decision.decision_type == "strategy_selection"
    assert decision.selected_option == str(selected.id)

    invocations = mission_database.list_model_invocations(spec.mission_id)
    assert [item.purpose for item in invocations] == [
        "strategy_generation",
        "strategy_selection",
    ]
    assert all(item.status is ModelInvocationStatus.SUCCEEDED for item in invocations)
    assert all(item.provider == "scripted" and item.model == "test" for item in invocations)
    assert decision.invocation_id == invocations[1].id
    assert len({item.prompt_hash for item in invocations}) == 2
    assert mission_database.list_strategy_candidates(spec.mission_id)


def test_the_rejection_reason_for_each_alternative_is_kept(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    reasoner = ScriptedReasoner(
        _generation(),
        {
            "selected_index": 0,
            "rationale": "y" * 60,
            "rejected": [{"index": 2, "reason": "no recurring use"}],
        },
    )
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    _, _, decision, _ = strategize(spec, evidence, reasoner, recorder)
    reasons = {item["index"]: item["rejected_because"] for item in decision.alternatives_considered}
    assert reasons[2] == "no recurring use"
    assert reasons[1] == ""


def test_without_a_provider_the_mission_stops_and_stores_no_strategy(
    mission_database, spec_and_evidence
):
    """The ablation contract: no model, no strategy, and no imitation of one."""

    spec, evidence = spec_and_evidence
    recorder = InvocationRecorder(mission_database, spec.mission_id)

    with pytest.raises(ModelUnavailable) as caught:
        strategize(spec, evidence, UnavailableReasoner(), recorder)

    assert caught.value.code == "AI_STRATEGY_UNAVAILABLE"
    assert mission_database.list_strategy_candidates(spec.mission_id) == []
    assert mission_database.list_ai_decisions(spec.mission_id) == []
    invocations = mission_database.list_model_invocations(spec.mission_id)
    assert [item.status for item in invocations] == [ModelInvocationStatus.UNAVAILABLE]
    assert invocations[0].error.startswith("AI_STRATEGY_UNAVAILABLE")


def test_too_few_candidates_are_refused(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    reasoner = ScriptedReasoner({"candidates": [_candidate(), _candidate()]})
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    with pytest.raises(StrategyRejected, match="fewer than the required 3"):
        generate_candidates(spec, evidence, reasoner, recorder)


def test_three_restatements_of_one_idea_are_refused(mission_database, spec_and_evidence):
    """Variety in the wording is not variety in the bet."""

    spec, evidence = spec_and_evidence
    reasoner = ScriptedReasoner({"candidates": [_candidate(), _candidate(), _candidate()]})
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    with pytest.raises(StrategyRejected, match="not distinct strategies"):
        generate_candidates(spec, evidence, reasoner, recorder)


def test_a_candidate_missing_a_field_is_refused(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    broken = _generation()
    broken["candidates"][2]["winning_mechanism"] = "  "
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    with pytest.raises(StrategyRejected, match="omitted"):
        generate_candidates(spec, evidence, ScriptedReasoner(broken), recorder)


def test_a_selection_outside_the_candidate_set_is_refused(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    candidates, _ = generate_candidates(
        spec, evidence, ScriptedReasoner(_generation()), recorder
    )
    with pytest.raises(StrategyRejected, match="outside the candidate set"):
        select_candidate(
            spec,
            evidence,
            candidates,
            ScriptedReasoner({"selected_index": 9, "rationale": "z" * 60}),
            recorder,
        )


def test_a_selection_without_a_stated_reason_is_refused(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    candidates, _ = generate_candidates(
        spec, evidence, ScriptedReasoner(_generation()), recorder
    )
    with pytest.raises(StrategyRejected, match="without stating why"):
        select_candidate(
            spec,
            evidence,
            candidates,
            ScriptedReasoner({"selected_index": 0, "rationale": "because"}),
            recorder,
        )


def test_the_generation_prompt_carries_the_competition_and_not_a_template(
    mission_database, spec_and_evidence
):
    """A prompt that does not contain the competition cannot have reasoned about it."""

    spec, evidence = spec_and_evidence
    reasoner = ScriptedReasoner(_generation())
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    generate_candidates(spec, evidence, reasoner, recorder)
    prompt = reasoner.prompts[0]
    assert "Test Cup" in prompt
    assert "publish a repository" in prompt


def test_the_project_plan_must_be_buildable(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    candidates, _ = generate_candidates(
        spec, evidence, ScriptedReasoner(_generation()), recorder
    )
    plan, decision = plan_project(
        spec,
        candidates[0],
        ScriptedReasoner(
            {
                "repository_name": "red-build-triage",
                "language": "Python 3.11",
                "framework": "none",
                "install_commands": [["python3", "-m", "venv", ".venv"]],
                "test_commands": [[".venv/bin/python", "-m", "pytest", "-q"]],
                "lint_commands": [],
                "first_slice_specification": "s" * 120,
            }
        ),
        recorder,
    )
    assert plan["repository_name"] == "red-build-triage"
    assert plan["test_commands"] == [[".venv/bin/python", "-m", "pytest", "-q"]]
    assert decision.decision_type == "project_plan"


def test_a_project_plan_without_a_test_command_is_refused(mission_database, spec_and_evidence):
    spec, evidence = spec_and_evidence
    recorder = InvocationRecorder(mission_database, spec.mission_id)
    candidates, _ = generate_candidates(
        spec, evidence, ScriptedReasoner(_generation()), recorder
    )
    with pytest.raises(StrategyRejected, match="no test commands"):
        plan_project(
            spec,
            candidates[0],
            ScriptedReasoner(
                {
                    "repository_name": "x-tool",
                    "language": "Python",
                    "install_commands": [["python3", "-m", "venv", ".venv"]],
                    "test_commands": "pytest",
                    "first_slice_specification": "s" * 120,
                }
            ),
            recorder,
        )
