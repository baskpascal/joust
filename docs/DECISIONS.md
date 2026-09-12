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
