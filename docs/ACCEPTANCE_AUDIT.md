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
| Public Agent Index entry | Rendered `/agent-index/galahad-hackathon` page showed Galahad, one active user, and 119K tokens | PASS (public community listing) |
| Chosen `AGENT_ID` wiring | Explicit compose env, reporter, and doctor check | PASS (local) |
| Verified listing | Organizer eligibility surface, expected to open 2026-09-14 | EXTERNAL / NOT YET AVAILABLE |
| Real-user activation trial | Fresh-session reply identified as Galahad and reached delivery state `delivered` | PASS (live owner trial) |
| Real official-source intake | Public Agent Index URL produced six evidence records and a persisted, explicit quality blocker instead of inventing missing prohibitions | PASS (safe partial-source behavior) |
| External action safety | `ExternalActionService` requires explicit approval and idempotency | PASS (local gate) |
| Explicit postmortem and reusable lessons | `record_postmortem`, `POSTMORTEM.md`, `competition_memory` | PASS (local) |
| Unit/integration/E2E/secret/license quality | 71 tests, Ruff, `uv lock --check`, diff check, MIT license | PASS |

## External handoff

The line-scoped `plow-credentials` has been generated with `plow-agents`, a
stable `AGENT_ID` has been selected, the live compose runtime is up, the branded
response retest passed, and the public community entry is reporting usage.
After the Verified program opens, request that status on the Agent Index entry.
Galahad still will not
accept legal terms, publish, or submit without explicit confirmation immediately
before that irreversible action.
