# Architectural decisions

## ADR-001 — Downstream Plow variant

Galahad builds from the immutable official base tag and digest for
`plow-hermes-agent` commit `8710797b6409c77df560c6198407765d138ea617`.
Generic boot, chat, Latch, and Hermes behavior remain upstream.

## ADR-002 — Agent Index integration

Use the official `plow-pbc/agent-index-client` at reviewed commit
`f900ff144076f0a766584b6ec4d0993600779b16`, verify SHA-256 at image build,
and invoke it from a supervised `s6` longrun. Galahad implements no parallel
registration/reporting protocol.

## ADR-003 — Deterministic first slice

The architectural spine is initially deterministic and fixture-testable.
`LLMClient` is a provider-neutral protocol; later model-backed capabilities
must return Pydantic-validated structured output. State never mutates directly
from prose.

## ADR-004 — Devpost workflow does not apply

The AI Worth Using / Hermes event supplied by the user is not present in the
live Devpost managed-hackathon catalog. No Devpost event identity was invented
and no unrelated registration was performed. Competition updates supplied by
the organizer are recorded as project inputs until an official Agent Index
surface exposes an authoritative rules API.

## ADR-005 — Incomplete live rule sources block visibly

Real event pages often omit deadlines, prohibitions, or machine-readable rule
markup. Galahad may infer conservative candidates from ordinary HTML, but it
must not invent missing hard rules. If the rules quality gate fails, the
  mission is persisted in `BLOCKED`, a `QUALITY_GATE_FAILED` event records the
  specific findings, and status exposes them without making downstream tasks
  ready. A missing deadline is recorded as explicitly unknown rather than
  silently treated as known.

## ADR-006 — Project target is separate from the agent repository

The repository that distributes Galahad is not the project it builds for a
competition. Each mission may attach one `ProjectTarget` in `existing_repo`,
`new_repo`, or `local_only` mode. The target records the local path, optional
GitHub URL, branch policy, and explicit install/build/test commands.

The real build path uses a mission branch, records a `RepositorySnapshot`,
captures a `ChangeSet` and `BuildRun` records, and requires a passing build or
test command before the change set is considered validated. A dirty existing
workspace is refused rather than overwritten. GitHub push, pull-request,
deploy, and merge remain separate approval-gated actions; the local build loop
does not perform them implicitly.

## ADR-007 — Joust is the next architecture, not an implicit public rename

The user supplied a new Joust SDD whose available attachment ends at section
14. Sections 1–13 supersede the product direction where they are more specific:
the system is a persistent competition agent organized around control,
execution, and observation planes and a continuing compete loop.

The deployed Agent Index identity remains Galahad until an explicit external
rebrand decision is made. Internal contracts are extended compatibly first;
the repository, agent id, and published profile are not silently renamed. The
missing portion of the truncated SDD is not inferred.
