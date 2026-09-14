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

In Plow Chat, send the competition and three words:

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

## Evidence

Three live competitions read on 2026-09-14, none of them known to the code:

| Competition | What Joust produced |
|---|---|
| [OneAquaHealth IEEE](https://oneaquahealth-ieee-hackathon.devpost.com/rules) | 3 strategies; chose a dry-weather discharge detector for a utility operator; created `dryday` |
| [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/rules) | 3 strategies across the Fire TV, Bee and Ring tracks; deadline read as 2026-10-23 12:00 PDT |
| [RevenueCat Shipaton](https://revenuecat-shipaton-2026.devpost.com/rules) | 3 strategies; identified store publication as the binding gate |

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

## Inside

[The design document](docs/SDD.md) says what Joust is meant to be.
[The runbook](docs/RUNBOOK.md) says how to operate it.
[The build notes](docs/BUILD_NOTES.md) say why each piece came out the way it did.

MIT licensed.
