# V0 acceptance audit

This audit distinguishes repository evidence from external conditions. A
synthetic Plow relay is used only for a boot contract test; it is not evidence
of the owner's live registration or Agent Index listing.

| SDD criterion | Evidence | Result |
|---|---|---|
| Immutable Plow variant builds | `Dockerfile`, final image digest in `BUILD_NOTES.md` | PASS |
| Runtime `/init` starts safely | s6 boot smoke with synthetic identity relay | PASS (contract) |
| Live Hermes/Plow interaction | Requires owner's authenticated relay | EXTERNAL / UNVERIFIED |
| No embedded credentials | `.gitignore`, `.dockerignore`, image/source secret scan | PASS |
| URL mission and restart | `tests/test_vertical_slice.py`, two-instance container E2E | PASS |
| DAG, retries, crash recovery | `tests/test_task_engine.py` | PASS |
| Rules, evidence, cross-check, contradiction | `tests/test_vertical_slice.py`, `test_rule_updates.py`, research fixture | PASS |
| Multi-batch ideas and tournament | strategy tests and persisted 20-idea mission | PASS |
| PRD, architecture, implementation, acceptance plan | planning artifacts and artifact graph | PASS |
| Independent evaluators and meta-judge | six strategy roles, five implementation roles plus test-gap reviewer, stored evaluations | PASS |
| Red team and improvement tasks | V0 completion path and evaluation capability | PASS |
| Submission pack and blocker gate | compliance report, install validation, final checklist | PASS (local) |
| Agent Index client pinned and integrity checked | `vendor/client.pin`, Docker build checksum step | PASS |
| Agent Index reporter supervised | `image/s6-overlay/s6-rc.d/agent-index` and image doctor | PASS (not registered in smoke) |
| Chosen `AGENT_ID` wiring | Explicit compose env, reporter, and doctor check | PASS (local) |
| Verified listing | Organizer eligibility surface, expected to open 2026-09-14 | EXTERNAL / NOT YET AVAILABLE |
| Real-user activation trial | Mission task `real_user_activation_trial` waits for approval | PENDING HUMAN |
| External action safety | `ExternalActionService` requires explicit approval and idempotency | PASS (local gate) |
| Explicit postmortem and reusable lessons | `record_postmortem`, `POSTMORTEM.md`, `competition_memory` | PASS (local) |
| Unit/integration/E2E/secret/license quality | 67 tests, Ruff, `uv lock --check`, diff check, MIT license | PASS |

## External handoff

Generate the line-scoped `plow-credentials` with `plow-agents`, choose a stable
`AGENT_ID`, then run the live-source rehearsal and user activation trial. After
the Verified program opens, request that status on the Agent Index entry.
Galahad still will not
accept legal terms, publish, or submit without explicit confirmation immediately
before that irreversible action.
