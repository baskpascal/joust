# Runbook

## Local development

Set `HACKATHON_COMPETITOR_HOME` to a writable directory, then run migrations,
tests, and `doctor`. The fixture E2E is offline and makes no external writes.

## Plow deployment

Generate `plow-credentials` locally with `plow-agents login`, send the printed
activation phrase by SMS/iMessage, list lines, and mint a free line. Choose a
stable `AGENT_ID` yourself (for example, `galahad-hackathon`); Plow does not
assign it. Build and start with Docker Compose, keeping the credential file
out of the image and Git. Verified status is a separate eligibility request;
the agent is eligible for the competition only after the Agent Index shows it
in the Verified section.

## Operational chat channel

The live product channel for this installation is the Plow phone line provided
by `hermes-plow-plugin`, reached through SMS. iMessage may be used during line
activation where supported. A browser ChatGPT or custom-GPT conversation is a
separate interface; it does not prove that the SMS agent received or executed
the message. End-to-end acceptance tests must send the messages through the
live SMS line and then verify the container's durable state.

## Recovery

Missions and tasks are persisted in SQLite. On process restart, stale running
tasks are changed to retryable failure and can be resumed within their retry
limit. Never delete the database to hide a failed task.

When a live source does not contain enough official rule information, mission
creation returns an inspectable `BLOCKED` status with `quality_blockers` rather
than a traceback. Add or refresh from a richer official rules source; do not
override the gate with community claims.

## GitHub runtime authentication

The container uses `GH_CONFIG_DIR=/var/lib/hermes/.config/gh`, inside the
persistent Hermes volume. Authenticate interactively with `gh auth login`; never
bake GitHub credentials into the image or commit them. When the container has no
OS keyring, `gh` stores its credential in `hosts.yml`; keep that file owned by the
Hermes runtime user with mode `0600` and keep the containing directory
owner-only. Use `gh auth logout` to revoke the stored session.

Authentication proves identity and access, but it is not action approval. Push,
PR creation, deployment, Agent Index updates, verification requests, and final
submission remain approval-bound external actions.

## Submission safety

Joust may prepare artifacts automatically. Publishing or submitting remains
a confirmation-gated external action.
