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

- [ ] **2. Convert observations into versioned competition state**
  Spec ref: `Joust SDD > 10. Competition Spec; 11. Rule Engine`
  What to build: Implement `SourceObservation -> Extraction -> StructuredSignal
  -> Reconciliation -> CurrentCompetitionState` for rules, metrics, deadlines,
  and leaderboard signals, with source evidence and supersession.
  Acceptance: The organizer announcement supersedes the old judging rule without
  losing either source or rule version.
  Verify: Fixture and reconciliation tests prove authority ordering, conflicts,
  supersession, and an auditable current state.

- [ ] **3. Ingest real Agent Index metrics**
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

- [ ] **5. Feed metric deltas into strategy**
  Spec ref: `Joust SDD > 3. Design Principle; 4. Measure and Adapt`
  What to build: Compare snapshots and expose own/competitor velocity so the
  planner can distinguish acquisition, activation, retention, and usage
  bottlenecks.
  Acceptance: A fixture where competitor growth outpaces Joust changes the
  persisted bottleneck and selected next action.
  Verify: Deterministic strategy tests assert snapshot delta, interpretation, and
  action selection.

- [ ] **6. Prove authenticated GitHub observation**
  Spec ref: `Joust SDD > 5. Execution and Observation Planes`
  What to build: Separate local Git state from authenticated GitHub state and
  observe account, repository access, push permission, branch protection, PRs,
  check runs, and Actions.
  Acceptance: Each unavailable permission is an explicit uncertainty; remote
  checks are stored with repository and commit SHA.
  Verify: Adapter tests and a read-only authenticated runtime rehearsal.

- [ ] **7. Unify approved external actions**
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

- [ ] **9. Enable Hermes cron**
  Spec ref: `Joust SDD > 4. Compete Loop; 6. Hermes and Plow`
  What to build: Schedule only the monitored runner after items 1-8 pass.
  Acceptance: Repeated triggers show lease exclusion, unchanged-state token
  avoidance, bounded retries, restart recovery, and continued competition after
  submission.
  Verify: Supervised container run across multiple scheduled intervals.

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

- [ ] Raw evidence becomes versioned rules/signals.
- [ ] Public competition metrics are ingested.
- [ ] Metrics change mission decisions.
- [x] Monitor primitives provide fingerprint, lease, backoff, and last-success state.
- [ ] Hermes cron runs safely.
- [ ] GitHub runtime is authenticated.
- [ ] Remote checks are observed.
- [ ] Push/PR/deploy/submission use approval actions.
- [ ] Actual external results are verified.
- [x] Product identity is Joust in local/runtime contracts.
- [x] `AGENT_ID` identity remains stable in durable installation state.

`AGENT_ID` is an immutable external identifier. It is not the product name.
