# Implementation plan

## Dependency graph

1. Variant/compliance foundation: immutable Plow base, MIT license, secret
   hygiene, Agent Index reporter.
2. Mission kernel: Pydantic contracts -> migration -> repositories -> state
   machine -> task DAG -> event log -> CLI/doctor.
3. First vertical slice: safe source ingestion -> rules/evidence/cross-check ->
   idea batches -> independent top-three evaluations -> decision -> PRD -> status.
4. Depth expansion: research registry, opportunity map, clustering, debates,
   meta-judge, deadline manager, approvals, and quality gates.
5. Execution/evaluation: workspace/tool adapters, architecture tournament,
   red-team/repair loop, artifact staleness.
6. Submission/hardening: complete submission pack, demo/pitch tournaments,
   runtime E2E, real-user trials, verification preparation.

## First-slice verification

- Unit: model validation, legal transitions, DAG cycle detection/retries.
- Integration: migrations, persistence, event ordering, restart recovery.
- E2E: fixture official source outranks a contradictory community source;
  prompt injection is data; blockers remain visible; 20 ideas and three
  independent reviews produce an evidence-linked strategy and PRD.
- Image: immutable base, pin checksum, `s6` wiring, explicit `AGENT_ID`, and
  secret scan.
