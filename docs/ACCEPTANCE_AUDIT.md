# V0 acceptance audit

This audit distinguishes repository evidence from external conditions. A
synthetic Plow relay is used only for the boot contract test; the live
owner-authenticated compose evidence is recorded separately below. Neither
runtime evidence nor client registration proves a public Verified listing.

| SDD criterion | Evidence | Result |
|---|---|---|
| Immutable Plow variant builds | `Dockerfile`, final image digest in `BUILD_NOTES.md` | PASS |
| Runtime `/init` starts safely | s6 boot smoke with synthetic identity relay | PASS (contract) |
| Live Hermes/Plow interaction | Owner message produced a persisted 219-character reply; delivery state reached `delivered` | PASS (live runtime) |
| No embedded credentials | `.gitignore`, `.dockerignore`, image/source secret scan | PASS |
| URL mission and restart | `tests/test_vertical_slice.py`, two-instance container E2E | PASS |
| DAG, retries, crash recovery | `tests/test_task_engine.py` | PASS |
| Rules, evidence, cross-check, contradiction | `tests/test_vertical_slice.py`, `test_rule_updates.py`, research fixture | PASS |
| Multi-batch ideas and tournament | strategy tests and persisted 20-idea mission | PASS |
| PRD, architecture, implementation, acceptance plan | planning artifacts and artifact graph | PASS |
| Independent evaluators and meta-judge | six strategy roles, five implementation roles plus test-gap reviewer, stored evaluations | PASS |
| Red team and improvement tasks | V0 completion path and evaluation capability | PASS |
| Submission pack and blocker gate | compliance report, install validation, final checklist | PASS (local) |
| Public distribution bundle | Committed-tree ZIP passed secret/path checks, clean Python install, CLI smoke, and Docker build | PASS (local artifact) |
| Agent Index client pinned and integrity checked | `vendor/client.pin`, Docker build checksum step | PASS |
| Agent Index reporter supervised | Live status registered; supervised usage report returned HTTP 200 for two rows | PASS (live runtime) |
| Public Agent Index entry | Rendered `/agent-index/galahad-hackathon` page showed Galahad, GitHub install link, one active user, 119K tokens, and the Engineering story | PASS (public community listing) |
| Public repository publication | `https://github.com/baskpascal/joust`, public `main`, linked from the Agent Index entry | PASS (public) |
| Chosen `AGENT_ID` wiring | Explicit compose env, reporter, and doctor check | PASS (local) |
| Verified listing | Organizer eligibility surface, expected to open 2026-09-14 | EXTERNAL / NOT YET AVAILABLE |
| Real-user activation trial | Fresh-session reply identified as Joust and reached delivery state `delivered` | PASS (live owner trial) |
| Real official-source intake | Public Agent Index URL produced six evidence records and a persisted, explicit quality blocker instead of inventing missing prohibitions | PASS (safe partial-source behavior) |
| Real project target contract | Persisted `ProjectTarget`, mission attachment, and status reporting are covered by `test_project_target.py` | PASS (local contract) |
| Real build / test / repair loop | `test_real_build_loop.py` creates a mission branch, commits generated code, detects a failing test, repairs it, and records validated build runs | PASS (local contract) |
| Clean-clone reproduction | The real build loop executes the validated commit from a fresh temporary clone and records `reproduce_*` runs | PASS (local contract) |
| GitHub publication adapter | Typed `GitHubCliAdapter` plus approval-bound push/PR service are covered by `test_github.py` and `test_github_publish.py`; no live write was run | PARTIAL (contract; no live write) |
| GitHub project bootstrap | Existing-repository target can request a read-only `gh repo clone` through the build loop; covered by the missing-checkout test | PASS (local contract) |
| External action safety | `ExternalActionService` requires explicit approval and idempotency | PASS (local gate) |
| Explicit postmortem and reusable lessons | `record_postmortem`, `POSTMORTEM.md`, `competition_memory` | PASS (local) |
| Project-target compliance inspection | `test_project_compliance.py` proves target license/technology/repository checks and conservative `UNKNOWN` for unproven prohibitions | PASS (local contract) |
| Project command environment isolation | `test_tool_gateway.py` and `test_real_build_loop.py` prove credential filtering, safe allowlist handling, and rejection of sensitive names | PASS (local contract) |
| CLI real-project smoke | Fresh mission + temporary target through `attach-project` and `build-project` produced a validated mission-branch commit and passed clean-clone reproduction | PASS (local E2E) |
| Red-team blocker repair | `test_real_build_loop.py` proves a secret finding blocks the first commit, invokes repair, scopes evidence to the final commit, and validates the repaired result | PASS (local contract) |
| Target-bound readiness gate | `test_compliance.py` proves the V0 demo pack blocks when a real target is attached but not validated/bound to its commit | PASS (local contract) |
| Command and repair safety | `test_real_build_loop.py` proves negative repair budgets and credential-shaped command arguments are rejected; terminal failure status is persisted | PASS (local contract) |
| Target-bound submission E2E | `test_project_submission.py` proves a validated target produces repo/branch/SHA/diff-bound artifacts and reaches readiness only with clean-clone test/demo evidence | PASS (local E2E) |
| Known-deadline compliance | `test_project_compliance.py` proves future deadlines pass and expired deadlines fail | PASS (local contract) |
| Persistent competition controller | `test_compete_loop.py` proves ordered seven-stage cycles, evidence requirements, measured deltas, repetition, and terminal status | PASS (local contract) |
| Observation plane | `test_observation_plane.py` proves deadline/rule/Git/build/change/check/deployment/score capture into durable evidence and cycle advancement | PASS (adapter contract; no live remote observation) |
| Competition action dispatch | `test_competition_actions.py` proves idempotent durable dispatch of a selected `BUILD_PROJECT` action through `RealBuildLoop`, including failure recording | PASS (local E2E) |
| Live Hermes project construction | Mission `4881b861-a3a6-41e9-8f2d-0ed150c49f76` dispatched Hermes, created `README.md`, `entry.py`, and `test_entry.py`, committed `46e82c4adf5799baf211e847b03c1e2f862cfe23`, passed 16 generated tests, and recorded passing `test` plus `reproduce_test` runs | PASS (live model-backed local E2E) |
| Live persistent compete mission | Mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` completed multiple compete cycles, resumed durable stages, and opened subsequent cycles | PASS (live runtime) |
| Real competition research | Typed `RESEARCH` captured live official Agent Index pages as visible-text evidence; empty content fails and `CUSTOM` remains no-op only | PASS (live read-only) |
| Planner timeout resilience | Safe-mode planning is bounded; timeout records a deterministic fallback and selected local verification instead of stalling the mission | PASS (live runtime) |
| Live target verification | Six install/test and clean-clone reproduction runs passed; the no-diff review defect was found, repair was interrupted, and verification-only support was added | PASS (live commands; corrected contract locally tested) |
| Interrupted action recovery | Restart closes an orphaned `RUNNING` execution durably and advances the cycle without duplicate execution | PASS (local contract + live recovery) |
| Structured leaderboard/usage signal | Live page returned dynamic `Loading…`; no rank/install/usage value was inferred | PARTIAL / ADAPTER NEEDED |
| Joust contract foundation | `test_joust_contracts.py` proves status/phase separation defaults, typed competition metadata, persisted entrant attribution, rule supersession, and strategy-reassessment events | PASS (local contract) |
| Competitions Joust has never seen | Three live Devpost hackathons (`revenuecat-shipaton-2026`, `agentsforhumans`, `amazonappdev2026`) each locked a spec with 55-137 evidence records and a deadline matching the independently published `devpost.com/api/hackathons` submission period | PASS (live read-only, 2026-09-14) |
| Unreadable source is not a ruleless competition | `kaggle.com/competitions/.../rules` renders client-side and is reported `UNREADABLE: no_extractable_text`; typed reasons cover status, empty body, challenge, unreachable, size | PASS (live boundary preserved) |
| Install preconditions checked before the build | `scripts/preflight.py` from a bare clone of public `main` at `13c10dd`: git, Docker 29.1.3, Compose v2.40.3, daemon, credential mode `0o600`, `AGENT_ID` — ready, exit 0 | PASS (clean external clone) |
| Live competitive standing | `/v1/agent?agent_id=galahad-hackathon` returned `installs {attempted: 3, succeeded: 0}`, `users 1`, `token_usage 3119664`, `blessed_at ""`; 38 agents registered, 1 Verified | OBSERVED (not verified, unranked) |
| Public release reaches installers | Public `main` moved `f0b1e86` → `13c10dd`, read back from the remote; `raw.githubusercontent.com` serves the new README step and `scripts/preflight.py` (HTTP 200) | PASS (public) |
| Unit/integration/E2E/secret/license quality | 127 tests, Ruff, diff check, MIT license | PASS |

## External handoff

The line-scoped `plow-credentials` has been generated with `plow-agents`, a
stable `AGENT_ID` has been selected, the live compose runtime is up, the branded
response retest passed, and the public community entry is reporting usage.
After the Verified program opens, request that status on the Agent Index entry.
Joust still will not
accept legal terms, publish, or submit without explicit confirmation immediately
before that irreversible action.
