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
  outstanding mission task is a human-approval user trial; no external action
  occurred during that deterministic fixture run.
- Docker image build — passed from the immutable official base. The current
  Compose image manifest list is
  `sha256:13478d98e09f279a85b5e7655ceee3df68df9bd93459b12ba1cd28641af857e7`.
- Container `doctor` — healthy with migration v4, Git, all six skills, Plow
  discovery, explicit test `AGENT_ID`, service wiring, Agent Index client
  smoke (`not_registered` is safely visible), and no embedded credentials.
- Runtime boot contract — with a synthetic credential and local identity relay,
  `/init` promoted credentials and started `plow-init`, `main-hermes`,
  `hermes-gateway`, and `agent-index` under `s6`; no owner credential was used.

Authenticated Hermes/Plow startup was completed through the official
`plow-agents login --new-line`, `lines`, and `mint` flow. The real line-scoped
credential is mounted only at runtime and remains ignored by Git. The live
container promoted it with `plow-init`, connected the Plow Chat and email
platforms, and the pinned Agent Index client registered the chosen
`AGENT_ID=galahad-hackathon`. Its first report created a truthful zero-use
baseline; the Hermes store was created during gateway startup, so the first
early reporter pass was retried after the store became available. The optional
`agentsview` collector is not installed; the Hermes collector is the source of
truth for this image.

The owner then sent a live Plow Chat message. Hermes completed the turn in 5.8
seconds, persisted the session and response, and the delivery obligation
reached `delivered`. The next supervised Agent Index report submitted 25,710
tokens across two rows and received HTTP 200. This trial exposed a branding
defect: the first two responses reused the line's legacy `Willow` label because
the Plow Chat conversation retained its pre-fix system prompt. The Plow account
profile controls the owner's display name, not the agent line's identity, so it
remains separate from the variant. The variant persona now explicitly treats
legacy line labels as transport metadata, the image was rebuilt, and the old
conversation was preserved behind an official `session_reset` boundary. The
fresh session has the corrected identity prompt. Verified eligibility and final
submission remain human/external gates. The
separate Plow Latch MCP endpoint was returning HTTP 503 during this run, while
Plow Chat and email remained connected.

The branded-response retest passed: queued owner messages were processed after
the permission repair, the response identified itself as Galahad, and delivery
reached `delivered`. The temporary silence was caused by a root-run diagnostic
invoking Hermes' generic `_secure_dir()` default, which changed the shared
root-owned home to `0700`. The image now exports `HERMES_HOME_MODE=3770`, matching
the upstream `plow-init` shared-home contract, and the image contract test pins
that requirement against regression. Verified eligibility and final submission
remain external gates.

The public Agent Index metadata was then completed for `galahad-hackathon`.
The rendered community page at
`https://aiworthusing.com/agent-index/galahad-hackathon` showed Galahad, its
Hermes / Plow runtime, one active user, and 119K tokens. A fresh supervised
report submitted the exact current total of 119,363 tokens across two rows and
received HTTP 200. Verification is still unavailable until 2026-09-14.

A live-source rehearsal against `https://aiworthusing.com/agent-index` exposed
two research edge cases that fixtures had hidden: ordinary public copy produced
a first-person story false positive, and an incomplete official surface caused
an unhandled quality-gate exception. The heuristic now rejects narrative-heavy
blocks unless they contain explicit normative language and recognizes common
registration/reporting requirements. Incomplete rule sets persist an
inspectable blocked mission instead of advancing or crashing. The repeated live
run stored six evidence records and returned `BLOCKED` with only the truthful
finding `critical prohibitions are missing`.

The first shipped-image rehearsal then exposed a packaging permission defect:
Docker had created `/opt/galahad` as `0644`, so the unprivileged Hermes user
could not traverse it to import the mission package. The image now normalizes
all package directories to `0755` and files to `0644`; the image contract test
pins the directory rule.

The rebuilt-image `doctor` also revealed two diagnostic namespace mismatches:
the Plow MCP URL is injected through the root-owned `s6` environment directory,
and Agent Index identity lives in `HERMES_HOME`, not Galahad's application-state
subdirectory. Doctor now checks the non-secret presence of the runtime marker
without reading it and runs the official client smoke check against the actual
Hermes home.

The final rebuilt-image `doctor` returned healthy with migration v4, all six
skills, Plow tools available, the stable agent id present, Agent Index status
`registered`, and the credential present at mode `0600`. The supervised report
again returned HTTP 200 for 119,363 tokens across two rows.
