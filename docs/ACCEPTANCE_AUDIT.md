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
| Public repository publication | `https://github.com/baskpascal/galahad`, public `main`, linked from the Agent Index entry | PASS (public) |
| Chosen `AGENT_ID` wiring | Explicit compose env, reporter, and doctor check | PASS (local) |
| Verified listing | Organizer eligibility surface, expected to open 2026-09-14 | EXTERNAL / NOT YET AVAILABLE |
| Real-user activation trial | Fresh-session reply identified as Galahad and reached delivery state `delivered` | PASS (live owner trial) |
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
| Unit/integration/E2E/secret/license quality | 91 tests, Ruff, `uv lock --check`, diff check, MIT license | PASS |

## External handoff

The line-scoped `plow-credentials` has been generated with `plow-agents`, a
stable `AGENT_ID` has been selected, the live compose runtime is up, the branded
response retest passed, and the public community entry is reporting usage.
After the Verified program opens, request that status on the Agent Index entry.
Galahad still will not
accept legal terms, publish, or submit without explicit confirmation immediately
before that irreversible action.
