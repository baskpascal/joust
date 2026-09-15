"""Ask a model what to build, and keep every answer it gave.

This replaces the part of Joust that was never intelligent. Idea generation
used to hash a title into a score between 0.55 and 0.96, six "independent
judges" multiplied those hashes by fixed weights, and the winner was the
largest number. That pipeline produced a decision for any competition and
learned nothing from any of them.

Here a real model reads the extracted competition and proposes materially
different ways to win, then picks one and says why. Every answer is validated
against the competition it was given — a candidate that could have been written
without reading the rules is rejected — and every call is recorded as a
ModelInvocation. When no model answers, this raises. It never falls back.
"""

from __future__ import annotations

import json
import re
from uuid import UUID

from ..ai import InvocationRecorder, ModelUnavailable, Reasoner, json_object
from ..models import AIDecision, Evidence, HackathonSpec, StrategyCandidate

MINIMUM_CANDIDATES = 3
_REQUIRED_FIELDS = (
    "product_thesis",
    "target_user",
    "recurring_job",
    "winning_mechanism",
    "technical_plan",
    "distribution_plan",
    "expected_competitive_advantage",
)


class StrategyRejected(ValueError):
    """The model answered, but the answer does not survive validation."""


def competition_briefing(spec: HackathonSpec, evidence: list[Evidence]) -> dict:
    """Everything the model is allowed to reason from, and nothing else."""

    return {
        "name": spec.name,
        "organizer": spec.organizer,
        "canonical_url": spec.canonical_url,
        "deadline_at": spec.deadline_at.isoformat() if spec.deadline_at else None,
        "judging_mode": spec.judging_mode,
        "leaderboard_model": spec.leaderboard_model,
        "scoring_rules": spec.scoring_rules[:10],
        "required_technologies": spec.required_technologies[:10],
        "prohibited_actions": spec.prohibited_actions[:10],
        "submission_requirements": [item.text for item in spec.submission_requirements][:15],
        "eligibility_requirements": [item.text for item in spec.eligibility_requirements][:15],
        "uncertainty": spec.uncertainty[:5],
        "evidence_excerpts": [item.excerpt[:300] for item in evidence[:12]],
    }


_GENERATION_SCHEMA = {
    "winning_mechanism_analysis": "what actually produces rank or victory here",
    "candidates": [
        {
            "product_thesis": "one specific product, not a category",
            "target_user": "who precisely",
            "recurring_job": "the repeated task it does for them",
            "winning_mechanism": "how this scores under THIS competition's rules",
            "technical_plan": "what gets built, concretely",
            "distribution_plan": "how it reaches users before the deadline",
            "assumptions": ["assumption"],
            "risks": ["risk"],
            "expected_competitive_advantage": "why this beats the obvious entries",
        }
    ],
}


def generate_candidates(
    spec: HackathonSpec,
    evidence: list[Evidence],
    reasoner: Reasoner,
    recorder: InvocationRecorder,
    *,
    minimum: int = MINIMUM_CANDIDATES,
) -> tuple[list[StrategyCandidate], str]:
    briefing = competition_briefing(spec, evidence)
    prompt = (
        "You are deciding what to build to win a specific competition. Read the "
        "competition below and propose "
        f"{minimum} materially different products. Materially different means different "
        "target users and different winning mechanisms, not three versions of one idea.\n\n"
        "Each proposal must be a concrete product a named person would use for a repeated "
        "job. Reject your own generic answers: 'AI productivity assistant', 'research "
        "assistant' and 'agent with many tools' are not products. Ground the winning "
        "mechanism in this competition's stated scoring and requirements, quoting the rule "
        "you are relying on. Do not propose anything the prohibited actions forbid.\n\n"
        "Return exactly one JSON object, no markdown, no commentary.\n\n"
        f"response_schema={json.dumps(_GENERATION_SCHEMA, sort_keys=True)}\n"
        f"competition={json.dumps(briefing, sort_keys=True, default=str)}"
    )
    text, invocation = recorder.run(
        reasoner,
        purpose="strategy_generation",
        prompt=prompt,
        context=briefing,
    )
    payload = json_object(text)
    raw = payload.get("candidates")
    if not isinstance(raw, list) or len(raw) < minimum:
        raise StrategyRejected(
            f"the model returned {len(raw) if isinstance(raw, list) else 0} candidates, "
            f"fewer than the required {minimum}"
        )
    candidates = [_validate_candidate(item, spec, invocation.id, index) for index, item in enumerate(raw)]
    _reject_undifferentiated(candidates)
    return candidates, str(payload.get("winning_mechanism_analysis") or "").strip()


def _validate_candidate(item: object, spec: HackathonSpec, invocation_id: UUID, index: int) -> StrategyCandidate:
    if not isinstance(item, dict):
        raise StrategyRejected(f"candidate {index} is not an object")
    missing = [field for field in _REQUIRED_FIELDS if not str(item.get(field) or "").strip()]
    if missing:
        raise StrategyRejected(f"candidate {index} omitted {missing}")
    thesis = str(item["product_thesis"]).strip()
    if len(thesis) < 20:
        raise StrategyRejected(f"candidate {index} states no real product: {thesis!r}")
    return StrategyCandidate(
        mission_id=spec.mission_id,
        invocation_id=invocation_id,
        product_thesis=thesis,
        target_user=str(item["target_user"]).strip(),
        recurring_job=str(item["recurring_job"]).strip(),
        winning_mechanism=str(item["winning_mechanism"]).strip(),
        technical_plan=str(item["technical_plan"]).strip(),
        distribution_plan=str(item["distribution_plan"]).strip(),
        assumptions=[str(value).strip() for value in item.get("assumptions") or [] if str(value).strip()],
        risks=[str(value).strip() for value in item.get("risks") or [] if str(value).strip()],
        expected_competitive_advantage=str(item["expected_competitive_advantage"]).strip(),
    )


def _reject_undifferentiated(candidates: list[StrategyCandidate]) -> None:
    """Three restatements of one idea are one idea.

    A model asked for variety will sometimes return it only in the wording, so
    the distinctness gate looks at the two fields that define a different bet:
    who it is for and how it wins.
    """

    for field in ("target_user", "winning_mechanism"):
        values = {getattr(candidate, field).strip().casefold() for candidate in candidates}
        if len(values) < 2:
            raise StrategyRejected(
                f"every candidate shares the same {field}; these are not distinct strategies"
            )


_SELECTION_SCHEMA = {
    "selected_index": 0,
    "rationale": "why this one wins here, citing the competition's own rules",
    "rejected": [{"index": 1, "reason": "why not"}],
}


def select_candidate(
    spec: HackathonSpec,
    evidence: list[Evidence],
    candidates: list[StrategyCandidate],
    reasoner: Reasoner,
    recorder: InvocationRecorder,
) -> tuple[StrategyCandidate, AIDecision]:
    briefing = competition_briefing(spec, evidence)
    listing = [
        {
            "index": index,
            "product_thesis": candidate.product_thesis,
            "target_user": candidate.target_user,
            "recurring_job": candidate.recurring_job,
            "winning_mechanism": candidate.winning_mechanism,
            "risks": candidate.risks,
            "expected_competitive_advantage": candidate.expected_competitive_advantage,
        }
        for index, candidate in enumerate(candidates)
    ]
    prompt = (
        "Choose the single strategy most likely to win this competition, and say why "
        "against this competition's own scoring and requirements. Judge feasibility "
        "before the stated deadline, whether real users would adopt it, and whether it "
        "differs from what obvious entrants will submit. Give a reason for each rejection.\n\n"
        "Return exactly one JSON object, no markdown.\n\n"
        f"response_schema={json.dumps(_SELECTION_SCHEMA, sort_keys=True)}\n"
        f"competition={json.dumps(briefing, sort_keys=True, default=str)}\n"
        f"candidates={json.dumps(listing, sort_keys=True, default=str)}"
    )
    text, invocation = recorder.run(
        reasoner,
        purpose="strategy_selection",
        prompt=prompt,
        context={"competition": briefing, "candidates": listing},
    )
    payload = json_object(text)
    index = payload.get("selected_index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(candidates):
        raise StrategyRejected(f"the model selected an index outside the candidate set: {index!r}")
    rationale = str(payload.get("rationale") or "").strip()
    if len(rationale) < 40:
        raise StrategyRejected("the model selected a strategy without stating why")
    selected = candidates[index]
    decision = recorder.record_decision(
        invocation,
        decision_type="strategy_selection",
        alternatives=[
            {
                "index": item["index"],
                "product_thesis": item["product_thesis"],
                "target_user": item["target_user"],
                "rejected_because": next(
                    (
                        str(entry.get("reason") or "").strip()
                        for entry in payload.get("rejected") or []
                        if isinstance(entry, dict) and entry.get("index") == item["index"]
                    ),
                    "",
                ),
            }
            for item in listing
        ],
        selected_option=str(selected.id),
        rationale=rationale,
        evidence_ids=[item.id for item in evidence[:12]],
    )
    return selected, decision


def strategize(
    spec: HackathonSpec,
    evidence: list[Evidence],
    reasoner: Reasoner,
    recorder: InvocationRecorder,
    *,
    minimum: int = MINIMUM_CANDIDATES,
) -> tuple[list[StrategyCandidate], StrategyCandidate, AIDecision, str]:
    """Generate, persist and choose. Raises ModelUnavailable when nothing answers."""

    candidates, analysis = generate_candidates(
        spec, evidence, reasoner, recorder, minimum=minimum
    )
    for candidate in candidates:
        recorder.database.save_strategy_candidate(candidate)
    selected, decision = select_candidate(spec, evidence, candidates, reasoner, recorder)
    return candidates, selected, decision, analysis


_PROJECT_SCHEMA = {
    "repository_name": "short-kebab-case name for the new project",
    "language": "the implementation language",
    "framework": "framework or 'none'",
    "install_commands": [["argv", "form", "only"]],
    "test_commands": [["argv", "form", "only"]],
    "lint_commands": [["argv", "form", "only"]],
    "first_slice_specification": (
        "what to implement first: the smallest build that delivers the recurring job "
        "end to end, with the tests that prove it"
    ),
}


def plan_project(
    spec: HackathonSpec,
    selected: StrategyCandidate,
    reasoner: Reasoner,
    recorder: InvocationRecorder,
) -> tuple[dict, AIDecision]:
    """Let the model shape the project it is about to build.

    Naming the repository, picking the stack and writing the first slice are
    product decisions, not platform mechanics. Deciding them in Joust would put
    a human's template back in the middle of the promise, so they are asked for
    and validated like everything else.
    """

    briefing = {
        "competition": spec.name,
        "deadline_at": spec.deadline_at.isoformat() if spec.deadline_at else None,
        "required_technologies": spec.required_technologies[:10],
        "submission_requirements": [item.text for item in spec.submission_requirements][:10],
        "strategy": {
            "product_thesis": selected.product_thesis,
            "target_user": selected.target_user,
            "recurring_job": selected.recurring_job,
            "winning_mechanism": selected.winning_mechanism,
            "technical_plan": selected.technical_plan,
        },
    }
    prompt = (
        "Plan the repository for this product. Choose the stack that gets a working, "
        "testable first slice fastest, and give every command in argv form, executable "
        "on Linux with nothing preinstalled beyond that language's toolchain. The first "
        "slice must deliver the recurring job end to end for one real input, not a "
        "skeleton. Use a test command that fails when the behaviour is wrong.\n\n"
        "Return exactly one JSON object, no markdown.\n\n"
        f"response_schema={json.dumps(_PROJECT_SCHEMA, sort_keys=True)}\n"
        f"brief={json.dumps(briefing, sort_keys=True, default=str)}"
    )
    text, invocation = recorder.run(
        reasoner, purpose="project_planning", prompt=prompt, context=briefing
    )
    payload = json_object(text)
    name = str(payload.get("repository_name") or "").strip()
    slice_spec = str(payload.get("first_slice_specification") or "").strip()
    if not name or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", name):
        raise StrategyRejected(f"the model proposed an unusable repository name: {name!r}")
    if len(slice_spec) < 80:
        raise StrategyRejected("the model proposed no implementable first slice")
    plan = {
        "repository_name": name,
        "language": str(payload.get("language") or "").strip() or "unknown",
        "framework": str(payload.get("framework") or "none").strip(),
        "install_commands": _argv_list(payload.get("install_commands"), "install"),
        "test_commands": _argv_list(payload.get("test_commands"), "test"),
        "lint_commands": _argv_list(payload.get("lint_commands"), "lint", required=False),
        "first_slice_specification": slice_spec,
    }
    if not plan["test_commands"]:
        raise StrategyRejected("the model planned a project with no test command")
    decision = recorder.record_decision(
        invocation,
        decision_type="project_plan",
        alternatives=[],
        selected_option=name,
        rationale=(
            f"{plan['language']} project '{name}' implementing "
            f"{selected.product_thesis[:160]}"
        ),
    )
    return plan, decision


def _argv_list(value: object, phase: str, *, required: bool = True) -> list[list[str]]:
    if not isinstance(value, list):
        if required:
            raise StrategyRejected(f"the model returned no {phase} commands")
        return []
    commands: list[list[str]] = []
    for entry in value:
        if not isinstance(entry, list) or not entry:
            raise StrategyRejected(f"the model returned a {phase} command that is not argv")
        argv = [str(part) for part in entry]
        if any(not part.strip() for part in argv):
            raise StrategyRejected(f"the model returned an empty {phase} argument")
        commands.append(argv)
    return commands


__all__ = [
    "MINIMUM_CANDIDATES",
    "ModelUnavailable",
    "StrategyRejected",
    "competition_briefing",
    "generate_candidates",
    "plan_project",
    "select_candidate",
    "strategize",
]
