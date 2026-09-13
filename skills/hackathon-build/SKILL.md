---
name: hackathon-build
description: Turn a selected Galahad strategy into a PRD, architecture, implementation slices, tests, and a verified build.
---

# Hackathon build

Trace rules and evidence into product requirements, implementation, tests,
demo steps, pitch claims, and submission fields. Work in small coherent slices;
critical behavior receives tests and structured failures remain visible.

The competition source and the project being built are separate mission
objects. Before claiming a build, attach a `ProjectTarget` for an existing
GitHub checkout, a new repository, or a local-only project. Declare install,
build, and test commands as explicit argv vectors. The real build path must
create a mission branch, invoke the configured coding agent, persist the commit
and logs, run the checks from a clean clone, and review the actual diff. The
deterministic demo is a regression fixture, not evidence that the target
project was built.

Use the official Plow/Hermes ownership boundaries. Do not patch generic runtime
behavior in this variant, delete tests to obtain green output, or claim
unimplemented behavior. Use tools for builds and tests and report exact results.
