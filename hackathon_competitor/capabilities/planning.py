from __future__ import annotations

from ..models import DebateRecord, Decision, HackathonSpec, Idea, MetaJudgeResult

ARCHITECTURE_CRITERIA = (
    "feasibility",
    "implementation_time",
    "operational_risk",
    "dependency_risk",
    "testability",
    "performance",
    "simplicity",
    "demoability",
    "sponsor_alignment",
    "recovery",
)


def architecture_tournament() -> list[dict[str, object]]:
    candidates = [
        {
            "name": "Durable modular monolith",
            "summary": "One orchestrator, SQLite state, task DAG, and replaceable capabilities.",
            "scores": [0.94, 0.92, 0.88, 0.91, 0.95, 0.78, 0.94, 0.91, 0.90, 0.94],
        },
        {
            "name": "Permanent multi-agent swarm",
            "summary": "Always-on role agents coordinate through a shared message bus.",
            "scores": [0.58, 0.42, 0.48, 0.50, 0.55, 0.62, 0.35, 0.78, 0.82, 0.44],
        },
        {
            "name": "Stateless linear workflow",
            "summary": "A single request executes every competition phase sequentially.",
            "scores": [0.90, 0.96, 0.82, 0.94, 0.68, 0.88, 0.97, 0.60, 0.64, 0.35],
        },
    ]
    for candidate in candidates:
        scores = candidate["scores"]
        candidate["score"] = round(sum(scores) / len(ARCHITECTURE_CRITERIA), 3)
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def render_prd(spec: HackathonSpec, selected: Idea, decision: Decision) -> str:
    requirements = [
        *[item.text for item in spec.submission_requirements],
        *[item.text for item in spec.eligibility_requirements],
        *spec.required_technologies,
    ]
    requirement_lines = (
        "\n".join(f"- {item}" for item in requirements) or "- No explicit requirement extracted."
    )
    prohibited_lines = (
        "\n".join(f"- {item}" for item in spec.prohibited_actions) or "- None extracted."
    )
    return f"""# PRD — {selected.title}

## Problem

Hackathon teams lose decision quality when rules, evidence, product strategy,
implementation, testing, and submission claims drift into separate documents.

## Product direction

{selected.summary}

## Users and first-use value

A participant provides the official competition source and receives a sourced
rules snapshot, candidate directions, an independently reviewed recommendation,
and a concrete plan without configuring a large permanent swarm.

## Requirements traced from official evidence

{requirement_lines}

## Prohibited or blocking conditions

{prohibited_lines}

## MVP acceptance

- The official source and extracted claims remain inspectable.
- At least 20 ideas span multiple assumption batches.
- Three distinct evaluator roles review each finalist.
- The selected strategy links back to evidence.
- The mission and generated PRD survive restart.
- Consequential submission or publication remains human-confirmed.

## Decision record

{decision.rationale}

Confidence: {decision.confidence:.2f}. Reconsider if: {", ".join(decision.reconsider_if)}.
"""


def render_architecture(spec: HackathonSpec, selected: Idea) -> str:
    tournament = architecture_tournament()
    rows = "\n".join(
        f"| {candidate['name']} | {candidate['score']:.3f} | {candidate['summary']} |"
        for candidate in tournament
    )
    winner = tournament[0]
    return f"""# Architecture — {selected.title}

## Tournament

Three materially different candidates were scored across {len(ARCHITECTURE_CRITERIA)} criteria:
{", ".join(ARCHITECTURE_CRITERIA)}.

| Candidate | Competitive utility | Shape |
|---|---:|---|
{rows}

## Selected shape

**{winner["name"]}** wins on competitive utility, not sophistication.
One mission orchestrator owns one durable SQLite state. A persistent task DAG
dispatches narrow research, strategy, planning, execution, and evaluation
capabilities. Evidence and artifacts are first-class records; dependency edges
mark downstream work stale when upstream facts change.

## Runtime boundary

Galahad is a variant of the official Plow Hermes image. Plow Chat, Latch,
gateway boot, and generic credentials remain upstream. This repository owns
only the persona, skills, mission package, tests, and Agent Index service.

## Competition fit

The architecture optimizes for {spec.name}: useful end-to-end missions,
transparent progress, recovery after restart, and evidence-backed decisions.
It deliberately avoids a permanent swarm and avoids token-budget logic.
"""


def render_implementation_plan(selected: Idea) -> str:
    return f"""# Implementation plan — {selected.title}

1. Prove the highest-risk user-value assumption with a narrow prototype.
2. Trace locked rules into features and executable acceptance checks.
3. Build the primary path in coherent slices with persisted task results.
4. Run technical, product, security, skeptical, and demo reviews.
5. Convert blocking findings into ordered repair tasks and re-run checks.
6. Freeze claims, rehearse the demo, and prepare submission artifacts.

Each slice includes code, tests, typing, error handling, docs, exact validation
commands, and no unrelated refactor.
"""


def render_acceptance_plan(spec: HackathonSpec) -> str:
    return f"""# Acceptance plan — {spec.name}

- Mission creation from an official URL persists across restart.
- Rule extraction stores source-backed evidence and contradiction records.
- Strategy selection retains finalists, independent evaluations, fallback,
  risks, and reconsideration conditions.
- Artifact changes mark dependent PRD, demo, pitch, and submission content stale.
- No readiness state is possible while a blocker rule is failed or unknown.
- Install, primary demo path, and submission claims are verified before readiness.
- Agent Index reporter is present, pinned, supervised, and isolated from mission content.
"""


def render_risk_register(spec: HackathonSpec, selected: Idea) -> str:
    return f"""# Risk register — {selected.title}

| Risk | Probability | Damage | Early signal | Mitigation |
|---|---:|---:|---|---|
| User value is not obvious on first use | Medium | High | Users stop before first artifact | Return sourced competition snapshot first |
| Rule update invalidates a claim | Medium | High | New official announcement | Version spec, rerun compliance, stale descendants |
| Depth is hard to demo | Medium | High | Demo exceeds three minutes | Tournament and rehearse shorter narratives |
| Integration fails near deadline | Medium | High | Flaky primary path | Deadline freeze and critical-path tests |
| Product duplicates common idea tools | Medium | Medium | Competitor map shows saturation | Emphasize evidence-to-repair full loop |

Current official-source target: {spec.canonical_url or "unknown"}.
"""


def render_premortem(selected: Idea) -> str:
    return f"""# Premortem — {selected.title}

Assume the project performed badly. The most plausible causes are: weak
first-use value, a rules miss, an unproven core assumption, a fragile demo,
and claims that outrun the build. Detect them with activation observation,
compliance checks, an early prototype, repeated demo runs, and a claims map.
"""


def render_win_review(selected: Idea) -> str:
    return f"""# Win review — {selected.title}

Assume the project wins. Likely causes: users get useful output immediately,
return for multiple missions, trust the evidence trail, understand progress,
and see the full research-to-repair loop in a credible demo. Convert those
traits into activation, repeat-use, provenance, status, and demo acceptance tests.
"""


def render_strategy_review(debate: DebateRecord, meta: MetaJudgeResult) -> str:
    return f"""# Strategy review

## Debate

Proposal: {debate.proposal}

Alternative: {debate.alternative_proposal}

Decision: {debate.judge_decision}

## Meta-judge

Consensus: {"; ".join(meta.consensus)}

Unresolved: {"; ".join(meta.unresolved_disagreement) or "none"}

Next action: {meta.recommended_next_action}
"""
