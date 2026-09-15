---
name: hackathon-safety
description: What Joust may never read, and what to do instead, when diagnosing any failure during a mission — network, build, or otherwise.
---

# Hackathon safety

A user approving or denying a Joust action must never need to understand a
shell command, a secret, or SSL internals. This held once, and broke: asked
why a competition URL was unreachable, Joust proposed `cat
/var/lib/hermes/.env`, `env | grep ...`, and `find /etc/ssl ...`. Every rule
below exists because that happened.

## Never read, under any diagnosis

`.env` files, `plow-credentials`, SSH keys (`id_rsa`, `id_ed25519`,
`authorized_keys`, `.ssh/`), any `*_TOKEN`/`*_KEY`/`*_SECRET`/password
variable or file, auth headers, cookies, cloud credential files
(`.aws/credentials`, `.kube/config`, `.netrc`), or a broad dump of the
process environment (`env`, `printenv` with no argument, `/proc/*/environ`).
No diagnosis — not a network failure, not a build failure, not a "why did
this fail" investigation of any kind — needs any of these. If a command
would touch one, do not run it, and do not propose it as something to
approve. `hackathon_competitor.security_policy.classify_command` enforces
this mechanically wherever a command is validated in Joust's own code; the
same line applies to any command reached for outside that path.

## Network and connectivity failures

Diagnose with `hackathon_competitor.capabilities.network_diagnostics.diagnose`
(DNS resolution, TCP connectivity, TLS handshake, certificate validation,
HTTP status) instead of shell commands, environment inspection, or
filesystem traversal of certificate directories (`/etc/ssl`, `/etc/pki`,
`.ssh`). It answers "is this host reachable, and why not" from a direct,
credential-free library call, and its output
(`NetworkDiagnosticResult.to_evidence_text()`) is the plain-language account
to show, not a raw command's output.

## What a user is shown

Show intent, never shell: "Joust could not reach `<host>`. I want to check
whether the site is reachable and whether its SSL certificate is valid. No
credentials or private files will be read." Offer ALLOW ONCE and CANCEL.
The underlying command, if one is genuinely needed, belongs under an
optional "technical details" disclosure only —
`hackathon_competitor.command_approval.format_approval_prompt` produces
exactly this shape from a `ProposedCommand`.

## Approval is durable, and denial is authoritative

Anything requiring a human's yes goes through
`hackathon_competitor.command_approval.CommandApprovalService`: a durable
`PENDING` record with an id and an expiry, not in-memory session state that
can be lost between a proposal and a reply. A denial stops that action —
`execute_if_granted` refuses to run anything not currently `GRANTED` — and
must not be quietly worked around by attempting an equivalent action a
different way; check `has_active_or_denied_request` (or call
`propose_unless_blocked`, which checks it for you) before proposing another
command in the same category after a denial. An expired request must not
silently be treated as approved; it resolves to `EXPIRED` and stays stopped.

## The general rule

Safe, local, credential-free diagnostics may run automatically. Anything
that could read a secret is forbidden outright, not offered for approval.
Anything external or materially consequential (a push, a publish, a spend,
a submission) requires a human's explicit approval through a durable
request. A user approves an intention; Joust is responsible for making sure
the command underneath it actually matches that intention.
