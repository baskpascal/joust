# Build notes

## 2026-09-12 — Bootstrap and first vertical slice

- Inspected the empty workspace, the attached SDD, official
  `plow-pbc/plow-hermes-agent` commit
  `8710797b6409c77df560c6198407765d138ea617`, and the current official
  downstream variant/Agent Index pattern.
- Preserved the attached SDD verbatim in `docs/SDD.md`; both files verify to
  SHA-256 `572c39001c2dffb67abf1f78fa3b085084b2647d6202f2dee17aff060170d203`.
- Converted the workspace from a temporary base clone into a downstream
  Galahad variant; generic Plow/Hermes runtime files were removed because they
  are upstream-owned.
- Added MIT licensing, secret hygiene, a pinned official Agent Index client,
  SHA-256 verification, `s6` supervision, explicit `AGENT_ID`, persona, and six
  validated operational skills.
- Added Pydantic contracts, four SQLite migrations/repositories, append-only events,
  deterministic state transitions, persistent DAG scheduling, cycle detection,
  retry/crash recovery, provider-neutral LLM protocol, CLI, and doctor command.
- Added auditable task-failure/cancellation metrics and an explicit postmortem
  record that persists outcome, artifact, and reusable cross-mission lessons.
- Completed the SDD capability surface at 48 names, including screenshot,
  video-script, and final-checklist submission capabilities. Clarified that
  `AGENT_ID` is operator-chosen, while Verified status is a separate program
  step expected to open on 2026-09-14.
- Implemented the fixture-backed path from URL through locked and independently
  cross-checked rules, evidence, contradiction handling, 20 ideas in five
  clusters, six evaluator roles plus meta-judge, selected strategy,
  architecture tournament, planning artifacts, Git-checkpointed executable
  demo, experiment, five-role red team, repair tasks, demo/pitch tournaments,
  compliance, submission pack, status, rules refresh, and restart.

Verification:

- `quick_validate.py` — all six skills valid.
- `pytest -q tests/` — 67 passed (including five deadline parameter cases).
- `ruff check hackathon_competitor tests` and `ruff format --check` — passed.
- `git diff --check` — passed (Windows line-ending notices only).
- `docker compose config --quiet` with `AGENT_ID=galahad` — passed.
- Git Bash `bash -n image/s6-overlay/s6-rc.d/agent-index/run` — passed.
- Downloaded official client hash —
  `633ad3bc24a51d6b7dcfaae319983ab174d9853a525237d99cac64878452560c`,
  matching `vendor/client.pin`.
- Real container E2E — mission created in one container and resumed in a second:
  `READY_FOR_SUBMISSION`, 12/14 tasks succeeded, 26 artifacts, 25 evaluations,
  five recorded source tool calls, and the rehearsal task ready. The other
  outstanding task is a human-approval user trial; no external action occurred.
- Docker image build — passed from the immutable official base. Final manifest
  list: `sha256:df8d9148f5d229d65543faa1c8581dd9b3c4bae054b882ff5a856c2aed43596f`.
- Container `doctor` — healthy with migration v4, Git, all six skills, Plow
  discovery, explicit test `AGENT_ID`, service wiring, Agent Index client
  smoke (`not_registered` is safely visible), and no embedded credentials.
- Runtime boot contract — with a synthetic credential and local identity relay,
  `/init` promoted credentials and started `plow-init`, `main-hermes`,
  `hermes-gateway`, and `agent-index` under `s6`; no owner credential was used.

Authenticated Hermes/Plow startup is prepared through the official
`plow-agents login` flow, but remains pending the owner's SMS/iMessage
activation. The local credential and operator-chosen `AGENT_ID` must stay out
of Git. Verified eligibility and final submission remain human/external gates.
