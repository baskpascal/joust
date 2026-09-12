# Runbook

## Local development

Set `HACKATHON_COMPETITOR_HOME` to a writable directory, then run migrations,
tests, and `doctor`. The fixture E2E is offline and makes no external writes.

## Plow deployment

Mint `plow-credentials` with `plow-agents`, set the verified `AGENT_ID`, build,
and start with Docker Compose. Never place credentials in the image or Git.

## Recovery

Missions and tasks are persisted in SQLite. On process restart, stale running
tasks are changed to retryable failure and can be resumed within their retry
limit. Never delete the database to hide a failed task.

## Submission safety

Galahad may prepare artifacts automatically. Publishing or submitting remains
a confirmation-gated external action.
