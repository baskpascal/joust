# Runbook

## Local development

Set `HACKATHON_COMPETITOR_HOME` to a writable directory, then run migrations,
tests, and `doctor`. The fixture E2E is offline and makes no external writes.

## Plow deployment

Generate `plow-credentials` locally with `plow-agents login`, send the printed
activation phrase by SMS/iMessage, list lines, and mint a free line. Choose a
stable `AGENT_ID` yourself (for example, `galahad-hackathon`); Plow does not
assign it. Build and start with Docker Compose, keeping the credential file
out of the image and Git. Verified status is a separate eligibility request
that becomes available on the organizer's stated September 14 opening date.

## Recovery

Missions and tasks are persisted in SQLite. On process restart, stale running
tasks are changed to retryable failure and can be resumed within their retry
limit. Never delete the database to hide a failed task.

## Submission safety

Galahad may prepare artifacts automatically. Publishing or submitting remains
a confirmation-gated external action.
