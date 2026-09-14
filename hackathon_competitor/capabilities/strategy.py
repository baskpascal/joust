"""A deterministic stand-in for strategy, kept only as a regression fixture.

None of this reasons. `generate_ideas` names twenty ideas from a fixed list,
`_stable_score` is a SHA-256 of the title mapped into 0.55-0.96, the six
"independent judges" multiply those same hashes by fixed weights, and
`select_strategy` returns the largest number. It produced a confident decision
for every competition and read none of them.

It survives because the original vertical slice and its tests are built on it,
and because having the imitation in the tree, clearly labelled, is better than
having it in the product unlabelled. The path that decides what Joust builds is
`hackathon_competitor.capabilities.ai_strategy`, which calls a real model and
stops when none answers. Do not route a mission through this module.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from uuid import UUID

from ..models import DebateRecord, Decision, Evaluation, HackathonSpec, Idea, MetaJudgeResult

BATCHES = {
    "general": ["Navigator", "Workbench", "Coach", "Radar"],
    "contrarian": ["Failure Atlas", "Constraint Lens", "Skeptic", "Reverse Brief"],
    "ambitious": ["Live Twin", "Autonomous Lab", "Evidence Graph", "Simulation Room"],
    "demoable": ["Five-Minute Win", "Guided Sprint", "Instant Audit", "One-Click Proof"],
    "sponsor-native": ["Native Copilot", "Integration Forge", "Sponsor Studio", "API Advantage"],
}


def _stable_score(seed: str, low: float = 0.55, high: float = 0.96) -> float:
    number = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * number, 3)


def generate_ideas(spec: HackathonSpec) -> list[Idea]:
    evidence_ids = spec.evidence_ids[:3]
    required = spec.required_technologies[0] if spec.required_technologies else "the sponsor stack"
    ideas: list[Idea] = []
    for batch, names in BATCHES.items():
        for name in names:
            title = f"{spec.name}: {name}"
            ideas.append(
                Idea(
                    title=title,
                    summary=(
                        f"A {batch.replace('-', ' ')} product direction using {required} "
                        "to turn competition evidence into an immediately demonstrable user outcome."
                    ),
                    batch=batch,
                    dimensions={
                        dimension: _stable_score(f"{title}:{dimension}")
                        for dimension in (
                            "rule_fit",
                            "user_value",
                            "differentiation",
                            "feasibility",
                            "demoability",
                            "evidence_strength",
                        )
                    },
                    evidence_ids=evidence_ids,
                )
            )
    return ideas


def screen_ideas(ideas: list[Idea], limit: int = 3) -> list[Idea]:
    return sorted(
        ideas,
        key=lambda idea: sum(idea.dimensions.values()) / len(idea.dimensions),
        reverse=True,
    )[:limit]


def cluster_ideas(ideas: list[Idea]) -> dict[str, list[Idea]]:
    clusters: dict[str, list[Idea]] = defaultdict(list)
    for idea in ideas:
        clusters[idea.batch].append(idea)
    if len(clusters) < 3:
        raise ValueError("idea diversity gate requires at least three opportunity clusters")
    return dict(clusters)


def opportunity_map(clusters: dict[str, list[Idea]]) -> dict[str, dict[str, object]]:
    return {
        name: {
            "candidate_count": len(members),
            "dominant_assumption": {
                "general": "broad user value",
                "contrarian": "common approaches are structurally weak",
                "ambitious": "technical depth creates visible advantage",
                "demoable": "immediate legibility drives judging utility",
                "sponsor-native": "native integration strengthens rule and sponsor fit",
            }.get(name, "unclassified opportunity"),
            "evidence_ids": sorted({str(item) for idea in members for item in idea.evidence_ids}),
        }
        for name, members in clusters.items()
    }


ROLE_WEIGHTS = {
    "product_judge": {"user_value": 1.5, "differentiation": 1.2, "demoability": 1.0},
    "technical_judge": {"feasibility": 1.5, "rule_fit": 1.2, "evidence_strength": 1.0},
    "skeptical_judge": {"evidence_strength": 1.5, "rule_fit": 1.3, "feasibility": 1.1},
    "innovation_judge": {"differentiation": 1.5, "user_value": 1.1},
    "sponsor_rule_judge": {"rule_fit": 1.5, "evidence_strength": 1.2},
    "user_value_judge": {"user_value": 1.6, "demoability": 1.2},
}


def evaluate_top_ideas(mission_id: UUID, ideas: list[Idea]) -> list[Evaluation]:
    evaluations: list[Evaluation] = []
    for idea in ideas:
        for role, weights in ROLE_WEIGHTS.items():
            scores = {
                dimension: round(value * weights.get(dimension, 1.0), 3)
                for dimension, value in idea.dimensions.items()
            }
            evaluations.append(
                Evaluation(
                    mission_id=mission_id,
                    evaluator_role=f"{role}:{idea.id}",
                    rubric=weights,
                    scores=scores,
                    findings=[f"{idea.title} was reviewed independently by {role}."],
                    blocking_findings=[],
                    recommendations=[
                        "Prototype the highest-risk assumption before expanding scope."
                    ],
                    confidence=0.82,
                )
            )
    return evaluations


def deep_candidate_analysis(
    ideas: list[Idea], evaluations: list[Evaluation]
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for idea in ideas:
        panel = [item for item in evaluations if item.evaluator_role.endswith(str(idea.id))]
        mean = sum(sum(item.scores.values()) / len(item.scores) for item in panel) / len(panel)
        weakest = min(idea.dimensions, key=idea.dimensions.get)
        results.append(
            {
                "idea_id": str(idea.id),
                "title": idea.title,
                "panel_score": round(mean, 3),
                "riskiest_dimension": weakest,
                "riskiest_score": idea.dimensions[weakest],
                "prototype_question": (
                    f"Can {idea.title} prove {weakest.replace('_', ' ')} in one executable path?"
                ),
                "evidence_ids": [str(item) for item in idea.evidence_ids],
            }
        )
    return sorted(results, key=lambda item: item["panel_score"], reverse=True)


def select_strategy(
    mission_id: UUID,
    ideas: list[Idea],
    evaluations: list[Evaluation],
) -> Decision:
    totals: dict[UUID, list[float]] = defaultdict(list)
    for evaluation in evaluations:
        idea_id = UUID(evaluation.evaluator_role.rsplit(":", 1)[1])
        totals[idea_id].append(sum(evaluation.scores.values()) / len(evaluation.scores))
    ranked = sorted(
        ideas,
        key=lambda idea: sum(totals[idea.id]) / len(totals[idea.id]),
        reverse=True,
    )
    selected, runner_up = ranked[:2]
    return Decision(
        mission_id=mission_id,
        question="Which strategy should anchor the first implementation?",
        options=[
            {"id": str(idea.id), "title": idea.title, "summary": idea.summary} for idea in ranked
        ],
        selected_option=str(selected.id),
        rationale=(
            f"{selected.title} won the independent product, technical, and skeptical reviews. "
            f"Runner-up {runner_up.title} scored lower on the combined role-weighted rubric."
        ),
        evidence_ids=selected.evidence_ids,
        confidence=0.84,
        depth_level=4,
        reversible=True,
        reconsider_if=[
            "official rules change",
            "the riskiest prototype assumption fails",
            "new competitor evidence removes differentiation",
        ],
    )


def debate_strategy(selected: Idea, runner_up: Idea) -> DebateRecord:
    return DebateRecord(
        proposal=selected.title,
        pro_arguments=[
            "Highest combined independent-review score.",
            "Strong traceability to official evidence.",
        ],
        con_arguments=[
            "The riskiest user-value assumption remains to be prototyped.",
            "A polished demo still determines whether the depth is legible.",
        ],
        alternative_proposal=runner_up.title,
        evidence_comparison=[
            f"{selected.title} and {runner_up.title} use the same locked rule evidence.",
            f"{selected.title} has the stronger role-weighted evaluation aggregate.",
        ],
        judge_decision=f"Proceed with {selected.title}; retain {runner_up.title} as fallback.",
    )


def meta_judge(evaluations: list[Evaluation]) -> MetaJudgeResult:
    if len({item.evaluator_role.split(":", 1)[0] for item in evaluations}) < 3:
        raise ValueError("meta-judge requires at least three independent evaluator roles")
    role_means: dict[str, float] = {}
    for evaluation in evaluations:
        role = evaluation.evaluator_role.split(":", 1)[0]
        role_means.setdefault(role, 0.0)
        role_means[role] += sum(evaluation.scores.values()) / len(evaluation.scores)
    spread = max(role_means.values()) - min(role_means.values())
    return MetaJudgeResult(
        consensus=[
            "The finalist set is feasible enough to prototype and grounded in locked rules."
        ],
        unresolved_disagreement=(
            ["Evaluator roles disagree materially on the balance of novelty and feasibility."]
            if spread > 1.0
            else []
        ),
        confidence=0.8 if spread <= 1.0 else 0.65,
        recommended_next_action="Prototype the selected strategy's highest-risk assumption.",
        more_evidence_required=spread > 1.0,
    )
