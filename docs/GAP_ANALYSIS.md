# Repository inventory and SDD gap analysis

## Starting point

`D:\Projects\Galahad` was empty. The official
`plow-pbc/plow-hermes-agent` repository was inspected at commit
`8710797b6409c77df560c6198407765d138ea617`, together with the current
`plow-pbc/life-assistant-hermes-agent` variant pattern and the official
`plow-pbc/agent-index-client` integration.

## Initial inventory

- Runtime/base: the official base contained generic boot, Plow Chat, Latch
  relay, seed configuration, and base persona behavior.
- Agent Index: supported by `AGENT_ID` at boot, but a reporter is variant-owned.
- Persona/skills: only generic base content existed; no competitor persona or
  hackathon skills existed.
- Product kernel: no mission models, database, DAG, evidence, decisions,
  artifacts, evaluations, CLI, or vertical-slice pipeline existed.
- Security: upstream credential handling was fail-closed. The empty project had
  no secret-ignore policy, client pin, or product threat model.
- License: the base source is Apache-2.0; the competition variant must be MIT
  while preserving upstream notice obligations.

## Required delta

The repository must be a downstream variant, not a modified copy of the base.
It therefore needs an immutable `FROM` reference, Galahad-only persona/skills,
an Agent Index service with an integrity-checked client, and the complete
mission/evidence/task/artifact spine. The first implementation slice proves
the URL-to-PRD path before the deeper backlog is added.

## Implemented V0 delta

- Immutable official base, MIT license, secret exclusions, integrity-pinned
  Agent Index client, supervised reporter, explicit `AGENT_ID`, and six
  validated Hermes skills.
- Restart-safe SQLite mission kernel, state machine, task DAG, retries,
  evidence/decision/artifact/experiment/approval models, append-only events,
  telemetry, deadline policy, and stale propagation after official rule changes.
- Safe source discovery, separate rules cross-check, contradiction handling,
  20-idea/5-cluster strategy tournament, six judge roles plus meta-judge,
  architecture tournament, planning pack, executable demo, five-role red team,
  improvement tasks, demo/pitch tournaments, compliance gate, and submission pack.
- Mission-confined file/shell/Git tools use argument vectors without shell
  expansion. Generated work is committed and the commit is recorded as an event.
- Install/run documentation is executed as a gate, mission export includes an
  artifact/hash bundle, and the doctor performs a safe Agent Index client smoke.

## External readiness still required

An authenticated `/init` boot through the real Hermes/Plow channel is now
validated in the live compose runtime with the owner's line-scoped
`plow-credentials` and the operator-chosen stable `AGENT_ID`. The credential was
generated with `plow-agents login`/`mint`; the id is not supplied by Plow. The V0
does not perform final submission, attest legal terms, or claim an
organizer-verified Agent Index listing. Verified eligibility is a separate
external step expected to open on 2026-09-14. Real-user activation and
rehearsal against the event's live official source remain explicit mission
tasks.
