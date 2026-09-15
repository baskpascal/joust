<p align="center">
  <img src="docs/brand/joust-hero.png" alt="Joust" width="100%">
</p>

# Joust

**Drop a competition. Joust it.**

Joust is an agent that takes a hackathon or technical competition, works out
what winning actually requires there, decides what to build, builds it in a
separate real project, tests it, and keeps improving it until the deadline.

It reads the competition you give it. It has no idea what your competition is
until it reads it.

## Try it

You need Git, Docker and Docker Compose v2.

```bash
git clone https://github.com/baskpascal/joust.git && cd joust
```

Mint a Plow credential with the official helper. It writes `./plow-credentials`,
which holds an API token, so keep it local and out of Git:

```bash
git clone https://github.com/plow-pbc/plow-agents.git
export PATH="$PWD/plow-agents/bin:$PATH"
plow-agents login && plow-agents lines && plow-agents mint <free-line-id>
```

Pick a stable Agent Index id, then check the machine before anything is built.
The preflight needs nothing installed and changes nothing; it names whatever is
missing and the command that fixes it:

```bash
export AGENT_ID=your-agent-id
python3 scripts/preflight.py
```

When it says ready:

```bash
docker compose up --build -d
```

## First mission

In the operational Plow Chat phone line (SMS; iMessage may be used for line
activation), send the competition and three words:

```text
https://some-hackathon.devpost.com/rules

Joust it.
```

Or run the same mission from the command line:

```bash
python -m hackathon_competitor.cli mission joust-it --url <competition-url>
```

## What happens

1. **It reads the live competition.** Rules, deadlines and the scoring
   mechanism come out of the pages themselves. A page it cannot read is
   reported unreadable, never as a competition without rules.
2. **A model forms competing strategies.** At least three, for different users,
   winning in different ways, each tied to a rule the competition actually
   states.
3. **It chooses one and says why** — against that competition's own scoring,
   with a reason recorded for every strategy it turned down.
4. **It creates a real project.** A separate repository with its own stack,
   its own tests and its own install path. Not a folder inside Joust.
5. **A coding model implements it,** and when a test fails, diagnoses and
   repairs it.
6. **It keeps going after the first build** — watching the competition, the
   deadline and its own project, and changing course when they change.

Every model call is stored: which provider, which model, what it was asked, what
it chose, and what it chose over. A change the model made carries the model's
name. **With no model configured, a mission stops at `AI_STRATEGY_UNAVAILABLE`
and builds nothing** — there is no deterministic impersonation underneath.

<p align="center">
  <img src="docs/brand/joust-duel.png" alt="" width="100%">
</p>

## Evidence

Competitions read on 2026-09-14 and 2026-09-15, none of them known to the code
beforehand — chosen after the code was frozen, not the other way around:

| Competition | What Joust produced |
|---|---|
| [OneAquaHealth IEEE](https://oneaquahealth-ieee-hackathon.devpost.com/rules) | Chose a dry-weather discharge detector; built `dryday`; repaired its own build failures; **11/11 tests passing**, clean-clone verified (`807df02`) |
| [The Agent Index](https://aiworthusing.com/agent-index) | Built a GitHub issue-triage agent (`issue-pilot`); diagnosed and fixed two real defects on its own; **4/4 tests passing** (`646d9077`) |
| Same mission, redirected mid-build | An operator instruction changed the winning strategy twice; Joust re-planned, built a *different* real project each time, and marked the superseded one as superseded — the strategy and the repository never drifted apart |
| [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/rules) | Chose an Alexa+ caregiving check-in agent; built `kinkeeper` **concurrently** with the row below, against a shared database |
| [RevenueCat Shipaton](https://revenuecat-shipaton-2026.devpost.com/rules) | Chose an Android cost-splitting app; built `classsplit`; a build-loop crash found here (a coding agent never generated its own Gradle wrapper) was fixed and re-verified live |

The Amazon and RevenueCat missions above ran **at the same time**, against a
shared database and a shared pool of project directories, to check for
exactly the failure mode an agent like this invites: one mission's context
leaking into another's. It didn't — each build stayed correctly scoped to
its own project, and each failure it hit was its own.

[The build notes](docs/BUILD_NOTES.md) record how each of these went, including
what broke.

## Current limitations

- **Reading is not universal.** Competition pages that render client-side —
  Kaggle's rules, for one — return `no_extractable_text`. Joust says so rather
  than guessing.
- **Deadlines are read from prose.** Where a page states no parseable date,
  the deadline stays unknown instead of being invented.
- **The chat path depends on Plow.** When the Plow device behind the credential
  is disconnected, the toolset parks and the agent can report but not converse.
- **Submission is never automatic.** Publishing, deploying, accepting terms and
  submitting each wait for an explicit approval immediately before the action.
- **Parts of the older pipeline are deterministic fixtures.** They are labelled
  as such in the source and no mission is routed through them.

<p align="center">
  <img src="docs/brand/joust-scenes.png" alt="" width="100%">
</p>

## Inside

[The design document](docs/SDD.md) says what Joust is meant to be.
[The runbook](docs/RUNBOOK.md) says how to operate it.
[The build notes](docs/BUILD_NOTES.md) say why each piece came out the way it did.
[The marks](docs/brand/joust-marks.png) are drawn on a 16-pixel grid; nothing
in them is anti-aliased.

MIT licensed.
