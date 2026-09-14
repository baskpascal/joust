<p align="center">
  <img src="docs/brand/joust-hero.png" alt="Joust — a persistent autonomous competition agent" width="100%">
</p>

Give Joust a competition. It reads the rules, picks a way to win, builds a real
entry, tests it, repairs its own failures, publishes the result, and keeps
improving it until the deadline.

It is an agent that runs on Plow, and it is evidence-first: nothing reports
success on a claim, only on a result it observed. A build passes because a
recorded run exited zero. A branch is pushed because the remote SHA was read
back and matched. Whatever Joust cannot observe stays unverified rather than
becoming a pass.

## Run it

You need Git, Docker and Docker Compose v2.

```bash
git clone https://github.com/baskpascal/joust.git && cd joust
```

Mint a Plow credential with the official helper — it writes `./plow-credentials`,
which holds an API token, so keep it local and out of Git:

```bash
git clone https://github.com/plow-pbc/plow-agents.git
export PATH="$PWD/plow-agents/bin:$PATH"
plow-agents login && plow-agents lines && plow-agents mint <free-line-id>
```

Pick a stable Agent Index id, set `AGENT_ID` to it, and start:

```bash
AGENT_ID=your-agent-id docker compose up --build -d
```

Then talk to it in Plow Chat. Send a competition URL and `Joust it.`

<details>
<summary>Windows PowerShell, a standalone image build, and credential paths</summary>

```powershell
$env:AGENT_ID = "your-agent-id"
docker compose up --build -d
```

`docker build -t joust-agent .` builds the image on its own. `AGENT_ID` is
yours to choose, is not the product name, and must not change across restarts.
If your checkout sits on a filesystem that cannot hold POSIX modes — a Windows
drive mounted under WSL, say — keep the credential somewhere that can and point
`PLOW_CREDENTIALS_PATH` at it.

</details>

## Check it

```bash
python -m hackathon_competitor.cli doctor
```

## What it does

Joust owns a mission, not a codebase, so publishing a submission does not end
the run:

```text
observe → assess → strategize → execute → verify → measure → adapt ─┐
   ^                                                                │
   └────────────────────────────────────────────────────────────────┘
```

Every remote mutation — pushing, opening a pull request, deploying, submitting
— takes one path: a durable proposal, an approval decision, an idempotent
execution, an observation of the actual remote state, and evidence. An action
waiting on somebody else rests in `AWAITING_EXTERNAL`, which is neither success
nor failure. A source that could not be read is recorded as unreadable, never
as unchanged.

## Read more

[The design document](docs/SDD.md) · [what is built against it](docs/JOUST_ARCHITECTURE_DELTA.md)
· [why each piece came out this way](docs/BUILD_NOTES.md) · [running it](docs/RUNBOOK.md)

MIT licensed. The marks are generated: `python docs/brand/build_marks.py`.
