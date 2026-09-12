# Agent Index integration

The image downloads the official client named in `vendor/client.pin`, verifies
its SHA-256, and runs it as the unprivileged Hermes user under `s6`.

`AGENT_ID` must be the real registered/verified id. The service stands down if
it is absent. The broad Plow credential is supplied only to the client's
one-time official registration exchange; periodic reports use the stored
Agent Index key and do not receive the Plow token.

To update the client, review the upstream change, replace both the 40-character
commit and SHA-256, build the image, and run the service tests.
