# Build notes

## 2026-09-15 — Cloud-ready installation boundaries

The cloud-readiness audit checked the five installation invariants. The image
contains the pinned runtime, persona, skills, and Joust package only: `.env`,
Plow credentials, GitHub `hosts.yml`, and `AGENT_ID` are absent from the image.
Compose requires `AGENT_ID` at provisioning time and stores it immutably in the
tenant's persistent Hermes home. The Agent Index reporter stands down rather
than guessing when the provisioned value is missing.

GitHub authentication remains volume-scoped through
`/var/lib/hermes/.config/gh`. A fresh named volume has no GitHub session; the
existing volume retains its session after a normal container recreation. The
CLI adapter also pins its `GH_CONFIG_DIR` to the explicit installation home,
so local host configuration cannot leak into another tenant.

The default `joust-it` and `mission create` paths now put the mission workspace
and newly generated projects under the installation's persistent tenant home.
An explicit existing-project path remains an intentional operator override for
working on a repository that already lives elsewhere. No default depends on a
developer checkout path, Windows drive, or creator home.

Evidence collected for this audit: a clean image scan found no credential or
GitHub config files; a fresh-volume CLI run migrated the database, created a
mission, and reported `GitHubConnectionStatus.connected = false`; changing
`AGENT_ID` on the same volume was rejected as immutable; and `docker compose
up --build -d` recreated the live container without deleting its persistent
home. The live container remains healthy.

## 2026-09-15 — Product language and installation-scoped GitHub identity

The reported Plow Chat failure exposed two product defects. Project answers
included `/var/lib/hermes`, container names, branch UUIDs, Python class names,
and `gh auth` details. GitHub observations also described whichever `gh`
session happened to be visible, which made it unclear whether the account was
owned by the current SMS operator or leaked from the installation creator.

The fix adds one presentation boundary in `hackathon_competitor/presentation.py`.
Normal mission answers receive product-safe facts and are rendered with
competition, project, repository, tests, GitHub, ready, blocked, paused, and
cancelled language. Explicit requests such as “show technical details”, “show
logs”, “where is it stored?”, or “which branch?” select details mode and may
show the stored diagnostics. The same renderer is a final safety net for model
text, so routine replies do not expose paths, container names, UUID branches,
internal classes, database states, or shell commands.

`GitHubConnectionStatus` and `GitHubConnectionObserver` now provide the one
canonical, token-free connection observation. The CLI's GitHub adapter pins
`GH_CONFIG_DIR` to the persistent home of the current Joust installation;
creator or host-wide `gh` configuration is never used when an installation
home is supplied. `joust mission github-status <mission-id>` returns the
structured authoritative observation. Product wording is “GitHub connected:
<login>” or “GitHub isn't connected yet.” It never assumes the SMS sender owns
that account, and repository owners continue to come from observed GitHub
data.

Regression coverage now includes normal-versus-details redaction, friendly
connected/disconnected/insufficient-permission output, token-free connection
observation, durable evidence, and separate installation config directories.
The full suite now collects 314 tests and passes; Ruff 0.15.6 is clean.

The fresh-image/fresh-volume check was run without copying `~/.config/gh`:
the new installation had no active GitHub session and did not report
`baskpascal`. Reusing the existing Hermes volume intentionally retains its
existing session, as the persistence contract requires; after a normal
`docker compose up --build -d` recreation, the same connected login was still
observed. A real second GitHub
account and the SMS acceptance transcript still require credentials and a
tester-controlled Plow line; no account or browser ChatGPT result is being
presented as evidence. The supported boundary remains one Joust installation
per GitHub identity. A shared multi-user hosted instance will need a future
OAuth/GitHub App identity model.

## 2026-09-15 — An auth failure that looked exactly like an empty answer

Running Test 15's scenario for real, inside the production container, against
a live model call surfaced a defect worse than the one it was meant to find:
`HermesOneShotReasoner.complete()` returned `HermesOneShotReasoner`'s call to
the `hermes` CLI, which on a failed request prints `HTTP 401: {"detail":
"Invalid or revoked token"}` to stdout and exits 0 rather than raising.
`json_object()`'s substring scan happily found the embedded `{"detail": ...}`
object inside that text and parsed it as a completion, so `generate_candidates`
saw a payload with no `candidates` key and reported "the model returned 0
candidates" — indistinguishable from a model that was reached and genuinely
answered with nothing. (The actual cause that day was unrelated to any of
this: a manual verification script ran through a plain `docker exec` shell,
which does not inherit `s6-overlay`'s `/run/s6/container_environment/*`
variables — only processes started through `with-contenv` do — so the token
was simply missing from that one shell's environment. Real production calls,
run under proper s6 supervision, were never affected.)

Whether or not that specific case turns out to matter operationally, the
underlying gap does: an authentication failure, a rate limit, a provider
outage, a timeout, and a genuinely empty answer are five different situations
an operator needs to tell apart, and all five used to collapse into the same
generic `AI_STRATEGY_REJECTED`. `HermesOneShotReasoner.complete()` now
classifies an `HTTP <status>` line the CLI printed *before* any JSON parsing
happens — 401/403 → `MODEL_AUTHENTICATION_FAILED`, 429 → `MODEL_RATE_LIMITED`,
5xx → `MODEL_PROVIDER_UNAVAILABLE` — and a shell timeout now raises
`MODEL_TIMEOUT` instead of a bare `TimeoutError` that `joust_it()` had no
handler for at all. `ai.json_object()` now raises a typed
`ModelResponseInvalid` (`MODEL_RESPONSE_INVALID`) — still a `ValueError`, so
existing handling keeps working — when there is no JSON object anywhere in
the text. `StrategyRejected` gained an optional `code`, defaulting to the
existing `AI_STRATEGY_REJECTED`, and `generate_candidates()` now reports
`NO_STRATEGY_CANDIDATES` specifically when a valid, parsed answer's candidate
list is empty. `joust_it()` propagates whichever code the exception actually
carries instead of overwriting it. Eleven new tests cover every one of these
paths, including that a normal answer that merely happens to start with the
word "HTTPS" still passes through untouched. The suite now collects 288
tests.

## 2026-09-15 — `joust-it` had no way to say "evolve this repository"

Preparing to actually run Test 15's protocol through the real CLI (against
the real production container, not a direct Python call) surfaced the gap:
`joust_it()` gained an `existing_project_path` parameter earlier today, but
the `joust mission joust-it` command line never exposed it. An operator could
attach a project to a mission, but had no way to tell `joust-it` itself that
a repository already exists and must be evolved rather than replaced — the
exact capability the four gaps were supposed to deliver end to end. Added
`--existing-project-path` to the `joust-it` subcommand, threaded straight
through to `joust_it()`. Two new tests cover the flag reaching `joust_it()`
and defaulting to `None` when omitted. The suite now collects 277 tests.

## 2026-09-15 — A credential resolver, so a configured operator is never asked where it is

Mid-release-verification, `docker compose build` failed on a fresh clone for
the ordinary reason: no Plow credential minted yet in that environment. The
operator's actual complaint was different and sharper — Joust already has an
explicit contract for where its credential lives (`PLOW_CREDENTIALS_PATH`,
falling back to `./plow-credentials`), so an agent should never need to
search the filesystem or ask a configured operator where their own credential
is. Two independent, slightly different implementations of that lookup
already existed (`scripts/preflight.py`'s `check_credential`, and
`cli.py`'s `credential_candidates`/`credential_check`), and neither read a
`.env` file the way `docker compose` itself does, and the `cli.py` one never
`~`-expanded a configured path at all.

Added `hackathon_competitor/credentials.py`: `resolve_credential_path()`
resolves in a fixed order — an explicit argument, `PLOW_CREDENTIALS_PATH` in
the environment, the same key read from a `.env` next to the checkout, then
the documented default — expanding `~` at every step, and never opening the
file it resolves to. `cli.py`'s `credential_candidates()` now calls this
directly for its first, most-specific candidate rather than duplicating the
lookup. `scripts/preflight.py` stays deliberately stdlib-only with no project
imports, so it grew the equivalent resolution logic in place (plus a new
`--credential-path` flag) instead of importing the shared module.

Ten new tests cover CLI-argument priority, environment priority over `.env`,
`.env` fallback, `~`-expansion, that resolution never reads the credential's
bytes (checked by pointing it at genuinely invalid UTF-8 and confirming
resolution still succeeds), and that a configured, existing credential
produces no "where is it" remedy text. The suite now collects 275 tests. No
push, PR, or release was performed as part of this entry — it precedes the
`db3b610` release verification already in progress.

## 2026-09-15 — Test 15: reconciling an existing repository, and four gaps it found

Every defect found so far shared one shape: Joust assumes it controls state
from zero and breaks when it has to reconcile state that already exists. Test
15 targeted that directly. A small, real, three-commit Python fixture repo
(`textkit`, plain `git init`, no structure of Joust's own) was seeded with
three deliberate traps: a correctly implemented `tokenize()` that must not be
rewritten, a real `TODO: implement CSV export` in `report.py` that must be
completed, and an existing `test_stats.py` case protecting old behaviour that
must not regress. Joust's own code was frozen; the operator ran
`attach-project`, gave it an unseen competition (TikTok TechJam 2026), and
issued `joust-it`.

The build succeeded — 18/18 tests passing, clean-clone verified, all three
traps handled correctly (the existing function untouched, the TODO completed,
the protected test still green) — but it succeeded despite the architecture,
not because of it, and only because the implementation step happens to have
file access that the strategy step does not. Four real gaps surfaced:

`attach-project` assumed `--default-branch main` unconditionally. `textkit`
was on `master`; the only reason the mission ran at all was an operator
override. Fixed two ways: `attach-project` now reads the checkout's actual
current branch (`git symbolic-ref --short HEAD`) and falls back to `main`
only when there is no existing repository to read at all, and `RealBuildLoop`
independently re-checks the branch it is about to work from against the
branch that is actually checked out, self-correcting (and recording a
`PROJECT_DEFAULT_BRANCH_CORRECTED` event) if a caller still got it wrong.

`strategize()` and `plan_project()` had no parameter through which an
existing repository could reach them at all — not a bug in what they did
with it, but a total absence of the input. Nothing that chooses or shapes a
strategy could reference `tokenize()`, the real TODO, or the protected test,
no matter how capable the underlying model was. A new `RepositoryContext`
model and a read-only `inspect_repository()` (`capabilities/repository_context.py`)
build a bounded snapshot — language/framework, file tree, README excerpt,
test files, public API surface (via `ast`, never executed), open TODOs,
current branch, and commit metadata — entirely through static reads and
read-only `git` calls, with a dedicated test proving that even a repository
whose `conftest.py` and `setup.py` both `raise SystemExit` on import is
inspected safely. `generate_candidates()`, `select_candidate()`,
`strategize()`, and `plan_project()` now all accept an optional
`repository_context` and, when one is given, are told explicitly to build on
`existing_public_api` and `open_todos` rather than propose a disconnected
product. `joust_it()` gained an `existing_project_path` parameter that
inspects the repository once before any strategy is proposed, threads the
resulting context through the whole strategy and planning pipeline, and
attaches the real directory and its real detected branch as the mission's
`ProjectTarget` — never a freshly invented `repository_name` or an assumed
`main` — closing the gap Test 15 had to route around by hand.

A competition whose deadline had already passed was previously handled by
letting the model notice it in its own rationale and build anyway — a
"considered but overridden" outcome, which is worse than not noticing, since
it looks deliberate without being acted on. `joust_it()` now compares the
extracted deadline against the current time before any model is ever asked
what to build and raises a `COMPETITION_CLOSED` block if it has passed; a
deadline with no timezone information is left uncompared rather than guessed
at, consistent with how deadline extraction already treats timezone
uncertainty elsewhere.

`GitWorkspace.checkpoint()` ran `git add --all` unconditionally, which
respects `.gitignore` but does nothing when a repository's own `.gitignore`
is incomplete — exactly the state a real partially-built repo can be in.
`checkpoint()` now checks, before staging, whether common generated-artifact
patterns (`.egg-info`, `__pycache__`, `.venv`, `node_modules`, `dist`,
`build`, and similar caches) exist unignored in the tree, and if so appends
them to `.gitignore` (creating one if none exists) before staging — using a
direct `subprocess` call rather than the shared shell tool, since
`git check-ignore` returns a legitimate non-zero exit code for "not ignored",
which the shared tool would otherwise treat as a command failure.

Eight new tests cover the branch auto-detection, the `.gitignore` repair, the
`RepositoryContext` inspection (including the safety property that inspecting
a repository must never execute anything from it), the `COMPETITION_CLOSED`
gate, and the new `repository_context` wiring through the strategy pipeline
and `joust_it()`'s attach-existing-project path — the suite now collects 264
tests. No push, PR, or release was performed as part of this entry.

## 2026-09-15 — The brand identity was drawn, validated, and then left unused

Three of the project's own pixel-art banners — `joust-duel.png` (a collision
at the tilt) and `joust-scenes.png` (helm, prize-giving, favour) — were
generated and validated in an earlier session (see "Rasterised silhouettes"
and "Shading" below) at the exact same 1260-1280×420, 3:1 frame as
`joust-hero.png`. Only the hero ever made it into the README; the rest of
the page was plain text after it, which is what prompted the question this
entry answers. Added the duel banner at the turn into "Evidence" and the
scenes strip as the closing bookend before "Inside" — the same width, the
same aspect, no new shape introduced. `joust-marks.png` (the mark sheet) is
linked from "Inside" as a reference rather than inlined as a fourth banner,
since it is a design-system sheet, not a scene, and reads wrong at banner
width. `joust-card.png` is exactly 1200×630 — the standard OpenGraph/social-
preview size — and belongs in the repository's own social-preview setting,
not in the page; that is a GitHub Settings action, not a file this repo can
push.

Checking the render (GitHub's markdown API, rendered through a headless
Chromium at realistic content width, the same method "Looking at the README
instead of shipping it" used) is what caught that the Evidence table was
also nearly a day stale: it credited three competitions with "3 strategies"
each, when the actual evidence by now is stronger and more specific — real
projects built, repaired, and passing tests (`dryday` 11/11, `issue-pilot`
4/4, both clean-clone verified), a live demonstration of the strategy-pivot
fix (a `redirect` that actually moves the built project, not just the
label), and the three-concurrent-mission isolation result. Rewritten to say
what actually happened, with commit SHAs.

Validating this the way the project always does — reproducing the exact
install path, not just reading the diff — surfaced a real, previously
undetected regression: `build_public_bundle` and
`validate_install_run_documentation` both required the literal substring
"docker build" in the README, but the real README has said
`docker compose up --build -d` since an earlier rewrite. `joust cli bundle`
has been silently broken against the real README ever since; nothing
caught it because every existing test for either function used a synthetic
fixture, never the actual file. Fixed by accepting either phrasing — a bare
`docker build` and the compose equivalent are both a real, current answer
to "how does the image get built," and the deterministic fixture path's own
generated submission README still legitimately says `docker build .`
literally, so picking one to require would have broken the other real
caller. A new test runs validation against the real README directly rather
than a fixture, so this cannot go stale silently again.

Tests passing, ruff clean, `joust cli bundle` verified working against the
real committed tree.

## 2026-09-15 — A Plow Chat safety incident, and the boundary of what this fixes

A real incident, reported live: diagnosing why a competition URL
(lablab.ai, the IBM Bob 2 hackathon) was unreachable, an agent proposed
`cat /var/lib/hermes/.env`, `env | grep ...`, and `find /etc/ssl ...`. The
user sent `/deny`. Plow Chat answered "No pending command to deny." The
agent continued anyway.

**What this fixes, honestly.** Plow Chat's own approval UI — the surface
that lost the pending request and answered `/deny` with an ambiguous
failure — lives in the Hermes gateway, in the base image
(`plow-pbc/plow-hermes-agent`), not in this repository. This repository
has no access to that code and cannot patch the specific race condition in
it. What it can do, and what was built: make the dangerous command
unnecessary and unreachable from Joust's own side, and build the durable
approval primitive Joust's own code needs, so that anywhere Joust itself
proposes or gates a risky command, the failure mode in the incident cannot
recur. This is prevention and a correct pattern to point at, not a claim of
having patched Hermes's own UI.

**`security_policy.classify_command`** — the actual live commands
classified, and rejected before any approval prompt would exist:
`.env`, `plow-credentials`, SSH keys, `*_TOKEN`/`*_KEY`/`*_SECRET`/password
patterns, cookies and auth headers, and a genuine environment dump (bare
`env`/`printenv`, or either piped into a filter) are all forbidden
outright. `printenv PATH` — naming one specific, non-secret variable — is
not; the distinction is deliberate; a dump is not the same failure as
reading one declared value. Wired into `build_loop.validate_project_commands`
so a project's own declared commands are held to the same standard as
anything proposed interactively.

**`capabilities/network_diagnostics.diagnose`** — the answer to "why is
this host unreachable" that never needed a shell in the first place: DNS
resolution, TCP connectivity, a TLS handshake, certificate validation, and
an HTTP status, as one direct library call with no filesystem or
environment access at all. Run against the actual reported host:

```
lablab.ai is reachable (HTTP 403).
DNS: resolved to 104.26.10.134, 2606:4700:20::ac43:4620
TLS: handshake succeeded, certificate valid
HTTP: responded with status 403
```

DNS, TLS, and the certificate were all fine the whole time; the 403 is a
bot/WAF block, the same pattern already documented for other Devpost-style
hosts. There was never a network or credential problem to diagnose — which
is exactly the point: a tool that answers the real question in one honest
call removes any reason to reach for `.env` or `/etc/ssl` at all.

**`command_approval.CommandApprovalService`** — the durable primitive this
incident's UI needed and evidently didn't have. A `ProposedCommand` is a
row (`propose`/`get`/`grant`/`deny`, backed by a new `proposed_commands`
table, migration 14), not session state: `get` resolves a stale `PENDING`
to `EXPIRED` on read rather than trusting whatever a caller last believed;
`deny` on an already-denied request is an idempotent no-op (a second
`/deny` must never look like a failure); `deny`/`grant` on anything else
non-pending raise a *named* status (`CommandNotPending`, carrying the
actual state) instead of the ambiguous message that caused the live
incident; nothing this service governs can run except through
`execute_if_granted`, which reads status fresh and refuses anything not
`GRANTED` at that moment. `propose_unless_blocked` makes "a denial is
authoritative" a checked precondition, not a convention: a same-category
fallback after a denial is refused (`CategoryBlocked`) before it becomes a
new request at all, not merely discouraged in prose. `classify_command`
runs inside `propose` itself, so a forbidden command never becomes
something with an id to grant or deny in the first place —
`format_approval_prompt` renders only commands that passed that gate, and
renders intent first ("I want to check whether the site is reachable... no
credentials will be read"), with the raw command as an optional technical
disclosure, never the primary text.

**`hackathon-safety`**, a new skill, is the actual point of leverage for
the specific incident: it happened in Plow Chat's own top-level
conversation, entirely outside anything this repository dispatches, which
means the code fixes above were never in that call path at all. Skills are
how Joust's own behavioral policy reaches the agent that *is* in that path.
It states the forbidden list, names the safe diagnostic tool for
connectivity failures, and states the approval/denial semantics, and is
cross-referenced from `hackathon-intake` and `hackathon-research` at the
exact point (an unreachable source) the incident occurred. `ClaudeCodeImplementer`
and `HermesImplementer`'s own repair/implement prompts carry the same
instruction directly, since those run a real coding agent with real shell
access too.

Seven regression tests, one per named property
(`test_command_approval_security.py`): a network failure must not trigger
secret inspection; a denied approval must not execute; an approval request
must survive a fresh service instance untouched (durability, not session
state); the exact "no pending command" ambiguity must instead be two
distinct, named failures (`CommandNotFound` vs. `CommandNotPending`) and a
second `/deny` must be a no-op, not an error; a denial must block an
equivalent same-category fallback before it is even proposed; a forbidden
command must never become an approvable request at all; and an expired,
undecided request must resolve to `EXPIRED` and stay refused, never be
treated as silently approved.

**Re-running the actual flow**: `joust mission joust-it --url
https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon` now completes cleanly
end to end — lablab.ai answered normally this run (the WAF block above was
not present this time, so the original failure did not reproduce on
demand). 3 strategies, `ClauseWatch` selected on a concrete, rules-grounded
rationale, reached `BUILDING`. No secret file was read, no environment
dump occurred, and no shell command was ever shown to a user during this
run — which is consistent with the fix, not proof of it, since the
condition that triggered the incident (an actually-blocked fetch) did not
occur this time. The six tests above are what actually exercises the fix
under that condition, deterministically, rather than waiting for a live
403 to happen to recur.

242 tests passing, ruff clean.

## 2026-09-15 — Three missions at once: clean isolation, one more crash site found

Three competitions run truly concurrently — the same shared `state.db`, the
same shared project-pool directory, overlapping `claude -p` subprocesses —
against genuinely unseen ground: Amazon's Developer Hackathon, RevenueCat's
Shipaton, and (once a wrong first guess at its URL produced an honest
`SOURCE_UNREADABLE` 404) DevNetwork's API+Cloud+AI Hackathon, whose deadline
had already passed. `joust mission joust-it` ran all three at once;
`build-project` then ran two of them at once against real, distinct
`ClaudeCodeImplementer` specifications.

**Isolation held.** Every check that could show contamination came back
clean: each mission's three `ModelInvocation` records (generation, selection,
planning) carried exactly its own `mission_id`, with no cross-wiring. The two
concurrent coding-agent processes ran against a Kotlin/Gradle expense-split
domain module and a TypeScript/MCP check-in server respectively, each
correctly `--add-dir`-scoped to its own project directory, with zero bleed
of one specification into the other's files. `PRAGMA integrity_check`
returned clean after all of it. The one soft finding: all three missions
share the same `Mission.workspace_path` (the operator's cwd, since none was
started with an explicit `--workspace`) — inert here because
`--projects-root` was passed explicitly every time, but a real gap if
anything ever resolved a path from `workspace_path` directly. Devnetwork's
already-closed competition produced `RULES_NOT_EXTRACTABLE` rather than a
built strategy — an honest failure, not proof Joust noticed the deadline had
passed (the page's own rule-prose likely fell under the same-page
extraction, not a checked date).

**One more crash site, same class as the last one.** ClassSplit's own plan
declared `./gradlew` as its test command; the coding agent never generated
the wrapper script, so the very first `./gradlew --version` raised
`FileNotFoundError`. `RealBuildLoop._run_commands` and `_reproduce` — a
different pair of call sites than the `competition_actions.execute_selected`
one fixed earlier today, but the identical bug — only caught
`(RuntimeError, TimeoutError)`, so it escaped uncaught and crashed the whole
`build-project` invocation on attempt one, never reaching repair. Broadened
both to `except Exception`, the same reasoning as before: an operational
failure becomes a captured, evidenced `BuildRun` that can trigger a real
repair; only a genuine interrupt still propagates. Confirmed live: the exact
same mission, re-run unchanged, now completes a full 3-attempt repair cycle
with the real `FileNotFoundError` in its failure record — the coding agent
still never generated the wrapper across either repair attempt, which is a
real, separate reliability gap in that implementer worth its own
investigation, not something patched over here.

Kinkeeper's build failed too, for an unrelated and already-correctly-handled
reason (`eslint.config.*` vs the installed ESLint v10's expected format) —
three genuine repair attempts, all exhausted, a legitimate implementer
shortcoming rather than a Joust defect.

235 tests passing, ruff clean.

## 2026-09-15 — A pivot that changed the record but not the repository

A validation program run against the frozen `3c33afa` commit (zero code
touched during any mission — see "A validation program" directly below,
and "Two unseen competitions" further down) found the most serious defect yet:
`ai_mission.redirect` changed `mission.active_strategy_id` and recorded a real,
well-reasoned AI decision, but nothing downstream ever read that field. Run
live twice against `issue-pilot`, a pivot from IssuePilot to PolicyGuard
produced the mission claiming "now pursuing PolicyGuard" — a Slack/Teams
compliance monitor — while the repository on disk kept being the GitHub-triage
bot, indefinitely, with git HEAD unmoved. The intelligence could think
correctly and the body would keep executing the mission it had just left.

The fix opens a new development line on top of the frozen commit rather than
amending it, so the frozen-test evidence stays exactly what it was when it was
observed. Four defects closed together, because the second and third were
found chasing the first live:

**The reasoner's `--max-turns 1` was failing 40-50% of live calls.** Across
Test 1 (frozen-SHA) and Test 4 (long-running adaptation) it failed six times
in one session with `Error: Reached max turns (1)`. The cause, confirmed with
`claude -p ... --output-format json`: a reasoning prompt has no legitimate
reason to use a tool, but the model sometimes tried anyway (`stop_reason:
tool_use`), spending its one turn on a call instead of an answer, sometimes
recovering on a bare retry of the identical prompt. `ClaudeCliReasoner` now
denies every built-in tool (removing the actual cause), gives a bounded
`--max-turns 3` margin rather than hiding the symptom behind a much larger
number, reads `--output-format json` to classify what actually happened
(`REASONING_PROVIDER_TURN_BUDGET_EXCEEDED`, `REASONING_PROVIDER_INVALID_RESPONSE`,
`REASONING_PROVIDER_ERROR_<SUBTYPE>`, or an unretryable
`REASONING_PROVIDER_UNAVAILABLE` for a process that never produced a
structured result), and retries the retryable classifications up to three
times with backoff, keeping every attempt's classification in the record
rather than only the last one. Five live calls after the fix: five clean
successes.

**A strategy pivot now actually moves the project.** `redirect` detects an
actual candidate change (not a reconfirmation), re-plans a real project for
the new strategy through the same `plan_project` `joust_it` uses, attaches it
as the mission's new `ProjectTarget`, and marks the previous one
`superseded_at`/`superseded_reason` instead of leaving both live and
ambiguous. `get_project_target_for_mission` now skips superseded targets, so
every reader — `compete-run`, `build-project`, the planner — picks up the new
project without being told to look anywhere different. Verified live: a
pivot to a never-before-chosen candidate (TrendSync, a content-calendar
agent, out of the three original candidates for the Agent Index mission)
produced a new project directory (`trendsync`), a new `ProjectTarget` row,
and the prior one (`issue-pilot`) marked superseded with the operator's own
instruction as the reason. `HermesCompetitionPlanner.assess` also now reads
the mission's active strategy into its own context and is told every
candidate action must serve it, closing the same class of drift one level
down in the compete loop.

**A narrow exception clause was hiding operational failures behind a slower,
indirect recovery path.** `competition_actions.execute_selected` only caught
`(RuntimeError, TypeError, ValueError, TimeoutError)`. A real stale-venv
`FileNotFoundError`, hit live while reproducing this exact scenario, escaped
uncaught, left an `ActionExecution` stuck `RUNNING`, and cost the *next*
`compete-run` invocation an entire cycle just closing the orphan before
anything could retry the actual fix. Broadened to `except Exception`: every
operational failure an executor raises now reaches a terminal state
immediately, and only a real interrupt (`KeyboardInterrupt`, `SystemExit`)
still propagates. Orphan-recovery on a stuck `RUNNING` execution remains —
for the case no exception handler can reach, a hard process kill — but it is
now the last defense, not the routine path.

**A no-diff build was blocked for lacking evidence it could not have had in
advance.** `review_project_change` required a caller to have pre-declared
`verification_only` before the build even ran — before anyone could know
whether the fix would touch source at all. Live: a real dependency
reinstall validated cleanly (twice — working tree and clean clone) with no
changed files, and was blocked anyway, forcing an unneeded second repair
round. This function only ever runs after both those validations already
passed, so a no-diff result at that point is not missing work; it is
evidence of an environment or configuration outcome rather than a code one.
It is now a non-blocking finding.

One more defect surfaced while wiring `redirect`'s new `plan_project` call
live: `json_object` raises a plain `ValueError` when a model's answer is not
JSON at all, and `except StrategyRejected` — itself a `ValueError` subclass —
does not catch its own parent type. This was not new: `joust_it`'s original
`plan_project` call site had the identical gap and had simply never hit it
live before. Both original call sites and the new one in `redirect` now
catch `ValueError`.

Ruff clean, 234 tests passing (up from 200 on the frozen commit; the 34 new
tests are one per defect above, each reproducing the exact failure observed
live rather than a shape guessed at afterward).

## 2026-09-15 — A validation program: frozen SHA, and a compete loop under a real break

Two tests run against commit `3c33afa` with a hard rule: no edit to
`hackathon_competitor` during either mission, and no manual database patch
either — a genuine failure is reported as one, not quietly fixed and hidden.

**Frozen SHA, zero intervention.** Pointed at a competition neither this
codebase nor its author had touched: the AI Builders Hackathon
(`ai-builders-hackathon-2026.devpost.com`, deadline the following day).
`joust mission joust-it` failed twice in a row with the reasoner's
`--max-turns 1` limit (see the fix above) and succeeded on an unmodified
third attempt — 3 strategies, a GitHub-issue-triage-and-PR agent selected
with a rationale that correctly keyed off the one day of build time actually
remaining in the rules text. `build-project` then ran the AI's own plan,
which called for real GitHub API writes and a real AI Gateway call against a
live throwaway repository as its own test fixture — `no mocked LLM, no
mocked sandbox` was in the specification the AI itself wrote. Neither
`GITHUB_TOKEN` nor `AI_GATEWAY_API_KEY` exists on this host, and neither was
supplied: granting a repo-scoped token and a billed API key to an autonomous
agent is exactly the kind of consequential, hard-to-reverse action that
needs an explicit go-ahead, not an assumption. The build failed after
exhausting its repair budget — correctly. 4 of 6 tests passed (pure unit
tests); the two live end-to-end tests threw a clear, actionable error
instead of mocking anything, with a comment the AI wrote unprompted: "These
are deliberately NOT skipped silently: a triage pipeline that can't be
proven against a real issue isn't done." A real terminal failure, honestly
reported, is what this test was built to distinguish from a faked pass.

**Long-running adaptation, against a real break.** A dependency was
genuinely uninstalled (`reportlab`, from the already-validated `dryday`
mission) and `compete-run` was run repeatedly with zero manual fixes. It
correctly observed the regression ("27 of 61 build checks are failing"),
proposed a targeted repair action, executed it, verified via a clean-clone
reproduction, and measured `project_readiness` moving `0.0 → 1.0` — real
observation-to-verified-fix, not just a build. No new commit resulted, and
that was the right outcome: the actual fix was reinstalling a dependency
(an environment repair), which is correctly outside git. Getting there,
however, surfaced the three defects fixed immediately below: the reasoner's
turn-budget fragility (hit twice more here), a validated no-diff commit
wrongly blocked by review, and a stale-venv crash left an `ActionExecution`
stuck `RUNNING` for a full extra cycle. The same run, exercised in parallel
on `redirect`, is what found the strategy/execution disconnect that became
the most serious fix of the four: two live pivots, each producing a
genuine AI decision, neither moving the repository at all.

None of the four defects found here were patched mid-test. They were fixed
afterward, on a new commit, which is the entry directly above this one.

## 2026-09-14 — Two unseen competitions, built and validated by a real coding agent

`joust mission joust-it` was pointed at two competitions the code had never
built a project for: OneAquaHealth IEEE (`dryday`, a water-quality compliance
report generator) and the Agent Index (`issue-pilot`, a GitHub issue triage
bot). Both reached `BUILDING` with an AI-authored `FIRST_SLICE.md`, and both
were then handed to `ClaudeCodeImplementer` to actually write.

`issue-pilot` exposed the intended failure/repair contract working end to end
without help: the model's own package.json used `vitest`, not the `ts-node`
command the plan had declared, so the project's own stored test command had to
be corrected to match what was actually built before verification meant
anything. From there the agent found and fixed a real module-resolution defect
(`NodeNext` needs an explicit `.js` import extension) and, on the next repair
round, a real API defect (`octokit.issues.list` does not exist; the method is
`listForRepo`). Final commit `646d9077` passes 4 tests.

`dryday` repeatedly failed with `OSError: [Errno 7] Argument list too long`
inside `ClaudeCodeImplementer.repair`, and the first three hypotheses were all
wrong. It was not the coding agent's own environment (trimming it to
`PATH`/`HOME` didn't fix it). It was not two heavy builds running concurrently
against a Windows-drive-backed checkout (it failed identically running alone).
Direct measurement inside the failing call finally found it: the repair prompt
was 12,358,004 characters. The project's `flake8 .` command had no exclusion
for `.venv`, so it was linting every third-party package inside the virtualenv
— Pillow, reportlab, the lot — and that output was going straight into a
command-line argument to `claude -p`, well past what `execve` will accept.

Finding it took longer than it should have because of a second, independent
defect: `_run_commands` names each phase's log file `{phase}.log` with no
disambiguation, so when a target declares two lint commands (`flake8` then
`black --check`, both phase `"lint"`), the second command's log silently
overwrites the first's. The evidence for what had actually failed was gone by
the time anyone looked at it. Reading `lint.log` after the crash showed a
small, unremarkable `black` diff and nothing to explain twelve million
characters; only instrumenting the failing call directly, rather than trusting
the log it wrote, found the real cause.

Both are now fixed. `_run_commands` suffixes a log file by occurrence
(`lint.log`, `lint-2.log`, ...) when a phase repeats, so no command's failure
is ever silently discarded. `_bounded_failure` caps what any coding-agent
prompt embeds from a captured command failure to 20,000 characters, keeping
head and tail rather than truncating blind, since the actual assertion or
traceback is usually at the end of a flood of unrelated noise — this is a
property of the pipeline now, not a fix scoped to one linter misconfiguration,
so a different runaway command in a different generated project cannot
reproduce the same failure. `dryday`'s own `lint_commands` were also corrected
to exclude `.venv`. Final commit `807df02` passes 11 tests, `flake8` and
`black --check` clean.

A third, unrelated mistake surfaced while chasing this: both projects had been
created inside the Joust repository itself (`--projects-root` pointed at a
`projects/` directory under the checkout), which put each project's own `.git`
pack data inside the tree that `test_secret_bearing_paths_are_excluded_from_git_and_build_context`
scans for secret-shaped strings — compressed git blob bytes coincidentally
matched the pattern. Both projects were moved to an independent directory
outside the repository and their `ProjectTarget.local_path` updated to match;
the full suite (200 tests) is green again. Mission-owned projects must never
live inside Joust's own source tree, for the same reason Joust must never
treat its own repository as a mission target.

## 2026-09-14 — Auditing whether a model was ever in the loop

The question was direct: does Joust use AI to compete, or does it run a
deterministic pipeline wearing that name? Tracing the execution path rather
than the class names gave an uncomfortable answer.

`llm.py` and `structured.py` define an `LLMClient`, a telemetry wrapper and a
structured runner. Nothing in the product constructs one; grep finds them only
in tests. The mission path from a URL — `run_vertical_slice` — reached no model
at all. Its twenty ideas came from a fixed dictionary of names (`Navigator`,
`Workbench`, `Coach`, `Radar`, …). Their six scores came from
`_stable_score`, which is `sha256(title).hexdigest()[:8]` mapped into
0.55-0.96. Six "independent judges" multiplied those same hashes by six fixed
weight tables, and `select_strategy` returned the largest number, with a
rationale reading "won the independent product, technical, and skeptical
reviews". `architecture_tournament` scored three fixed candidates with three
fixed arrays, so its winner was decided when it was typed.
`build_demo_project` wrote one hardcoded source string.

A model was genuinely in the loop in exactly two places, both downstream:
`HermesCompetitionPlanner.assess` asks a model to choose the next action from a
fixed enum, and `HermesImplementer` runs a real coding agent over an already
attached project. Neither decides what to build. And nothing in stored state
distinguished a model's decision from a hash's: there was no invocation record,
no provider field, and a `ChangeSet` carried no attribution.

So the product promise was being made by the parts that could not keep it.

`ai.py` is the boundary now: a provider, an `InvocationRecorder` that writes a
`ModelInvocation` for every call including the ones that fail, and
`UnavailableReasoner`, which exists so "Joust without a model" is a state you
can run rather than an argument. `capabilities/ai_strategy.py` asks a real model
for materially different strategies, validates them against the competition
they came from, refuses three restatements of one idea, and makes it choose one
with a stated reason and a reason per rejection. `plan_project` lets the model
name the repository, pick the stack and write the first slice, because those
are product decisions and putting a template there would put the imitation
straight back. `ai_mission.joust_it` is the path a competition URL now takes.

Observed, against competitions the code had never seen:

| Competition | Result |
|---|---|
| OneAquaHealth IEEE (rules page published the same day) | 3 strategies, chose `dryday`, created the project, reached BUILDING |
| Amazon Developer Hackathon | 3 strategies across the Fire TV, Bee and Ring tracks, each citing that track's own gate |
| RevenueCat Shipaton | 3 strategies; named store publication as the binding constraint, not idea quality |
| AI Worth Using Agent Index | 3 strategies; read the scoring as single-axis and planned `flakedown` around reported usage |

The ablation is the part that matters. The same command, the same URL, with
the provider replaced by `UnavailableReasoner`: mission `BLOCKED`, boundary
`AI_STRATEGY_UNAVAILABLE`, one invocation recorded as `UNAVAILABLE`, zero
strategy candidates, zero decisions, and no project directory created. Nothing
deterministic underneath produced an approximation of the same entry.

Two defects came out of running it rather than reading it. `Database._save`
takes the model as its second positional parameter, so a column named `model`
collided with it — `TypeError: got multiple values for argument 'model'` — and
the column is `model_name`. And `joust_it` built a `SourceRecord` without its
required `content_hash`, which only surfaced on the first live acceptance run.
Both are competition-agnostic; neither was a patch to make a particular
hackathon pass.

The deterministic modules are kept and now say what they are in their own
docstrings. Having the imitation in the tree, labelled, is better than having
it in the product unlabelled.

## 2026-09-14 — The Plow toolset was never connected, and nothing said so

The live container had been reporting healthily to the Agent Index for
seventeen hours — `200 {'ok': True, 'agent_id': 'galahad-hackathon', 'days': 2,
'rows': 4}` every five minutes — while carrying this beside it, at the same
interval, since the moment it booted:

```text
WARNING tools.mcp_tool: MCP server 'plow' failed initial connection after 3
attempts, parking until a reconnect is requested (state: connecting → parked):
MCPError: Server returned an error response
```

Reporting is not reachability. A rebuild from the current tree reproduced it on
a fresh boot with a freshly read credential, so it is not a stale container.
Asking the relay directly, from inside the container and with the agent's own
token, named the condition:

```text
POST $PLOW_MCP_URL  ->  401 {"detail":"Missing or invalid Authorization header"}   (no token)
POST $PLOW_MCP_URL  ->  503 {"detail":"Device is not connected"}                   (agent token)
```

The token authenticates. `api.plow.co` reports that the device behind the
minted line is not connected, which is state on Plow's side, not in this
repository. Until it is connected, the Plow toolset stays parked and the
product's first-use sentence — send a competition URL in Plow Chat and say
`Joust it.` — has nothing to run on. That is an external blocker, recorded as
one, and it is the most plausible reason an installer would conclude nothing
happened.

The agent-index reporter is unaffected and continues to report truthfully.

## 2026-09-14 — Three people tried to install Joust and none of them got it running

The Agent Index reports installs, and reading
`/v1/agent?agent_id=galahad-hackathon` gave the number that matters:
`{"attempted": 3, "succeeded": 0, "rate": 0}`. Thirty-eight agents are
registered, one is Verified, and Joust is not it. Nobody who tried has ever
reached a running agent, and nothing recorded why.

The install path asks for a lot before it gives anything back: Docker, Compose
v2, a running daemon, a credential minted from a second repository, and a
stable `AGENT_ID` — with the failures arriving minutes into an image build, or
silently, as a token the container refuses. The author hit the worst of them
himself: a checkout on a Windows drive mounted under WSL reports 0777 whatever
`chmod` is asked for, so the token stays readable by every account on the
machine.

`scripts/preflight.py` now answers all of that in a second, before anything is
built. It is stdlib-only and imports nothing from the project, because it has
to run the moment the clone finishes. It probes the filesystem for POSIX modes
rather than guessing from the path, and each failure carries the command that
fixes it.

Writing it produced the first bug immediately: on this machine `docker` is on
PATH as the WSL shim and answers every invocation with "could not be found in
this WSL 2 distro", so the check failed and advised "Reinstall Docker" — the
one action that would not have helped. A `docker` that exists but will not
answer now points at Docker Desktop's WSL integration, and vendor output is
collapsed to one line so the verdict stays visible.

`tests/test_preflight.py` covers each remedy, including the Windows-drive trap
and the shim. The README now runs the preflight between minting the credential
and `docker compose up`. Whether this changes the install rate is unknown until
the Agent Index reports another attempt; the number is 0/3 as of this writing.

## 2026-09-14 — Reading competitions Joust had never seen

The claim that Joust can enter any competition had only ever been exercised
against the Plow hackathon and against local fixtures. Pointing the intake at
four live, unrelated competitions broke it four different ways.

Every Devpost host answered with nothing at all: `urllib` sends no `Accept`
header, and the front door replies `HTTP 202` with an empty body to a request
that asks for nothing. `SourceFetcher` handed that empty string on, the parser
found no rules in it, and the mission failed with "rules lock requires at least
three official rule records" — a sentence that blames the competition for
Joust's own blindness. The fetcher now sends `Accept: */*`, the same thing any
plain HTTP client sends, and it raises a typed `SourceUnreadable` carrying a
reason (`http_status`, `empty_body`, `bot_challenge`, `unreachable`,
`too_large`, `no_extractable_text`) instead of returning a page nobody read.
A source that could not be read is unreadable, never ruleless.

The first challenge detector was worse than none. Matching the AWS WAF cookie
helper classified the complete 120KB `agentsforhumans.devpost.com/rules` page
as an interstitial, because real pages embed that script too. Challenge markers
are now specific to challenge documents and only apply below 20KB, where a stub
lives and a rules page does not.

Kaggle's competition rules render client-side: the served HTML carries 47
characters of visible text. That is a real boundary and it is reported as one —
`no_extractable_text` — rather than as a competition without rules.

Deadlines were the last gap. Typed deadline extraction needed a JSON-LD event
to supply a reference year, and Devpost publishes neither. But these hosts
state the date in full: "Submission Period: Monday, August 10, 2026 (9:00 am
Pacific Time) – Monday, September 14, 2026 (5:00 pm Pacific Time)". Full dates
are now read without a reference year, the closing date of a stated period is
taken as the deadline, and named zones ("Pacific Time") resolve alongside
abbreviations. A date published without a time or without a zone is recorded as
uncertainty rather than guessed.

Observed after the repair, against live hosts on 2026-09-14:

| Source | Result |
|---|---|
| `revenuecat-shipaton-2026.devpost.com/rules` | spec locked; 137 evidence records; deadline `2026-09-30T23:45:00-07:00` |
| `agentsforhumans.devpost.com/rules` | spec locked; 55 evidence records; deadline `2026-09-14T17:00:00-07:00` |
| `amazonappdev2026.devpost.com/rules` | spec locked; 66 evidence records; deadline `2026-10-23T12:00:00-07:00` |
| `aiworthusing.com/agent-index` | spec locked; 6 evidence records; deadline absent, not invented |
| `kaggle.com/competitions/.../rules` | `UNREADABLE: no_extractable_text` |

The three extracted deadlines agree with the independently published
`devpost.com/api/hackathons` submission periods. `tests/test_source_intake.py`
holds one regression per defect, including the false positive. The suite is 192
tests and passes with Ruff clean.

## 2026-09-14 — Looking at the README instead of shipping it

Several candidates went out carrying a README nobody had looked at. Markdown
that reads fine as source does not tell you that a two-cell table holding a
portrait beside a landscape leaves the two captions on different lines with the
cell borders showing, or that a design-system mark sheet with its own heading
duplicates the section heading above it. Rendering the file through GitHub's own
markdown endpoint, wrapping it at the real content width and looking at it,
shows all of that at once.

The fix was to stop scattering art through the page. The table is gone. There
are three banners of one width and one aspect: the hero, the collision at the
tilt cropped to the action rather than to dead sky, and one strip carrying the
helm, the prize-giving and the favour as equal panels in a single file, so no
markdown layout can misalign them. The rendered page went from 3,627 pixels to
2,758.

Both banners are generated by `build_marks.py`, which crops them out of the
scenes rather than keeping a second hand-made copy that could drift.

Candidate `f0b1e8648143836ebdcb75e4f3e096879a0a158a` was validated from the
install URL: HEAD matching, doctor healthy, full suite green, all three banners
present at the same aspect, no table. Eight superseded proposals are denied; one
is live.

## 2026-09-14 — Shading, and why the canvas preview kept dying

Flat silhouettes were a crutch. They read acceptably at a glance precisely
because they hide that nothing is modelled, and once that was said plainly the
fix was a different technique, not a better silhouette: five-step colour ramps
per material, one light direction, a per-pixel normal, ordered 2x2 dithering at
the band boundaries, and an outline in deep violet rather than black. The
portrait carries twenty-three tones where the flat scenes carried six.

The scenes were also all the same picture — night sky, sun disc, stand on the
right — and shading would not have fixed that. Each one moved instead. The
portrait is a close crop, because detail needs pixels per object and a
tournament field spread over two hundred pixels has none to spare. The prize is
a low angle in torchlight, over the victor's bare head, looking up at the royal
box. The favour is a macro at dawn: her hand, the shaft, silk knotting round it.

Assembling all of it surfaced a real defect. The Prize artboard rendered alone
but came up blank in the full canvas, with "the preview stopped answering the
editor". It was weight: dithering alternates colour every pixel, so run-length
encoding merges nothing and a 104x116 scene became 5,468 SVG rect nodes. Dense
pixel art is a raster, not a vector. A small PNG writer now emits each scene at
2.5 KB as one image node, and separately at README scale, because GitHub does
not honour a pixelated rendering hint and the file has to carry the final size.

Finding that needed the right instrument. Checking artboards by assembling them
as plain HTML never exercises the canvas runtime, so the one artboard that could
not be verified that way — the interactive parallax — was also the one carrying
an unnoticed bug: each layer was one viewport wide and ran out the moment it was
dragged. Opening the assembled canvas in a browser showed both at once.

Candidate `c8aa38d3c81009e47495f1b154eb301ca1b9d1ea` carries the filled README
and was validated from the install URL: HEAD matching, doctor healthy, full
suite green, all five images present. Seven superseded proposals are denied; one
is live.

## 2026-09-14 — Rasterised silhouettes, and the entry repository goes private

`baskpascal/joust-entry` is now private, observed as `private=true`. It was
never a second product: the SDD forbids Joust treating its own repository as a
mission target, so proving the external-action path needed an independent repo
to act on. Joust created it, initialised `main`, pushed a mission branch and
opened PR #1, and those three actions are recorded `VERIFIED`. The problem was
that its `main` had been seeded from the Joust tree, so a stale second
repository presenting itself as Joust sat on a public profile during the very
week the hosts review it. The durable evidence does not depend on it being
public.

The mounted knights, abandoned twice, now work. The technique was the fault,
not the subject. Hand-typing ASCII pixel maps produces rectangles, and a horse
silhouette is overlapping organic masses — a rump, a barrel, a chest, a neck
wedge — so typed cell by cell it came out as a slab, and raising the neck to
separate the head only turned it into a club. The scene is rasterised instead:
ellipses, polygons and thick segments snapped to the grid with no
anti-aliasing. The outline comes out right on the first pass and the shading
never had to exist, because the whole composition is silhouette against a sun.

Three render passes fixed the rest. Both lances lay at the same shallow angle
and merged into a single white rail across the image until the V was opened;
the tilt sat in the foreground like a fence until it moved between the riders,
which is what a tilt is; the riders were beheaded by the top of the grid; and
the grip pennons were painted on top of the shields.

Candidate `05c4b4aa1a02ced03af377a75b07443da6602d8a` carries the duel and the
mark set in the README alongside the hero, still ninety-three lines, and was
validated from the install URL: HEAD matching, doctor healthy, full suite
green, all three images present. Six superseded proposals are denied; one is
live.

## 2026-09-14 — A README you can finish, and a pixel identity that reads

The README was rewritten down to a hero, a paragraph, three commands, and the
single idea that separates Joust from an agent that merely says it succeeded.
Verification means the hosts install and run this repository, and a reviewer
who has to wade through a wall of developer commands to find out what the thing
is has already been badly served. Windows, standalone image builds, and
credential paths moved into a disclosure so they stop taxing the common path.

The identity settled on pixel after a pop-art screenprint pass. Both directions
are kept: the screenprint taught the type and the off-register plates, and the
pixel version inherits them — the wordmark carries a red and a blue copy one
pixel behind the black. The helm is the same great helm in both, so the
directions are one agent rather than two.

Rendering every pass and looking at it is what made this work. The lance read
as a candle until it was couched on the diagonal; a maned lion's face read as a
strawberry until it was replaced with the geometry early heraldry actually
used; the crest was an antenna, then a horizontal smear, before it rose at the
right angle; and a gold disc behind the helm was being cut square by the frame
in both the hero and the card until the sprite's nine columns of empty padding
were trimmed and the compositions re-centred.

The roster on the canvas is four real figures of the European tournament —
Marshal on the Anglo-French circuit, Richard I relicensing tournaments in
England in 1194 after the Norman suppression, Ulrich von Liechtenstein, and
Geoffroi de Charny. Their devices are geometric and drawn in the period idiom,
labelled as Joust's marks rather than reconstructions, because attributing an
invented blazon to a real man would be a fabrication like any other.

Candidate `d806783a0fc602145d0615ff86be088dde8e351a` carries all of it and was
validated from the install URL: HEAD matching, doctor healthy, full suite
green, hero present. Five superseded proposals are denied; one is live.

## 2026-09-14 — The install path gets a face, and the knights do not ship

The freeze was reopened once, deliberately, before the handoff was delivered.
Verification means the hosts install and run this repository, so the README is
part of what gets reviewed, and it was still opening on a wall of developer
commands with no statement of what Joust does. Candidate
`a82e28b81bb9446a010e33f6987ffb99b0abd05b` publishes the rewritten README and a
generated pixel-art identity, and was validated the way a host meets it: cloned
from the install URL, HEAD matching, doctor healthy, full suite green, hero
image present. The four superseded proposals are denied, one is live, and the
freeze is back on.

The art is generated rather than hand-exported. `build_marks.py` redraws the
artboards from pixel maps and `render_marks.mjs` captures the PNGs through a
scripted Chromium with an explicit clip, because window-geometry screenshots
silently cropped a quarter off the bottom of the first attempt.

Mounted knights at the tilt were attempted and abandoned after three passes.
The horses would not read: the barrel rendered as a flat slab, and raising the
neck to separate the head from the body turned it into a club. Rendering each
pass and looking at it is what made that obvious, and shipping the result would
have put weak art on the page a reviewer opens. The heraldic crest carries the
identity on its own, so the knight sprite was removed rather than published at
that quality. It remains an open thread, not a blocker.

## 2026-09-14 — One candidate SHA, and a monitor that knows it cannot read

Verification installs and runs this repository once, so the entry now holds one
invariant while it is under review: candidate SHA equals public `main` equals
what the install URL serves equals the SHA named in the handoff. Release
`fb7a22ebe20ec4bd7e27399b77ac79c5b1a7dc07` was published, then validated the way
a host would meet it — cloned from the install URL, HEAD matching, doctor
healthy, full suite green, branding `Joust`, the configurable credential mount
and the reporter service present. The proposals naming superseded candidates
were denied through the approval contract rather than deleted, so the log keeps
why each was closed, and exactly one request is live.

Building the `verification_status` monitor exposed a defect worse than the one
it was written to avoid. Polling reads the public record inside the action
service's observer, and that service treated every exception as a failed
action. A single network timeout therefore moved a delivered handoff from
AWAITING_EXTERNAL to FAILED permanently, and the monitor — which only watches
actions that are awaiting an external party — went inert forever afterwards.
The project had already learned this lesson one layer up, where a collection
failure must never read as UNCHANGED; the action layer had not.

`ExternalObservationUnavailable` now separates "the remote could not be read"
from "the remote said no". The action's status is left exactly as it was, the
event is recorded, and the next poll resumes. A test asserts that an unreadable
Index leaves the action AWAITING_EXTERNAL.

The monitor itself is deliberately dumb. It watches one flag, plans nothing,
and reads nothing at all until a handoff has actually been delivered, which is
what makes it safe to schedule before the request is sent: against the live
mission it returns UNCHANGED after zero Agent Index reads. It carries the
fingerprint, lease, and backoff the cron gate requires. The full competitive
monitoring set stays off until `eligible_to_win` is true.

## 2026-09-14 — Entering the race: public identity, credential, and release

The Plow account profile published the builder as `La brava`. `plow-agents
profile --name "p_ascal"` changed it, and the public record now reads agent
`Joust`, id `galahad-hackathon`, builder `p_ascal`. The id was deliberately not
renamed: it is registered and accumulating usage, and the Agent Index keeps the
stable id separate from the display name for exactly this reason.

The credential moved to `~/.config/joust/plow-credentials` at mode `0600`
rather than enabling `metadata` in `/etc/wsl.conf`. Compose reads the host path
from `PLOW_CREDENTIALS_PATH`, defaulting to the documented `./plow-credentials`,
and the doctor inspects that configured path first; otherwise it would keep
failing on a checkout whose container reads a correctly protected token from
somewhere else. The world-readable original was removed after confirming the
copy was byte-identical.

The real blocker was none of the above. The official rule is that "Verified
agents are installed and run by the hosts", so the install path is part of the
eligibility gate, and the install URL pointed at a public `main` that was 165
commits behind and still branded Galahad. A host installing today would have
received the wrong agent. Release
`a2a5e5a2e38240aef9d84aa46b33eae6b8e2648f` publishes the current entry as a
squashed snapshot matching the previous release pattern, carrying the 139
committed files minus `.knightwatch`. It was reproduced from a clean clone
first, 172 tests and a healthy doctor, and re-observed from an independent
clone of the public URL afterwards.

Requesting verification against that commit then exposed a real defect. The CLI
keyed the idempotency token on the agent alone, so the first handoff bound the
key permanently and every later candidate was refused as a conflicting intent.
The key now includes the candidate commit: re-requesting the same candidate is
idempotent, a new candidate is a new request. The proposal is durable and
unapproved; delivery runs through the community Discord and is not Joust's to
send.

## 2026-09-14 — Agent Index actions and the pending-external outcome

An audit of the milestone found one overstated claim. The definition of done
recorded push, PR, deploy, and submission as using the unified approval-action
contract, but `grep ExternalActionKind` reached only `approvals.py`,
`models.py`, and `github_publish.py`: `DEPLOY`, `AGENT_INDEX_UPDATE`,
`VERIFICATION_REQUEST`, and `FINAL_SUBMISSION` were enum values with no
executor and no observer. The contract is kind-agnostic, so it covered them in
principle and not in fact. The checklist now names which kinds are closed.

Two of those four are now closed. `AgentIndexService` writes public page
metadata through the pinned upstream client and verifies by re-reading the
public record, so an Index that drops a field produces a mismatch rather than a
success. Verification is an external handoff: Joust refuses to request it while
its own published gate is unmet, so the one review the competition offers is
not spent on an ineligible agent.

That required a third outcome. `ExternalActionStatus.AWAITING_EXTERNAL` and
`ObservedExternalResult.pending_external` separate "Joust delivered its side and
the other party has not acted" from both success and failure; a model validator
forbids a result that is pending and matching at once, and re-running such an
action re-observes the remote instead of re-delivering the handoff. Reporting a
delivered verification request as `FAILED` would have been as wrong as
reporting it as `VERIFIED`.

`DEPLOY` and `FINAL_SUBMISSION` followed. Hosted deployment is the same shape
as verification, so both now share one delivery path parameterized by the
public timestamp they wait on, `deployable_at` and `blessed_at`. Final
submission is different: publishing the record is something Joust can do and
therefore verify immediately, by re-reading what the Index actually stored, and
its observation records that published is not Verified so the submission stays
an event in the mission rather than its end. All seven declared kinds now have
an executor and a remote observer.

Live observation of `galahad-hackathon` on this date: MIT, registered, and
reporting healthy across two active days with 3,119,664 tokens, `blessed_at` is
`""`, and rank is absent because ranking is computed over verified agents only.
Users is 1 and successful installs is 0. Eligibility, not Hermes cron, is the
binding constraint. `joust mission index-eligibility` and
`joust mission request-verification` were both exercised live; the latter
persists an unapproved proposal carrying the rendered handoff and publishes
nothing.

One test was also wrong rather than one check. `test_doctor` asserted whole-host
health, which depends on the mode of a credential file outside the repository,
so it failed on a working tree mounted from 9p/DrvFs where `chmod` is a no-op.
The doctor's finding was correct: the file really is world-readable there. The
test now asserts the checks the process controls, and `credential_check` is
covered directly against absent, `0600`, and `0644` files. Keeping the
credential outside `/mnt` is machine configuration and does not belong in this
repository.

## 2026-09-14 — Competition Closed Loop: live GitHub mutation rehearsal

With the user's explicit approval, Joust created the independent public target
[`baskpascal/joust-entry`](https://github.com/baskpascal/joust-entry), initialized
`main` at `0beaf9e7e830645c4cac4d9fc2dec4a688c3c995`, pushed mission branch
`joust/5a26f83b-61cd-426c-ba02-878dc8c9cc38`, and opened
[PR #1](https://github.com/baskpascal/joust-entry/pull/1) against `main`. The
branch contains commit `369c41889cd29d8f87642e1909ad880e4ec4671b` and the
remote branch observer returned that exact SHA.

The three durable actions are independently recorded as `VERIFIED`:

- repository creation: `474e39f9-b9c6-4c99-9de2-70a8b99934fa`;
- branch push: `4794def0-e506-4b44-8b85-55a3a29bfd3a`;
- pull request: `362b7dea-612f-4e01-b3e8-315d1e88eaff`.

The rehearsal exposed two real adapter defects before completion. Git
authentication was not visible in the first ephemeral process because the
persistent Git-config volume was not mounted, and a detached HEAD pushing to an
empty repository required a fully qualified `refs/heads/main` destination. The
first failure left the repository empty and the action `FAILED`; retry used the
same action/idempotency key, proved the exact repository already existed, then
completed and observed initialization. A CLI preflight also caught that the
installed `gh pr create` lacks `--json`; Joust now reads its returned URL and
uses `gh pr view --json` for independent verification.

The mission now points to a persistent, independent checkout at
`/var/lib/hermes/hackathon_competitor/missions/5a26f83b-61cd-426c-ba02-878dc8c9cc38/targets/joust-entry`,
not the Joust distribution repository. A post-action snapshot at
`2026-09-14T00:53:45.105160Z` observed PR #1 open with the expected head/base,
push permission, and empty check/Actions sets. Empty means no CI exists; it does
not mean CI passed. No merge, deploy, Agent Index update, verification request,
or submission occurred. The runtime image digest is
`sha256:318bd10c0f843b0bee7cd71d76ae5ce96b8f3c9cef9cfd0552ab58e58c52ae40`.

## 2026-09-14 — Competition Closed Loop: verified external actions

Database migration 12 adds durable `ProposedExternalAction` and
`ExternalActionObservation` records. Push, pull request, deploy, Agent Index
update, verification request, and final submission now share one contract:
proposal, non-`AUTO` approval, idempotency key, execution, independent remote
observation, and evidence. A successful executor response alone never marks an
action verified.

The service rejects missing, pending, denied, expired, mismatched, and reused
approvals before execution. Verified retries return the recorded observation
without invoking the executor again. An interruption before an executor result
retries with the same external idempotency key; an interruption after the
result was persisted resumes observation without repeating the mutation. A
remote mismatch is stored as evidence and leaves the action `FAILED`.

`GitHubPublicationService` now uses this contract. Push success requires the
observed remote branch SHA to equal the validated commit; PR success requires
an observed open PR with the approved head and base. The generic action kinds
reserve the same path for deployment, Agent Index metadata, verification, and
final submission adapters rather than allowing bespoke approval bypasses.

Ruff passed and the complete test suite passed. The rebuilt runtime is healthy
on database schema 12, retains GitHub authentication, and reports zero proposed
external actions for the live mission. No push, PR, deploy, Agent Index update,
verification request, or submission was proposed or executed. The rebuilt
`joust-agent:latest` image has manifest-list digest
`sha256:2603cd291c869bc79c0a55813107274ebe760b062b31d134aa843b61f3c951f5`.

## 2026-09-14 — Competition Closed Loop: authenticated GitHub observation

`GitHubRuntimeObserver` now performs a read-only preflight through the GitHub
CLI adapter and persists the authenticated account, requested and canonical
repository identities, repository URL, push permission, default branch and its
protection state, open pull requests, check runs, and recent Actions runs as
mission evidence. Adapter tests prove the path does not call push or PR-create
operations.

The runtime authenticated as `baskpascal`. Its GitHub CLI configuration is held
in the persistent Hermes volume at `/var/lib/hermes/.config/gh`, with the files
owned by the Hermes runtime user and mode `0600`. Because this container has no
OS keyring, the credential is stored by `gh` in its protected configuration
file; it is never baked into the image or printed by Joust. `GH_CONFIG_DIR` is
fixed in both the image and Compose contract. After rebuilding and recreating
`galahad-joust-recovery` with the existing volumes, `gh auth status` and Joust's
runtime doctor both passed without an injected per-command config path.

A live mission read at `2026-09-14T00:20:47.276872Z` proved repository access
and push permission, an unprotected `main` branch, and empty PR, check, and
Actions sets. Empty remote state is evidence, not a claim that CI passed. The
same response revealed that the saved target `baskpascal/galahad` canonicalizes
to `baskpascal/joust`; the current rehearsal target is therefore Joust's
distribution repository rather than an independent competition entry. No push,
PR, deploy, Agent Index update, verification request, or submission occurred.

Verification: focused Ruff and pytest checks passed (11 tests). The rebuilt
`joust-agent:latest` image has manifest-list digest
`sha256:b8d523b010b314133c176437f90a8ded86cf851815813b44473be5f068bf443e`.

## 2026-09-13 — Competition Closed Loop: metrics change decisions

`CompetitionMetricsAnalyzer` now turns consecutive snapshots into rank, user,
successful-install, token, token-growth, and acquisition-growth deltas. Its
ordering is explicit: eligibility first, then acquisition versus competitor
velocity, then stalled successful installs, then post-install usage. A test for
the proposed example (`rank 4 -> 7`, installs `+3`, tokens `+2%`, competitor
growth `+28%`) selects acquisition velocity and explicitly states that the
evidence does not identify retention as the bottleneck.

The live mission was refreshed at `2026-09-13T23:26:07.755879Z`. Its persisted
decision now reads `Agent Index eligibility: Joust is not Verified`, with next
action `Prepare an approval-bound Agent Index verification request`. No
verification request was sent: the analyzer proposes the action, while the
external-action approval boundary remains intact. The refreshed competition
state is version 2.

## 2026-09-13 — Competition Closed Loop: live Agent Index metrics

The public Agent Index page was inspected read-only. Its own JavaScript uses
the structured API at `https://agent-index-server.vercel.app`: `/v1/agents`,
`/v1/agent?agent_id=...`, and `/v1/usage?agent_id=...`. Joust now contains a
dedicated `CompetitionMetricsReader` contract and `PlowMetricsReader`; HTML/DOM
parsing is not coupled to the orchestrator. Missing or malformed dynamic data
raises `MetricsUnavailable` rather than becoming zero.

`PlowMetricsIngestor` preserves the three raw JSON responses as source evidence,
emits typed leaderboard/metric signals, reconciles current state, and feeds the
result into `CompetitionObserver` before planning. A live read was persisted to
mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` at
`2026-09-13T23:20:15.847564Z`: one user, zero successful installs, 3,119,664
tokens, two active days, not Verified, and therefore no eligible rank. The
reconciled state is version 1 (`0227e2f5-62ea-4361-9666-00fabeaaef96`) with six
active signals. This was a public read and local evidence write only.

## 2026-09-13 — Competition Closed Loop: structured competition state

Database migration 11 adds durable raw `SourceObservation`, extraction,
structured-signal, and versioned current-state records. The new competition
intelligence reducer accepts evidence-linked `RuleObservation`, `MetricSignal`,
`DeadlineSignal`, and `LeaderboardSignal` contracts. Reconciliation applies the
documented authority hierarchy and recency: a newer organizer announcement can
supersede official rules, while a third-party contradiction is retained as
`CONFLICTED` without replacing active state.

The observation plane now reads the reconciled deadline, active rules, metrics,
and leaderboard values. Tests model the supplied judging update and prove that
`TOP_10_HUMAN_REVIEW` becomes superseded by `LEADERBOARD_ONLY`, the September 23
snapshot is typed, and the `galahad-hackathon` leaderboard signal remains linked
to raw evidence. This slice does not claim live Agent Index metric ingestion;
that is the next checklist item.

## 2026-09-13 — Competition Closed Loop: reliable identity and monitor gate

The MVP closure plan is now tracked in `docs/COMPETITION_CLOSED_LOOP.md` as ten
sequenced, verifiable items. The external Agent Index key is no longer treated
as the product name: Joust centralizes product/display/brand as `Joust`, the CTA
as `Joust it.`, and binds the first configured `AGENT_ID` into SQLite
installation state. A later runtime using a different id fails explicitly, so
the registered `galahad-hackathon` identity cannot be fragmented by an
accidental rename.

Database migration 10 adds observation fingerprints, atomic expiring monitor
leases, and durable retry state. `CompetitionObserver` now separates read-only
collection from evidence persistence. `MonitoredCompetitionRunner` uses that
boundary to skip unchanged observations before planning, serialize workers,
apply 1m/2m/5m/15m/1h capped backoff with jitter, and retain the last successful
observation across failures. Collection failure and unchanged state have
different durable outcomes and events. Hermes cron remains disabled until the
remaining closed-loop gates pass.

Verification: Ruff formatting/checks passed; the full suite passed with 132
tests. The rebuilt `joust-agent:latest` image has manifest-list digest
`sha256:54224c90e6ef07750779b28229948f2b5d8358d0669b2491d09ac03eef2bb22d`.
An ephemeral image smoke test returned healthy at migration 10 with bound
`agent_id=galahad-hackathon`, `display_name=Joust`, and a matching identity
check. Active containers were not restarted and no remote mutation was
performed.

## 2026-09-12 — Bootstrap and first vertical slice

- Inspected the empty workspace, the attached SDD, official
  `plow-pbc/plow-hermes-agent` commit
  `8710797b6409c77df560c6198407765d138ea617`, and the current official
  downstream variant/Agent Index pattern.
- Started from the attached SDD in `docs/SDD.md` (source SHA-256
  `572c39001c2dffb67abf1f78fa3b085084b2647d6202f2dee17aff060170d203`) and
  documented the real-project execution extension as section 71. The current
  repository copy includes that extension (SHA-256
  `f646a65677a57ad6f0c004244fd68f1c80b477fd3610b977e3dbbf34aed0eae3`).
- Converted the workspace from a temporary base clone into a downstream
  Joust variant; generic Plow/Hermes runtime files were removed because they
  are upstream-owned.
- Added MIT licensing, secret hygiene, a pinned official Agent Index client,
  SHA-256 verification, `s6` supervision, explicit `AGENT_ID`, persona, and six
  validated operational skills.
- Added Pydantic contracts, four SQLite migrations/repositories, append-only events,
  deterministic state transitions, persistent DAG scheduling, cycle detection,
  retry/crash recovery, provider-neutral LLM protocol, CLI, and doctor command.
- Added auditable task-failure/cancellation metrics and an explicit postmortem
  record that persists outcome, artifact, and reusable cross-mission lessons.
- Completed the SDD capability surface at 48 names, including screenshot,
  video-script, and final-checklist submission capabilities. Clarified that
  `AGENT_ID` is operator-chosen, while Verified status is a separate program
  step expected to open on 2026-09-14.
- Implemented the fixture-backed path from URL through locked and independently
  cross-checked rules, evidence, contradiction handling, 20 ideas in five
  clusters, six evaluator roles plus meta-judge, selected strategy,
  architecture tournament, planning artifacts, Git-checkpointed executable
  demo, experiment, five-role red team, repair tasks, demo/pitch tournaments,
  compliance, submission pack, status, rules refresh, and restart.

Verification:

- `quick_validate.py` — all six skills valid.
- `pytest -q tests/` — 67 passed (including five deadline parameter cases).
- `ruff check hackathon_competitor tests` and `ruff format --check` — passed.
- `git diff --check` — passed (Windows line-ending notices only).
- `docker compose config --quiet` with `AGENT_ID=joust` — passed.
- Git Bash `bash -n image/s6-overlay/s6-rc.d/agent-index/run` — passed.
- Downloaded official client hash —
  `633ad3bc24a51d6b7dcfaae319983ab174d9853a525237d99cac64878452560c`,
  matching `vendor/client.pin`.
- Real container E2E — mission created in one container and resumed in a second:
  `READY_FOR_SUBMISSION`, 12/14 tasks succeeded, 26 artifacts, 25 evaluations,
  five recorded source tool calls, and the rehearsal task ready. The other
  outstanding mission task is a human-approval user trial; no external action
  occurred during that deterministic fixture run.
- Docker image build — passed from the immutable official base. The current
  Compose image manifest list is
  `sha256:9f63dbd5d62a95692aff6f6c859e4c895a8437cf489316aec563f827aa19b56c`.
- Container `doctor` — healthy with migration v4, Git, all six skills, Plow
  discovery, explicit test `AGENT_ID`, service wiring, Agent Index client
  smoke (`not_registered` is safely visible), and no embedded credentials.
- Runtime boot contract — with a synthetic credential and local identity relay,
  `/init` promoted credentials and started `plow-init`, `main-hermes`,
  `hermes-gateway`, and `agent-index` under `s6`; no owner credential was used.

Authenticated Hermes/Plow startup was completed through the official
`plow-agents login --new-line`, `lines`, and `mint` flow. The real line-scoped
credential is mounted only at runtime and remains ignored by Git. The live
container promoted it with `plow-init`, connected the Plow Chat and email
platforms, and the pinned Agent Index client registered the chosen
`AGENT_ID=galahad-hackathon`. Its first report created a truthful zero-use
baseline; the Hermes store was created during gateway startup, so the first
early reporter pass was retried after the store became available. The optional
`agentsview` collector is not installed; the Hermes collector is the source of
truth for this image.

The owner then sent a live Plow Chat message. Hermes completed the turn in 5.8
seconds, persisted the session and response, and the delivery obligation
reached `delivered`. The next supervised Agent Index report submitted 25,710
tokens across two rows and received HTTP 200. This trial exposed a branding
defect: the first two responses reused the line's legacy `Willow` label because
the Plow Chat conversation retained its pre-fix system prompt. The Plow account
profile controls the owner's display name, not the agent line's identity, so it
remains separate from the variant. The variant persona now explicitly treats
legacy line labels as transport metadata, the image was rebuilt, and the old
conversation was preserved behind an official `session_reset` boundary. The
fresh session has the corrected identity prompt. Verified eligibility and final
submission remain human/external gates. The
separate Plow Latch MCP endpoint was returning HTTP 503 during this run, while
Plow Chat and email remained connected.

The branded-response retest passed: queued owner messages were processed after
the permission repair, the response identified itself as Joust, and delivery
reached `delivered`. The temporary silence was caused by a root-run diagnostic
invoking Hermes' generic `_secure_dir()` default, which changed the shared
root-owned home to `0700`. The image now exports `HERMES_HOME_MODE=3770`, matching
the upstream `plow-init` shared-home contract, and the image contract test pins
that requirement against regression. Verified eligibility and final submission
remain external gates.

The public Agent Index metadata was then completed for `galahad-hackathon`.
The rendered community page at
`https://aiworthusing.com/agent-index/galahad-hackathon` showed Galahad, its
Hermes / Plow runtime, one active user, and 119K tokens. A fresh supervised
report submitted the exact current total of 119,363 tokens across two rows and
received HTTP 200. Verification is still unavailable until 2026-09-14.

A live-source rehearsal against `https://aiworthusing.com/agent-index` exposed
two research edge cases that fixtures had hidden: ordinary public copy produced
a first-person story false positive, and an incomplete official surface caused
an unhandled quality-gate exception. The heuristic now rejects narrative-heavy
blocks unless they contain explicit normative language and recognizes common
registration/reporting requirements. Incomplete rule sets persist an
inspectable blocked mission instead of advancing or crashing. The repeated live
run stored six evidence records and returned `BLOCKED` with only the truthful
finding `critical prohibitions are missing`.

The first shipped-image rehearsal then exposed a packaging permission defect:
Docker had created `/opt/joust` as `0644`, so the unprivileged Hermes user
could not traverse it to import the mission package. The image now normalizes
all package directories to `0755` and files to `0644`; the image contract test
pins the directory rule.

The rebuilt-image `doctor` also revealed two diagnostic namespace mismatches:
the Plow MCP URL is injected through the root-owned `s6` environment directory,
and Agent Index identity lives in `HERMES_HOME`, not Joust's application-state
subdirectory. Doctor now checks the non-secret presence of the runtime marker
without reading it and runs the official client smoke check against the actual
Hermes home.

The final rebuilt-image `doctor` returned healthy with migration v6, all six
skills, Plow tools available, the stable agent id present, Agent Index status
`registered`, and the credential present at mode `0600`. The supervised report
again returned HTTP 200 for 119,363 tokens across two rows.

A public source bundle builder now archives only committed content, applies the
repository's export exclusions, and validates install markers, required files,
MIT licensing, forbidden secret/state paths, and Linux control-file line
endings. A clean extracted ZIP installed the Python package, exposed the CLI,
and built the complete Docker image successfully. The builder explicitly
disables host `core.autocrlf` conversion after the first Windows smoke revealed
that carriage returns would corrupt the pinned client path.

The authenticated Plow/Latch MCP health probe was repeated after the public
bundle work. The route itself responded, but authenticated `initialize` still
returned HTTP 503, confirming that the remaining Latch gap is upstream/device
availability rather than Joust credentials or HTTP routing. Plow Chat and
Agent Index reporting remain healthy.

A local bare-remote publication rehearsal proved the intended `HEAD -> main`
push and clean clone, but also found that a normal Windows clone with global
`core.autocrlf=true` converted `vendor/client.pin` back to CRLF and broke the
Docker build. Repository attributes now force LF for the Dockerfile, pin files,
shell scripts, and every `s6` control file; the image contract test prevents
that cross-platform install regression.

The publication rehearsal was repeated from a fresh bare remote with
`core.autocrlf=true`: `HEAD` cloned as default branch `main`, the pin contained
zero carriage returns, and the Docker image built successfully from that clean
clone.

The public release was then published to
`https://github.com/baskpascal/joust` on `main`. Agent Index metadata was
updated with that repository and the README install URL, and story
`live-source-safety` was published with the `Engineering` tag. A fresh rendered
page verified the public GitHub install link, one active user, 119K tokens, and
the published use case. Verified status remains unavailable until 2026-09-14;
one-click Plow deployment and demo media remain external follow-ups.

The next execution slice now separates the competition source from the project
being built. A mission can persist a `ProjectTarget`, create a mission branch,
run an explicit argv-based implementation command, record `ChangeSet` and
`BuildRun` evidence, repair a failing test, and reproduce the validated commit
from a clean clone. The GitHub CLI adapter and publication service are covered
by contract tests; push and pull-request creation remain approval-bound and no
new live remote write was performed.

Project compliance now runs against the attached target rather than Joust's
own distribution repository. License, technology, repository, and demo checks
are evidence-based; behavioral prohibitions remain `UNKNOWN` until an explicit
audit artifact proves them, so the submission gate cannot claim compliance from
absence alone.

Project execution now also has an environment boundary: build, test, run, and
coding-agent subprocesses inherit only a small platform-safe base plus an
explicit non-sensitive allowlist. Credential-shaped names are rejected before
execution. The local suite was at 99 tests after adding a red-team repair
contract that prevents failed historical attempts from contaminating final
commit evidence, a target-bound submission readiness gate, and command
credential/repair-budget validation.

The real-project path now has its own submission writer and CLI command. It
binds every generated pack to the target repository, mission branch, commit
SHA, diff hash, and recorded build/reproduction runs. A fresh integration test
advanced a built target from `VALIDATING` through compliance to
`READY_FOR_SUBMISSION`; a known future deadline passed and an expired deadline
failed.

The post-change end-to-end smoke drove the public CLI through a fresh mission,
attached a temporary `new_repo` target, ran a file-based implementation
command, committed the mission branch, and passed the declared test both in
the working tree and in a clean clone. The rebuilt image's `doctor` is healthy
with database migration 6. The reproducible public bundle contains 112 files
; run `cli bundle` to print its current SHA-256.

## 2026-09-13 — Joust architecture delta

The available Joust SDD attachment was read in full; it contains 679 lines and
ends at the incomplete heading `# 14`. Sections 1–13 were mapped in
`JOUST_ARCHITECTURE_DELTA.md` without inventing the missing text. Compatible
contracts now separate terminal `MissionStatus` from phase, add the richer
`CompetitionSpec`, persist `EntrantProfile` and versioned `CompetitionRule`,
trigger strategy reassessment on critical supersession, and complete the
required `ProjectTarget` identity/command/deployment/SHA fields. Migration 6
adds the new profile and rule stores.

Migration 7 adds durable competition cycles. `CompeteLoop` now enforces and
persists the seven Joust stages, deterministic action selection, evidence-bound
verification, measured deltas, repeated cycles, and terminal mission status.
The suite contains 102 collected tests. This is controller evidence only: live
observation adapters, Hermes model-backed target construction, and authenticated
GitHub mission writes remain explicit acceptance gaps.

Migrations 8 and 9 add durable competition observations and action executions.
The observation plane captures deadline, rules, local Git state, build/change
state, score signals, GitHub checks, and deployment health through read-only
ports. The action dispatcher records the selected action and routes
`BUILD_PROJECT` through `RealBuildLoop` idempotently. The suite now contains 106
tests. Competition-page/announcement adapters, non-build executors, live Hermes
construction, and authenticated GitHub writes remain unproven.

## 2026-09-13 — Live Hermes construction evidence

The committed tree was rebuilt as `joust-agent:real-build` at
`sha256:6cd0e4df0484313b553d9019b1b7589b41cbdaf53df4a2a1c698a446355463df`.
Container `doctor` was healthy at database migration 9 and the Agent Index
reporter returned HTTP 200. After using the s6-managed Plow inference
environment, a Hermes one-shot returned `HERMES_READY`.

The isolated live-smoke mission
`4881b861-a3a6-41e9-8f2d-0ed150c49f76` selected and durably dispatched a
`BUILD_PROJECT` action to `HermesImplementer`. Hermes created `README.md`,
`entry.py`, and `test_entry.py`; Joust committed
`46e82c4adf5799baf211e847b03c1e2f862cfe23`. Sixteen generated unit/CLI tests
passed in the target, and the database records passing `test` and
`reproduce_test` runs at that same SHA. The first competition cycle completed
and sequence 2 began at `OBSERVE`, proving that a successful build does not
terminate the mission. No GitHub push, PR, deployment, or submission occurred.

## 2026-09-13 — Live persistent competition mission

Mission `5a26f83b-61cd-426c-ba02-878dc8c9cc38` was attached to an explicit
checkout and advanced through multiple durable compete cycles. The first retry
resumed at `ASSESS` without duplicating its observation. Live planning exposed
high provider variance, so the planner now runs in safe mode with project
rules/tools disabled, low-context input, a 60-second bound, recent-cycle memory,
and an audited deterministic fallback.

The first completed cycle exposed an evidence-integrity defect: `CUSTOM` had
claimed completion for a research-shaped action without doing research. A real
`RESEARCH` executor now fetches bounded official URLs, persists excerpts, and
fails if no readable text exists. The HTML parser now excludes script, style,
noscript, and template content. A subsequent live cycle captured visible Agent
Index copy about Verified eligibility while retaining the dynamic leaderboard
as unavailable rather than inventing rank or usage.

The deterministic planner fallback then selected local verification because no
build evidence existed. Six target `BuildRun` records passed: environment
creation, dependency installation, and tests in the working checkout, followed
by the same three phases in a clean clone. The implementation correctly
produced no diff, but the old review contract treated that as a blocker and
began an unnecessary repair. The repair process was stopped before it changed
the checkout. `ChangeSet` now has an explicit `verification_only` mode, and a
restarted runner closes an orphaned `RUNNING` execution with a durable
interruption event instead of hanging or duplicating it.

GitHub check observation now uses `gh api` rather than the unsupported
`gh pr checks --json` flag in the pinned CLI. The live container is not
authenticated to GitHub, so remote checks remain an explicit uncertainty. No
push, PR, deployment, submission, account mutation, or Verified request was
performed. The complete local suite now collects 300 tests and passes with
Ruff and `git diff --check` (line-ending notices only).

## 2026-09-15 — Plow channel correction and SMS runtime rebuild

The operational Plow Chat channel for this installation is the phone line
provided by `hermes-plow-plugin`, reached through SMS. The open browser
ChatGPT/custom-GPT conversation is a separate interface; it is not the live
agent channel and cannot be used as evidence that an SMS message executed a
Joust action. Earlier notes that called that browser conversation a live Plow
Chat retest are corrected by this entry.

The checkout was already at `galahad/competitor-agent` commit `f7b9ac2`.
The image was rebuilt from that checkout and the service was recreated without
removing the persistent `galahad_agent-home` volume. The new container contains
`hackathon_competitor/lifecycle.py`, exposes `mission pause`, `mission cancel`,
and `mission resume`, and `joust doctor` is healthy with Plow tools available,
the Agent Index client registered, and the line credential promoted with mode
`0600`. The browser/ChatGPT conversation was not used to claim an SMS result.

The live SMS pause/cancel sequence still needs to be sent and verified after
this rebuild. Until that happens, this project records the SMS path as ready,
not as a completed real-user lifecycle acceptance test.

After the channel and persona documentation was committed, the image was
rebuilt once more from `19cb0a3`; the container's `lifecycle.py` and seeded
persona hashes now match that checkout.

## 2026-09-15 — Mission lifecycle control incident

Plow Chat exposed implementation details when an operator asked “Can we cancel
it?”: it described an unavailable CLI instead of answering the product question
or offering the action. The root cause was that pause/cancel existed only as
orchestrator helpers, while the public CLI and persona had no canonical
lifecycle route. In addition, competition and monitoring entrypoints guarded
only the terminal status field, so a PAUSED mission could still be considered
active.

`MissionLifecycleService` is now the single boundary for pause, resume, and
cancel. It persists `MISSION_PAUSED`, `MISSION_RESUMED`, and
`MISSION_CANCELLED` exactly once on idempotent retries, records the prior phase
for resume, stops unfinished task bookkeeping on cancellation, and preserves
the attached target and project. Competition cycles, scheduled monitors, and
capability dispatch refuse PAUSED/CANCELLED missions; restart recovery does not
resume them. The CLI exposes `mission pause`, `mission resume`, and
`mission cancel` with authoritative JSON. Persona guidance distinguishes
questions from commands and keeps internal paths and implementation terms out
of normal replies.

The lifecycle regression suite covers state transitions, target/task/project
preservation, idempotent cancellation, execution guards, and natural-language
question versus command handling. The full suite contains 300 tests. The real
Plow Chat retest is still pending:
it requires sending the two-message confirmation sequence through the live
conversation and recording the existing IBM Bob 2.0 mission without modifying
its project.

Live Plow Chat observation on this host was performed against the open
`Plow-Hackhaton` conversation. “Can we cancel it?” produced the concise
confirmation question with no internal vocabulary. “Yes, cancel it.” produced
the expected cancellation wording, but the conversation has no connected Joust
action tool: it narrated the requested test instead of changing the mission.
The container database therefore remained unchanged. This is a real integration
gap, not evidence that cancellation itself failed; the lifecycle and CLI are
ready for the Plow tool binding to route those messages to
`MissionLifecycleService`.
