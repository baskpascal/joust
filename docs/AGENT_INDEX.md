# Agent Index integration

The image downloads the official client named in `vendor/client.pin`, verifies
its SHA-256, and runs it as the unprivileged Hermes user under `s6`.

`AGENT_ID` is an operator-chosen stable identifier (for example,
`galahad-hackathon`). Use the same value for Agent Index registration and every
restart; the service stands down if it is absent. Verified status is a separate
eligibility step and does not provide or choose the id. The broad Plow
credential is supplied only to the client's one-time official registration
exchange; periodic reports use the stored Agent Index key and do not receive
the Plow token.

The public community entry is
<https://aiworthusing.com/agent-index/galahad-hackathon>. On 2026-09-12 the
rendered page showed Galahad, built by Lucas, powered by Hermes / Plow, with one
active user and 119K reported tokens. The supervised reporter independently
returned HTTP 200 for 119,363 tokens across two rows. This confirms publication
and reporting, but not Verified eligibility; the organizer says verification
opens on 2026-09-14.

Generate the credential locally with `plow-agents login`, select a free line
with `plow-agents lines`, and run `plow-agents mint <line-id>`. The resulting
`./plow-credentials` file is secret-bearing and must remain outside GitHub.

To update the client, review the upstream change, replace both the 40-character
commit and SHA-256, build the image, and run the service tests.
