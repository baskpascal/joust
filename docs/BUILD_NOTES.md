# Build notes

## 2026-09-12 — Bootstrap and first vertical slice

- Inspected the empty workspace, the attached SDD, official
  `plow-pbc/plow-hermes-agent` commit
  `8710797b6409c77df560c6198407765d138ea617`, and the current official
  downstream variant/Agent Index pattern.
- Converted the workspace from a temporary base clone into a downstream
  Galahad variant; generic Plow/Hermes runtime files were removed because they
  are upstream-owned.
- Added MIT licensing, secret hygiene, a pinned official Agent Index client,
  SHA-256 verification, `s6` supervision, explicit `AGENT_ID`, persona, and six
  validated operational skills.
- Added Pydantic contracts, three SQLite migrations/repositories, append-only events,
  deterministic state transitions, persistent DAG scheduling, cycle detection,
  retry/crash recovery, provider-neutral LLM protocol, CLI, and doctor command.
- Implemented the fixture-backed path from URL through locked and independently
  cross-checked rules, evidence, contradiction handling, 20 ideas in five
  clusters, six evaluator roles plus meta-judge, selected strategy,
  architecture tournament, planning artifacts, Git-checkpointed executable
  demo, experiment, five-role red team, repair tasks, demo/pitch tournaments,
  compliance, submission pack, status, rules refresh, and restart.

Verification:

- `quick_validate.py` — all six skills valid.
- `pytest -q tests/` — 47 passed.
- `ruff check hackathon_competitor tests` — passed.
- `git diff --check` — passed (Windows line-ending notices only).
- `docker compose config --quiet` with `AGENT_ID=galahad` — passed.
- Git Bash `bash -n image/s6-overlay/s6-rc.d/agent-index/run` — passed.
- Downloaded official client hash —
  `633ad3bc24a51d6b7dcfaae319983ab174d9853a525237d99cac64878452560c`,
  matching `vendor/client.pin`.
- Real container E2E — mission created in one container and resumed in a second:
  `READY_FOR_SUBMISSION`, 12/14 tasks succeeded, 23 artifacts, 24 evaluations,
  five recorded source tool calls, and the rehearsal task ready. The other
  outstanding task is a human-approval user trial; no external action occurred.
- Docker image build — passed from the immutable official base. Final manifest
  list: `sha256:4bf0359dd3c48e0cab4497efe9a26f7796c1232bda48c25008d0448df3a6ebc9`.
- Container `doctor` — healthy with migration v3, Git, all six skills, Plow
  discovery, explicit test `AGENT_ID`, service wiring, and no embedded credentials.

Authenticated Hermes/Plow startup was not attempted because the owner's real
line-scoped credential file and registered Agent Index id were not supplied.
Final submission and organizer verification also remain human/external gates.
