# Joust architecture delta

## Source boundary

The user-supplied `JOUST — SOFTWARE DESIGN DOCUMENT` was inspected on
2026-09-13. The available attachment contains 679 lines and ends at the bare
heading `# 14`; sections after 13 are therefore unavailable and cannot be
invented. This document maps only the explicit requirements in sections 1–13.

The older Galahad implementation remains the history of the currently running
Agent Index identity (`galahad-hackathon`). Joust is the local product identity,
not authority to silently rename or republish that external registration.

## Architectural correction

The current repository has a strong deterministic control-plane spine, but it
was originally optimized around a linear V0 artifact pipeline. The Joust SDD
requires the product to own a continuing competition mission:

```text
OBSERVE -> ASSESS -> STRATEGIZE -> EXECUTE -> VERIFY -> MEASURE -> ADAPT
   ^                                                               |
   +---------------------------------------------------------------+
```

Publishing a submission is an event inside this loop, not its terminal state.
The mission terminates only at a terminal mission status such as completed,
expired, user-stopped, or irrecoverably blocked.

## Current evidence map

| Joust requirement | Current implementation evidence | Status |
|---|---|---|
| Control plane | SQLite mission state, deterministic transitions, DAG, evidence, decisions, rules, compliance, approvals | PRESENT |
| Execution plane | `ProjectTarget`, safe filesystem/shell/Git, coding-command handoff, build/repair/reproduction, GitHub adapter | PRESENT (local) |
| Observation plane | Durable observations capture deadline, active rules, local Git SHA/dirty state, build/change status, score signals, GitHub checks, deployment health, and live official-page snapshots with non-visible HTML removed | PARTIAL (structured leaderboard/deployment/submission adapters remain) |
| Real project | Mission branch, commit, diff hash, explicit checks, actual-file review, clean-clone reproduction | PRESENT (local E2E) |
| Target-bound submission | Repository/branch/SHA/diff-bound pack with compliance and reproduced demo gate | PRESENT (local E2E) |
| Persistent compete loop | `CompeteLoop` and `CompetitionIterationRunner` resume ordered stages, record failures/interruption, use an audited deterministic fallback when Hermes planning times out, and continue to the next cycle | PRESENT (live persistent mission) |
| Mission status vs phase | `MissionStatus` is separate from the backward-compatible phase field and terminal status prevents creation of another competition cycle | PRESENT (contract) |
| CompetitionSpec | Backward-compatible `CompetitionSpec` now includes type, multiple deadlines, scoring, integrations, platform, leaderboard model, sources, and uncertainty | PRESENT (contract; extraction partial) |
| Versioned CompetitionRule | Persisted lifecycle supports active/superseded/conflicted/unknown and critical supersession emits `STRATEGY_REASSESSMENT_REQUIRED` | PRESENT (contract; observation wiring partial) |
| Structured competition state | `SourceObservation -> Extraction -> StructuredSignal -> Reconciliation -> CurrentCompetitionState` persists evidence-linked rule, metric, deadline, and leaderboard signals; authority and recency choose active values while conflicts remain visible | PRESENT (contract and deterministic fixtures; live metrics pending) |
| EntrantProfile | Persisted reusable profile with GitHub/Discord/platform identities, mission attachment, export, and CLI entrypoint | PRESENT |
| ProjectTarget fields | Owner/name, dev/lint commands, deployment requirement/target, and base/final commit SHA extend the existing mandatory target boundary | PRESENT |
| GitHub live action | Adapter and approval/idempotency contracts exist; authenticated remote clone/push/PR has not been exercised for a mission | PARTIAL / EXTERNAL |
| Hermes model-backed coding | `HermesImplementer` completed a live model-backed action, created three project files, passed 16 generated tests, committed, and reproduced from a clean clone | PRESENT (live local E2E) |
| Real research action | `RESEARCH` fetches bounded official URLs, removes script/style content, persists source evidence, and fails if no readable evidence exists; `CUSTOM` cannot claim research | PRESENT (live official pages) |
| Planner resilience | Hermes planning runs without project rules/tools/plugins, has a 60-second bound, sees recent outcomes/project summary, and falls back to a deterministic safe action | PRESENT (live timeout/fallback) |
| Verification-only build | A local action may pass configured checks and clean-clone reproduction without manufacturing a diff; this is explicit in `ChangeSet.verification_only` | PRESENT (contract; live predecessor exposed the bug) |
| Product and external identity | Product/display/brand are Joust and CTA is `Joust it.`; durable installation state rejects changes to the bound external `AGENT_ID`, which remains `galahad-hackathon` | PRESENT (external id intentionally stable) |

## Plan ordered by dependency and risk

1. Bind the immutable external identity and add observation fingerprints,
   leases, retry/backoff, and last-success state before any scheduler is enabled.
2. Add a deterministic competition-intelligence reducer: convert newly fetched
   evidence into proposed versioned rule/score/submission changes, require an
   authority/conflict decision, and update the active `CompetitionSpec`.
3. Add structured Agent Index leaderboard/usage, submission-state, and
   deployment-health adapters. Live HTML containing `Loading…` is evidence of
   an unavailable signal, not a score.
4. Authenticate and prove GitHub remote observation, then add executors for
   tests without implementation, submission preparation,
   preview deployment, and approval-bound GitHub publication. Research and
   build executors are now real; `CUSTOM` remains an explicit no-op only.
5. Run one authenticated GitHub branch/PR rehearsal after explicit approval,
   then exercise deployment observation and a second build caused by measured
   feedback.
6. Enable Hermes cron only after the monitored runner and external observation
   path pass; keep the registered `AGENT_ID=galahad-hackathon` stable.

## Findings from the live persistent mission

Mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` exercised the shipped runtime,
not a fixture-only controller:

- Cycle 1 resumed from `ASSESS`, completed all seven stages, and proved that a
  successful action opens another `OBSERVE` cycle. It also exposed that the old
  `CUSTOM` executor could overstate a research action; `RESEARCH` is now typed
  and evidence-producing.
- Cycles 2 and 3 fetched live Agent Index pages. After the parser fix, persisted
  excerpts contain visible official copy, including the September 14 Verified
  start, while the dynamic leaderboard remained unavailable as `Loading…`.
- Hermes planning varied from about 40 seconds to timeout. Safe mode reduced
  initialization overhead; a 60-second deterministic fallback now preserves
  forward progress and records `COMPETITION_PLANNER_FALLBACK`.
- Cycle 4 used that fallback and ran six real target commands: install, test,
  clean-clone install, and clean-clone test all passed. The attempt exposed that
  the build loop forced a repair when the correct result was no code change.
  The repair was interrupted before it could manufacture a diff; restart now
  closes stale `RUNNING` actions durably, and verification-only changesets are
  explicitly supported.
- GitHub checks use the compatible REST endpoint now, but the container has no
  authenticated `gh` session or `GH_TOKEN`; remote check state therefore stays
  an explicit uncertainty.

The largest remaining architectural gap is no longer “can Joust run a loop?”
It is whether observed evidence can automatically and conservatively change
rules, score signals, strategy, and the next project action without repetition
or fabricated certainty.

## Critical end-to-end path

The product claim is not satisfied by producing planning artifacts. The
minimum credible path is:

```text
competition URL
  -> authoritative CompetitionSpec and versioned rules
  -> entrant profile and explicit GitHub ProjectTarget
  -> strategy and selected build action
  -> Hermes changes the target checkout
  -> lint/build/test/repair/clean-clone verification
  -> commit-bound submission evidence
  -> approved push/PR/deploy/submission action
  -> observe checks, deployment, deadline, usage or leaderboard
  -> reassess and build again while MissionStatus remains ACTIVE
```

The repository proves the middle local segment and a live multi-cycle mission
with restart/fallback behavior. It does not yet prove authenticated GitHub
mutation, live deployment observation, structured leaderboard deltas, or a
Hermes-cron schedule guarded by leases and observation fingerprints.

## Acceptance gates for the next architecture slice

1. A clean mission created from a real competition URL records authoritative
   rules, uncertainties, deadline, scoring model, entrant, and target repository.
2. A real Hermes session changes that target repository; Joust records the base
   SHA, final SHA, diff, commands, repair attempts, and authoritative evidence.
3. With explicit approval, the mission pushes a branch and opens a PR in the
   target repository; retrying the same action is idempotent.
4. The observation plane detects the resulting GitHub checks and deployment
   state and feeds them into the next persisted competition cycle.
5. A measured result can cause a new strategy/build cycle after submission;
   only a terminal `MissionStatus` stops the loop.
6. A clean export allows an independent reviewer to reproduce every claim at
   the recorded final commit.

## Non-negotiable invariants

- The Joust distribution repository is never inferred as a mission's
  competition-entry repository.
- External documents remain untrusted evidence, not executable instructions.
- Local reversible work is autonomous; irreversible or materially external
  consequences remain approval-bound unless a scoped preauthorization exists.
- Every public claim names authoritative evidence at the final target commit.
- No synthetic fixture may be presented as proof of a live Hermes/GitHub run.
