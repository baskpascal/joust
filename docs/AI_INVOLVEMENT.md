# Where the intelligence actually is

Traced by following the execution path, not the class names, on 2026-09-14.
Mechanisms are: **deterministic** (plain code), **template** (fixed text or
fixed tables), **model** (a real provider call), **coding agent** (a model that
writes files).

## After this change

| Decision | Mechanism | AI in the loop | Where |
|---|---|---|---|
| Competition page fetch and rule extraction | deterministic parser | no | `capabilities/research.py` |
| Deadline and scoring-mechanism extraction | deterministic parser | no | `capabilities/research.py` |
| Winning-mechanism analysis | model | **yes** | `ai_strategy.generate_candidates` |
| Product ideation (≥3 distinct strategies) | model | **yes** | `ai_strategy.generate_candidates` |
| Niche / target-user selection | model | **yes** | `ai_strategy.select_candidate` |
| Strategy choice and its rationale | model | **yes** | `ai_strategy.select_candidate` |
| Repository name, stack and commands | model | **yes** | `ai_strategy.plan_project` |
| First implementation slice | model | **yes** | `ai_strategy.plan_project` |
| Implementation | coding agent | **yes** | `build_loop.ClaudeCodeImplementer`, `HermesImplementer` |
| Failure diagnosis and repair | coding agent | **yes** | `build_loop.*.repair` |
| Next-best-action in the compete loop | model | **yes** | `hermes_planner.HermesCompetitionPlanner.assess` |
| Answering a question about a mission | model, over stored state only | **yes** | `ai_mission.ask` |
| Change of direction from the operator | model, over stored candidates | **yes** | `ai_mission.redirect` |
| Readiness measurement | deterministic | no | `hermes_planner.ReadinessMeasurer` |
| Post-action adaptation text | template | no | `hermes_planner.HermesCompetitionPlanner.adapt` |
| Compliance and readiness gates | deterministic | no | `compliance.py`, `quality_gates.py` |
| Clean-clone reproduction | deterministic | no | `build_loop.RealBuildLoop._reproduce` |
| Red-team review of a diff | deterministic patterns | no | `project_review.py` |

Deterministic is the right answer for several of these. Reproducing a clone,
hashing a diff and checking a licence are not judgement calls, and a model in
those places would make the evidence weaker, not stronger.

## Before this change

| Decision | Mechanism | AI in the loop |
|---|---|---|
| Product ideation | 20 titles from a fixed dictionary | no |
| Idea scoring | `sha256(title)` mapped into 0.55–0.96 | no |
| Six "independent judges" | the same hashes × six fixed weight tables | no |
| Strategy choice | largest of those numbers, templated rationale | no |
| Architecture tournament | three fixed candidates, three fixed score arrays | no |
| PRD | f-string | no |
| Implementation (vertical slice) | one hardcoded source string | no |
| Next-best-action | model | yes |
| Implementation (real build loop) | coding agent | yes |

`llm.py` and `structured.py` defined an LLM client, a telemetry wrapper and a
structured runner. No production path constructed one; they appeared only in
tests.

## What proves the difference

Run the same mission twice. With a provider, a competition URL produces
strategies, a choice and a project. With `--no-model`, the same URL on the same
command stops:

```json
{"state": "BLOCKED", "boundary": "AI_STRATEGY_UNAVAILABLE"}
```

No strategy candidates, no decisions, no project directory. If Joust still
produced a comparable entry without a model, the model would not be what is
producing it.
