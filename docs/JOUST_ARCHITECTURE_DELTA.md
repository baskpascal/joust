# Joust architecture delta

## Source boundary

The user-supplied `JOUST — SOFTWARE DESIGN DOCUMENT` was inspected on
2026-09-13. The available attachment contains 679 lines and ends at the bare
heading `# 14`; sections after 13 are therefore unavailable and cannot be
invented. This document maps only the explicit requirements in sections 1–13.

The older Galahad SDD remains the implementation history for the currently
published Agent Index entry. Joust is treated as the next product architecture,
not as authority to silently rename or republish the live Galahad identity.

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
| Observation plane | Durable observations now capture deadline, active rules, local Git SHA/dirty state, build/change status, score signals, GitHub checks, and deployment health through read-only adapters | PARTIAL (competition-page/announcement and live adapters remain) |
| Real project | Mission branch, commit, diff hash, explicit checks, actual-file review, clean-clone reproduction | PRESENT (local E2E) |
| Target-bound submission | Repository/branch/SHA/diff-bound pack with compliance and reproduced demo gate | PRESENT (local E2E) |
| Persistent compete loop | `CompeteLoop` persists ordered stages, observations and action executions; deterministic selection, measured deltas, repeated cycles, and terminal mission status are enforced | PRESENT (local vertical slice) |
| Mission status vs phase | `MissionStatus` is separate from the backward-compatible phase field and terminal status prevents creation of another competition cycle | PRESENT (contract) |
| CompetitionSpec | Backward-compatible `CompetitionSpec` now includes type, multiple deadlines, scoring, integrations, platform, leaderboard model, sources, and uncertainty | PRESENT (contract; extraction partial) |
| Versioned CompetitionRule | Persisted lifecycle supports active/superseded/conflicted/unknown and critical supersession emits `STRATEGY_REASSESSMENT_REQUIRED` | PRESENT (contract; observation wiring partial) |
| EntrantProfile | Persisted reusable profile with GitHub/Discord/platform identities, mission attachment, export, and CLI entrypoint | PRESENT |
| ProjectTarget fields | Owner/name, dev/lint commands, deployment requirement/target, and base/final commit SHA extend the existing mandatory target boundary | PRESENT |
| GitHub live action | Adapter and approval/idempotency contracts exist; authenticated remote clone/push/PR has not been exercised for a mission | PARTIAL / EXTERNAL |
| Hermes model-backed coding | `HermesImplementer` completed a live model-backed action, created three project files, passed 16 generated tests, committed, and reproduced from a clean clone | PRESENT (live local E2E) |
| Public product identity | Live entry is Galahad; Joust naming is specified locally but not published | DECISION REQUIRED BEFORE EXTERNAL CHANGE |

## Plan ordered by dependency and risk

1. Complete authoritative competition-page, announcement, submission-state,
   usage, and leaderboard adapters; exercise GitHub checks and deployment
   health against live targets.
2. Add executors for research, submission preparation, preview deployment, and
   approval-bound GitHub publication. `BUILD_PROJECT` already routes through a
   durable action record into the existing build/repair path.
3. Permit `COMPETING -> BUILDING` reassessment without weakening terminal
   status or approval invariants.
4. Run one authenticated GitHub branch/PR rehearsal after explicit approval;
   the live model-backed local Hermes build is now proven.
5. Only after that evidence, decide whether to migrate the public Agent Index
   identity from Galahad to Joust.

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

The repository currently proves the middle local segment from an attached
target through a selected durable Hermes build action, validated commit,
observation, and submission pack. It does not yet prove authenticated GitHub
mutation, live deployment observation, or a scheduled multi-cycle autonomous
mission.

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

- The Joust/Galahad distribution repository is never inferred as a mission's
  competition-entry repository.
- External documents remain untrusted evidence, not executable instructions.
- Local reversible work is autonomous; irreversible or materially external
  consequences remain approval-bound unless a scoped preauthorization exists.
- Every public claim names authoritative evidence at the final target commit.
- No synthetic fixture may be presented as proof of a live Hermes/GitHub run.
