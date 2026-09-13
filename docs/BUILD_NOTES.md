# Build notes

## 2026-09-13 — Competition Closed Loop: live Agent Index metrics

The public Agent Index page was inspected read-only. Its own JavaScript uses
the structured API at `https://agent-index-server.vercel.app`: `/v1/agents`,
`/v1/agent?agent_id=...`, and `/v1/usage?agent_id=...`. Joust now contains a
dedicated `CompetitionMetricsReader` contract and `PlowMetricsReader`; HTML/DOM
parsing is not coupled to the orchestrator. Missing or malformed dynamic data
raises `MetricsUnavailable` rather than becoming zero.

`PlowMetricsIngestor` preserves the three raw JSON responses as source evidence,
emits typed leaderboard/metric signals, reconciles current state, and feeds the
result into `CompetitionObserver` before planning. A live read was persisted to
mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` at
`2026-09-13T23:20:15.847564Z`: one user, zero successful installs, 3,119,664
tokens, two active days, not Verified, and therefore no eligible rank. The
reconciled state is version 1 (`0227e2f5-62ea-4361-9666-00fabeaaef96`) with six
active signals. This was a public read and local evidence write only.

## 2026-09-13 — Competition Closed Loop: structured competition state

Database migration 11 adds durable raw `SourceObservation`, extraction,
structured-signal, and versioned current-state records. The new competition
intelligence reducer accepts evidence-linked `RuleObservation`, `MetricSignal`,
`DeadlineSignal`, and `LeaderboardSignal` contracts. Reconciliation applies the
documented authority hierarchy and recency: a newer organizer announcement can
supersede official rules, while a third-party contradiction is retained as
`CONFLICTED` without replacing active state.

The observation plane now reads the reconciled deadline, active rules, metrics,
and leaderboard values. Tests model the supplied judging update and prove that
`TOP_10_HUMAN_REVIEW` becomes superseded by `LEADERBOARD_ONLY`, the September 23
snapshot is typed, and the `galahad-hackathon` leaderboard signal remains linked
to raw evidence. This slice does not claim live Agent Index metric ingestion;
that is the next checklist item.

## 2026-09-13 — Competition Closed Loop: reliable identity and monitor gate

The MVP closure plan is now tracked in `docs/COMPETITION_CLOSED_LOOP.md` as ten
sequenced, verifiable items. The external Agent Index key is no longer treated
as the product name: Joust centralizes product/display/brand as `Joust`, the CTA
as `Joust it.`, and binds the first configured `AGENT_ID` into SQLite
installation state. A later runtime using a different id fails explicitly, so
the registered `galahad-hackathon` identity cannot be fragmented by an
accidental rename.

Database migration 10 adds observation fingerprints, atomic expiring monitor
leases, and durable retry state. `CompetitionObserver` now separates read-only
collection from evidence persistence. `MonitoredCompetitionRunner` uses that
boundary to skip unchanged observations before planning, serialize workers,
apply 1m/2m/5m/15m/1h capped backoff with jitter, and retain the last successful
observation across failures. Collection failure and unchanged state have
different durable outcomes and events. Hermes cron remains disabled until the
remaining closed-loop gates pass.

Verification: Ruff formatting/checks passed; the full suite passed with 132
tests. The rebuilt `joust-agent:latest` image has manifest-list digest
`sha256:54224c90e6ef07750779b28229948f2b5d8358d0669b2491d09ac03eef2bb22d`.
An ephemeral image smoke test returned healthy at migration 10 with bound
`agent_id=galahad-hackathon`, `display_name=Joust`, and a matching identity
check. Active containers were not restarted and no remote mutation was
performed.

## 2026-09-12 — Bootstrap and first vertical slice

- Inspected the empty workspace, the attached SDD, official
  `plow-pbc/plow-hermes-agent` commit
  `8710797b6409c77df560c6198407765d138ea617`, and the current official
  downstream variant/Agent Index pattern.
- Started from the attached SDD in `docs/SDD.md` (source SHA-256
  `572c39001c2dffb67abf1f78fa3b085084b2647d6202f2dee17aff060170d203`) and
  documented the real-project execution extension as section 71. The current
  repository copy includes that extension (SHA-256
  `f646a65677a57ad6f0c004244fd68f1c80b477fd3610b977e3dbbf34aed0eae3`).
- Converted the workspace from a temporary base clone into a downstream
  Joust variant; generic Plow/Hermes runtime files were removed because they
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
- `docker compose config --quiet` with `AGENT_ID=joust` — passed.
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
  `sha256:9f63dbd5d62a95692aff6f6c859e4c895a8437cf489316aec563f827aa19b56c`.
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
the permission repair, the response identified itself as Joust, and delivery
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
Docker had created `/opt/joust` as `0644`, so the unprivileged Hermes user
could not traverse it to import the mission package. The image now normalizes
all package directories to `0755` and files to `0644`; the image contract test
pins the directory rule.

The rebuilt-image `doctor` also revealed two diagnostic namespace mismatches:
the Plow MCP URL is injected through the root-owned `s6` environment directory,
and Agent Index identity lives in `HERMES_HOME`, not Joust's application-state
subdirectory. Doctor now checks the non-secret presence of the runtime marker
without reading it and runs the official client smoke check against the actual
Hermes home.

The final rebuilt-image `doctor` returned healthy with migration v6, all six
skills, Plow tools available, the stable agent id present, Agent Index status
`registered`, and the credential present at mode `0600`. The supervised report
again returned HTTP 200 for 119,363 tokens across two rows.

A public source bundle builder now archives only committed content, applies the
repository's export exclusions, and validates install markers, required files,
MIT licensing, forbidden secret/state paths, and Linux control-file line
endings. A clean extracted ZIP installed the Python package, exposed the CLI,
and built the complete Docker image successfully. The builder explicitly
disables host `core.autocrlf` conversion after the first Windows smoke revealed
that carriage returns would corrupt the pinned client path.

The authenticated Plow/Latch MCP health probe was repeated after the public
bundle work. The route itself responded, but authenticated `initialize` still
returned HTTP 503, confirming that the remaining Latch gap is upstream/device
availability rather than Joust credentials or HTTP routing. Plow Chat and
Agent Index reporting remain healthy.

A local bare-remote publication rehearsal proved the intended `HEAD -> main`
push and clean clone, but also found that a normal Windows clone with global
`core.autocrlf=true` converted `vendor/client.pin` back to CRLF and broke the
Docker build. Repository attributes now force LF for the Dockerfile, pin files,
shell scripts, and every `s6` control file; the image contract test prevents
that cross-platform install regression.

The publication rehearsal was repeated from a fresh bare remote with
`core.autocrlf=true`: `HEAD` cloned as default branch `main`, the pin contained
zero carriage returns, and the Docker image built successfully from that clean
clone.

The public release was then published to
`https://github.com/baskpascal/joust` on `main`. Agent Index metadata was
updated with that repository and the README install URL, and story
`live-source-safety` was published with the `Engineering` tag. A fresh rendered
page verified the public GitHub install link, one active user, 119K tokens, and
the published use case. Verified status remains unavailable until 2026-09-14;
one-click Plow deployment and demo media remain external follow-ups.

The next execution slice now separates the competition source from the project
being built. A mission can persist a `ProjectTarget`, create a mission branch,
run an explicit argv-based implementation command, record `ChangeSet` and
`BuildRun` evidence, repair a failing test, and reproduce the validated commit
from a clean clone. The GitHub CLI adapter and publication service are covered
by contract tests; push and pull-request creation remain approval-bound and no
new live remote write was performed.

Project compliance now runs against the attached target rather than Joust's
own distribution repository. License, technology, repository, and demo checks
are evidence-based; behavioral prohibitions remain `UNKNOWN` until an explicit
audit artifact proves them, so the submission gate cannot claim compliance from
absence alone.

Project execution now also has an environment boundary: build, test, run, and
coding-agent subprocesses inherit only a small platform-safe base plus an
explicit non-sensitive allowlist. Credential-shaped names are rejected before
execution. The local suite was at 99 tests after adding a red-team repair
contract that prevents failed historical attempts from contaminating final
commit evidence, a target-bound submission readiness gate, and command
credential/repair-budget validation.

The real-project path now has its own submission writer and CLI command. It
binds every generated pack to the target repository, mission branch, commit
SHA, diff hash, and recorded build/reproduction runs. A fresh integration test
advanced a built target from `VALIDATING` through compliance to
`READY_FOR_SUBMISSION`; a known future deadline passed and an expired deadline
failed.

The post-change end-to-end smoke drove the public CLI through a fresh mission,
attached a temporary `new_repo` target, ran a file-based implementation
command, committed the mission branch, and passed the declared test both in
the working tree and in a clean clone. The rebuilt image's `doctor` is healthy
with database migration 6. The reproducible public bundle contains 112 files
; run `cli bundle` to print its current SHA-256.

## 2026-09-13 — Joust architecture delta

The available Joust SDD attachment was read in full; it contains 679 lines and
ends at the incomplete heading `# 14`. Sections 1–13 were mapped in
`JOUST_ARCHITECTURE_DELTA.md` without inventing the missing text. Compatible
contracts now separate terminal `MissionStatus` from phase, add the richer
`CompetitionSpec`, persist `EntrantProfile` and versioned `CompetitionRule`,
trigger strategy reassessment on critical supersession, and complete the
required `ProjectTarget` identity/command/deployment/SHA fields. Migration 6
adds the new profile and rule stores.

Migration 7 adds durable competition cycles. `CompeteLoop` now enforces and
persists the seven Joust stages, deterministic action selection, evidence-bound
verification, measured deltas, repeated cycles, and terminal mission status.
The suite contains 102 collected tests. This is controller evidence only: live
observation adapters, Hermes model-backed target construction, and authenticated
GitHub mission writes remain explicit acceptance gaps.

Migrations 8 and 9 add durable competition observations and action executions.
The observation plane captures deadline, rules, local Git state, build/change
state, score signals, GitHub checks, and deployment health through read-only
ports. The action dispatcher records the selected action and routes
`BUILD_PROJECT` through `RealBuildLoop` idempotently. The suite now contains 106
tests. Competition-page/announcement adapters, non-build executors, live Hermes
construction, and authenticated GitHub writes remain unproven.

## 2026-09-13 — Live Hermes construction evidence

The committed tree was rebuilt as `joust-agent:real-build` at
`sha256:6cd0e4df0484313b553d9019b1b7589b41cbdaf53df4a2a1c698a446355463df`.
Container `doctor` was healthy at database migration 9 and the Agent Index
reporter returned HTTP 200. After using the s6-managed Plow inference
environment, a Hermes one-shot returned `HERMES_READY`.

The isolated live-smoke mission
`4881b861-a3a6-41e9-8f2d-0ed150c49f76` selected and durably dispatched a
`BUILD_PROJECT` action to `HermesImplementer`. Hermes created `README.md`,
`entry.py`, and `test_entry.py`; Joust committed
`46e82c4adf5799baf211e847b03c1e2f862cfe23`. Sixteen generated unit/CLI tests
passed in the target, and the database records passing `test` and
`reproduce_test` runs at that same SHA. The first competition cycle completed
and sequence 2 began at `OBSERVE`, proving that a successful build does not
terminate the mission. No GitHub push, PR, deployment, or submission occurred.

## 2026-09-13 — Live persistent competition mission

Mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` was attached to an explicit
checkout and advanced through multiple durable compete cycles. The first retry
resumed at `ASSESS` without duplicating its observation. Live planning exposed
high provider variance, so the planner now runs in safe mode with project
rules/tools disabled, low-context input, a 60-second bound, recent-cycle memory,
and an audited deterministic fallback.

The first completed cycle exposed an evidence-integrity defect: `CUSTOM` had
claimed completion for a research-shaped action without doing research. A real
`RESEARCH` executor now fetches bounded official URLs, persists excerpts, and
fails if no readable text exists. The HTML parser now excludes script, style,
noscript, and template content. A subsequent live cycle captured visible Agent
Index copy about Verified eligibility while retaining the dynamic leaderboard
as unavailable rather than inventing rank or usage.

The deterministic planner fallback then selected local verification because no
build evidence existed. Six target `BuildRun` records passed: environment
creation, dependency installation, and tests in the working checkout, followed
by the same three phases in a clean clone. The implementation correctly
produced no diff, but the old review contract treated that as a blocker and
began an unnecessary repair. The repair process was stopped before it changed
the checkout. `ChangeSet` now has an explicit `verification_only` mode, and a
restarted runner closes an orphaned `RUNNING` execution with a durable
interruption event instead of hanging or duplicating it.

GitHub check observation now uses `gh api` rather than the unsupported
`gh pr checks --json` flag in the pinned CLI. The live container is not
authenticated to GitHub, so remote checks remain an explicit uncertainty. No
push, PR, deployment, submission, account mutation, or Verified request was
performed. The complete local suite now collects 127 tests and passes with
Ruff and `git diff --check` (line-ending notices only).
