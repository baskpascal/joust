# Galahad

Galahad is an evidence-first Hermes agent that helps a team understand,
research, plan, build, attack, repair, and package a hackathon entry.

Its promise is simple: **give it a hackathon; it tries to win it.**

## Architecture

This repository is a Plow agent variant. It builds from the immutable official
`plow-hermes-agent` image and owns only Galahad's persona, skills, deterministic
mission kernel, tests, docs, and Agent Index reporter. Generic Hermes/Plow
runtime behavior is not forked here.

Mission state is persisted in SQLite. Artifacts are written to the filesystem.
State transitions and DAG scheduling are deterministic code; model-backed
capabilities must return schema-validated data before they may influence state.

## Developer quick start

Requirements: Python 3.11+ and Pydantic 2.x.

```bash
python -m hackathon_competitor.cli db migrate
python -m hackathon_competitor.cli mission create --url tests/fixtures/hackathon/official.html
python -m hackathon_competitor.cli mission resume <mission-id>
python -m hackathon_competitor.cli mission show <mission-id>
python -m hackathon_competitor.cli mission refresh-rules <mission-id> --url <official-url>
python -m hackathon_competitor.cli doctor
```

Use `HACKATHON_COMPETITOR_HOME` to override the default local state directory.

## Run on Plow

1. Install `plow-agents` and mint a line-scoped `plow-credentials` file.
2. Set `AGENT_ID` to the agent's registered Agent Index id. Never guess it.
3. Run `docker compose up --build -d`.

Final contest submission, legal attestations, public pushes, and production
deployments are never performed by the local mission pipeline. They remain
explicitly confirmation-gated actions.

The image includes the official Agent Index client pinned by commit and
SHA-256 and runs it under `s6` every five minutes. Credentials, prompts,
mission content, and file paths are not sent by Galahad's reporting service.

See [docs/SDD.md](docs/SDD.md), [docs/DECISIONS.md](docs/DECISIONS.md), and
[docs/RUNBOOK.md](docs/RUNBOOK.md).
