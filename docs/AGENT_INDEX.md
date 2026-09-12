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

Generate the credential locally with `plow-agents login`, select a free line
with `plow-agents lines`, and run `plow-agents mint <line-id>`. The resulting
`./plow-credentials` file is secret-bearing and must remain outside GitHub.

To update the client, review the upstream change, replace both the 40-character
commit and SHA-256, build the image, and run the service tests.
