# Competition Closed Loop

## Build preferences

- **Mode:** autonomous MVP closure
- **Scope:** one milestone; no new architectural expansion
- **Verification:** automated checks at every item, live evidence where external state matters
- **Git:** local commits as recovery points; no push without current approval
- **External actions:** proposal, policy decision, execution, observation, evidence

## Checklist

- [x] **1. Bind product and external identity**
  Spec ref: `Joust SDD > 12. Entrant Profile`
  What to build: Centralize Joust's product identity and bind the first observed
  `AGENT_ID` immutably in installation state. Keep `galahad-hackathon` as the
  registered external identifier while product, display name, and brand remain
  `Joust`, with command `Joust it.`
  Acceptance: Restarting with the same id succeeds; starting the same state with
  a different id fails explicitly.
  Verify: `python -m pytest tests/test_storage.py tests/test_doctor.py`

- [x] **2. Convert observations into versioned competition state**
  Spec ref: `Joust SDD > 10. Competition Spec; 11. Rule Engine`
  What to build: Implement `SourceObservation -> Extraction -> StructuredSignal
  -> Reconciliation -> CurrentCompetitionState` for rules, metrics, deadlines,
  and leaderboard signals, with source evidence and supersession.
  Acceptance: The organizer announcement supersedes the old judging rule without
  losing either source or rule version.
  Verify: Fixture and reconciliation tests prove authority ordering, conflicts,
  supersession, and an auditable current state.

- [x] **3. Ingest real Agent Index metrics**
  Spec ref: `Joust SDD > 4. Compete Loop; 5. Observation Plane`
  What to build: Add a `CompetitionMetricsReader` boundary and
  `PlowMetricsSnapshot` for rank, users, successful installs, token usage, active
  days, Verified, and capture time. Prefer the page's structured data source;
  browser/DOM parsing is a contained fallback.
  Acceptance: Missing dynamic data remains unavailable and is never converted to
  zero or a synthetic rank.
  Verify: Contract tests plus one captured live snapshot linked to raw evidence.

- [x] **4. Make monitoring cron-safe**
  Spec ref: `Joust SDD > 4. Compete Loop; 6. Hermes and Plow`
  What to build: Gate each monitor with a normalized observation fingerprint, an
  atomic expiring lease, retry backoff of 1m/2m/5m/15m/1h with jitter, and a
  durable `last_successful_observation_id`.
  Acceptance: Concurrent workers cannot run one mission cycle; unchanged state
  skips planning; collection failure produces `FAILED`, never `UNCHANGED`; a
  successful retry resets backoff without losing the last successful observation.
  Verify: `python -m pytest tests/test_monitoring.py`

- [x] **5. Feed metric deltas into strategy**
  Spec ref: `Joust SDD > 3. Design Principle; 4. Measure and Adapt`
  What to build: Compare snapshots and expose own/competitor velocity so the
  planner can distinguish acquisition, activation, retention, and usage
  bottlenecks.
  Acceptance: A fixture where competitor growth outpaces Joust changes the
  persisted bottleneck and selected next action.
  Verify: Deterministic strategy tests assert snapshot delta, interpretation, and
  action selection.

- [x] **6. Prove authenticated GitHub observation**
  Spec ref: `Joust SDD > 5. Execution and Observation Planes`
  What to build: Separate local Git state from authenticated GitHub state and
  observe account, repository access, push permission, branch protection, PRs,
  check runs, and Actions.
  Acceptance: Each unavailable permission is an explicit uncertainty; remote
  checks are stored with repository and commit SHA.
  Verify: Adapter tests and a read-only authenticated runtime rehearsal.

- [x] **7. Unify approved external actions**
  Spec ref: `Joust SDD > 8. Autonomy Policy`
  What to build: Route push, PR, deploy, Agent Index update, verification request,
  and final submission through `ProposedExternalAction -> ApprovalPolicy ->
  decision -> execute -> observe -> Evidence`.
  Acceptance: No executor runs without the required approval or scoped
  preauthorization, retries are idempotent, and success requires observed remote
  state.
  Verify: Denied, approved, interrupted, retry, and remote-mismatch tests.

- [ ] **8. Rehearse push, PR, deploy, and submission state**
  Spec ref: `Joust SDD > 2. Product Promise; 8. Autonomy Policy`
  What to build: With explicit approval, execute a mission-branch rehearsal and
  observe its actual GitHub/deployment/submission state.
  Acceptance: Remote SHA equals local SHA, checks are observed, deployment health
  is captured, and submission remains an event rather than mission termination.
  Verify: Evidence bundle from the authenticated live rehearsal.

  Live progress:
  - [x] Independent public target `baskpascal/joust-entry` created and observed.
  - [x] Mission branch pushed; remote SHA equals the validated local SHA.
  - [x] PR #1 observed open from the mission branch to `main`.
  - [x] Agent Index metadata update has an executor and a remote observer that
    re-reads the public record and fails when the Index drops a field.
  - [x] Verification request has an executor, an eligibility precondition, and
    an observer that reads `blessed_at`.
  - [x] Hosted deployment is an approval-bound handoff observed through
    `deployable_at`; it rests in `AWAITING_EXTERNAL` until Plow enables it.
  - [x] Final submission publishes the public record and verifies what the
    Index actually stored, recording that published is not Verified.
  - [ ] Both remain deterministic until a live rehearsal is authorized.

- [~] **9. Enable Hermes cron**
  Spec ref: `Joust SDD > 4. Compete Loop; 6. Hermes and Plow`
  What to build: Schedule only the monitored runner after items 1-8 pass.
  Acceptance: Repeated triggers show lease exclusion, unchanged-state token
  avoidance, bounded retries, restart recovery, and continued competition after
  submission.
  Verify: Supervised container run across multiple scheduled intervals.

  The narrow `verification_status` monitor is built and safe to schedule at a
  30-minute interval once the handoff is delivered; an external error enters the
  existing backoff rather than hammering the Index. The full competitive
  monitoring set stays off until `eligible_to_win` is true, because only then
  can an observation produce a competitive decision.

- [ ] **10. Close and publish the MVP evidence**
  Spec ref: `Joust SDD > 1. Product Definition; 2. Product Promise`
  What to build: Re-run the complete local and live acceptance suite, update the
  reviewer evidence map, and verify the public product identity is Joust while
  the external id remains `galahad-hackathon`.
  Acceptance: Every milestone definition-of-done item links to reproducible or
  observed evidence; no simulated external claim is labeled live.
  Verify: Full test suite, clean-clone bundle verification, container doctor, and
  public page inspection.

## Milestone definition of done

- [x] Raw evidence becomes versioned rules/signals.
- [x] Public competition metrics are ingested.
- [x] Metrics change mission decisions.
- [x] Monitor primitives provide fingerprint, lease, backoff, and last-success state.
- [ ] Hermes cron runs safely.
- [x] GitHub runtime is authenticated.
- [x] Remote checks are observed (the current result is an evidence-backed empty set).
- [x] Push/PR/deploy/submission use the unified approval-action contract. A kind
  counts as covered only once an executor and a remote observer exist for it,
  which is now true of all seven: `REPOSITORY_CREATE`, `PUSH`, `PULL_REQUEST`,
  `AGENT_INDEX_UPDATE`, `VERIFICATION_REQUEST`, `DEPLOY`, `FINAL_SUBMISSION`.
- [ ] Actual external results are verified end to end. GitHub repository
  creation, push, and PR are observed live. Agent Index update, verification,
  hosting, and submission are covered deterministically and await an authorized
  live rehearsal.
- [x] Product identity is Joust in local/runtime contracts.
- [x] `AGENT_ID` identity remains stable in durable installation state.

`AGENT_ID` is an immutable external identifier. It is not the product name.

## Install-path freeze

```text
VERIFICATION_CANDIDATE = c8aa38d3c81009e47495f1b154eb301ca1b9d1ea
```

Public `main` is frozen at that commit while verification is pending. Work
continues on branches; `main` moves again only for a critical reason, so the
hosts review exactly what Joust claims is ready. Every superseded proposal was
denied rather than removed, and exactly one verification request is live:
`c55d938f`, naming this candidate.

## Milestone: enter the race

Eligibility is the binding constraint, and the official page states the rule
directly: "Verified agents are installed and run by the hosts, and only
verified agents can win the hackathon", with verification starting
2026-09-14. Because verification means the hosts install and run this
repository, the install path is part of the gate.

- [x] Builder is `p_ascal`, observed on the public record.
- [x] Agent display name is `Joust`; `AGENT_ID` remains `galahad-hackathon`.
- [x] The credential is `0600` outside the repository, with the host path
  configurable and the doctor inspecting the configured path first.
- [x] The install URL serves the current entry. The previous public release
  predated the Joust rename and was 165 commits behind, so a host following
  the install path received an agent branded Galahad.
- [x] One candidate SHA holds across every surface. Verification installs and
  runs this repository once, so the candidate, public `main`, what the install
  URL serves, and the SHA named in the handoff must all be the same commit.
  The current candidate is `c8aa38d3c81009e47495f1b154eb301ca1b9d1ea`,
  reproduced from a clean clone before publication and re-observed afterwards
  from an independent clone of the install URL: HEAD matched, doctor healthy,
  full suite green, branding `Joust`, 139 files.
- [x] Exactly one verification request is live. The proposals naming superseded
  candidates were denied through the approval contract rather than edited away,
  so the event log keeps why each one was closed.
- [x] The eligibility gate is clean except Verified.
- [x] A verification request is proposed and durable, keyed on the candidate
  commit so a later candidate is a new request rather than a refusal.
- [x] A `verification_status` monitor exists, with a fingerprint of
  `verification:<agent_id>:<observed_status>`, a
  `verification-monitor:<mission_id>` lease, and the shared retry backoff. It
  is inert until a handoff is actually delivered, so scheduling it early reads
  nothing: against the live mission it returns `UNCHANGED` after zero Agent
  Index reads.
- [ ] The handoff is delivered. Delivery runs through the community Discord,
  which is unsolicited external communication and is not Joust's to send. The
  announcement gives a date for when verification opens but no time or
  timezone, so the window is treated as unconfirmed until the option is
  actually observable rather than inferred from a local date rollover.
- [ ] Verified is observed and `eligible_to_win` becomes true.

Only once `eligible_to_win` is true does the full competitive monitoring set
earn its tokens. A narrow `verification_status` monitor is useful before that,
as soon as the request rests in `AWAITING_EXTERNAL`.

## Observed competitive state

Eligibility, not cron, is the current bottleneck. The published Plow gate is
`license_is_mit and verified and reporting_healthy`. Observed live on
2026-09-14 for `galahad-hackathon`:

```text
license MIT        true
registered         true
reporting healthy  true   (token usage reaching the Index across 2 active days)
verified           false  (blessed_at is ""; 1 of 34 agents is verified)
eligible_to_win    false
rank               none   (ranking is computed over verified agents only)
users              1
successful installs 0
```

Joust cannot mark itself Verified. `joust mission index-eligibility` observes
the gate and `joust mission request-verification` produces the durable,
approval-bound handoff. Until the Index blesses the agent, the delivered
request rests in `AWAITING_EXTERNAL`, which is neither success nor failure.
