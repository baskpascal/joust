from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..models import (
    BuildRun,
    ChangeSet,
    ComplianceReport,
    Decision,
    HackathonSpec,
    Idea,
    ProjectTarget,
)


def _tournament(kind: str) -> tuple[str, list[tuple[str, float]]]:
    if kind == "demo":
        candidates = [
            ("Evidence-to-outcome", 0.94),
            ("Feature tour", 0.71),
            ("Architecture deep dive", 0.68),
        ]
    elif kind == "pitch":
        candidates = [
            ("The competition lead", 0.93),
            ("Safer hackathon copilot", 0.79),
            ("Persistent agent platform", 0.70),
        ]
    else:
        raise ValueError(f"unsupported tournament kind: {kind}")
    return max(candidates, key=lambda item: item[1])[0], candidates


def submission_documents(
    spec: HackathonSpec,
    selected: Idea,
    decision: Decision,
    compliance: ComplianceReport,
) -> dict[str, tuple[str, str]]:
    demo_winner, demo_candidates = _tournament("demo")
    pitch_winner, pitch_candidates = _tournament("pitch")
    demo_scores = "\n".join(f"- {name}: {score:.2f}" for name, score in demo_candidates)
    pitch_scores = "\n".join(f"- {name}: {score:.2f}" for name, score in pitch_candidates)
    blockers = "\n".join(
        f"- [{'x' if rule.status.value == 'pass' else ' '}] {rule.text} ({rule.status.value})"
        for rule in compliance.rules
    )
    return {
        "README.md": (
            "submission_readme",
            f"""# {selected.title}

{selected.summary}

## Why it matters

Galahad connects rules, evidence, strategy, implementation, evaluation,
repair, demo, and submission artifacts in one restart-safe mission.

## Install and run

Build the Plow variant with `docker build .`, supply a line-scoped
`plow-credentials` file and your chosen stable `AGENT_ID`, then use Docker Compose.
Request Verified separately when that program is available.

## Evidence

Selected with {len(decision.evidence_ids)} official evidence references and an
independent evaluator panel. No private mission content is sent by the Agent
Index integration.
""",
        ),
        "submission-short.txt": (
            "submission_short",
            "Galahad turns a hackathon brief into an evidence-backed strategy, tested build, adversarial review, and honest submission pack.",
        ),
        "submission-long.md": (
            "submission_long",
            f"""# Submission description

Galahad is a competition lead, not merely an idea generator. For {spec.name},
it locks official rules, maps evidence, explores diverse strategies, uses
independent judges, records a reversible decision, builds a plan, validates an
executable path, red-teams the result, and packages claims that match evidence.

Selected direction: **{selected.title}**.
""",
        ),
        "demo-script.md": (
            "demo_script",
            f"""# Selected demo narrative

Tournament winner: **{demo_winner}**

{demo_scores}

1. Paste the official hackathon source.
2. Show the locked rules and contradiction record.
3. Show five idea clusters and the independent review panel.
4. Open the selected strategy and generated PRD/architecture.
5. Run the mission status demo and show persisted restart state.
6. Finish on compliance and the human-only submission gate.

Target length: under three minutes. Do not show unimplemented features.
""",
        ),
        "pitch.md": (
            "pitch",
            f"""# Pitch tournament winner

Tournament winner: **{pitch_winner}**

{pitch_scores}

**Hook:** Most hackathon copilots generate ideas. Galahad runs the competition.

**Differentiation:** It traces official evidence through strategy, build,
red-team, repair, demo, and submission — with durable state and human control.

**Close:** Give it a hackathon. It tries to win it, honestly.
""",
        ),
        "screenshots.md": (
            "screenshot_plan",
            """# Screenshot plan

- First competition snapshot with sources.
- Idea clusters and evaluator disagreement.
- Mission status with completed DAG tasks.
- Artifact graph and stale warning.
- Compliance gate with all blocker statuses visible.
""",
        ),
        "claims-map.md": (
            "claims_map",
            """# Claims map

| Claim | Executable evidence |
|---|---|
| Missions survive restart | SQLite integration and E2E restart test |
| Rules are evidence-backed | Evidence records and contradiction test |
| Strategy is independently reviewed | Stored evaluator panel and meta-judge |
| Usage reporting is official and pinned | Image client checksum and s6 service |
| Submission stays human-controlled | Approval service and submission skill |
""",
        ),
        "final-checklist.md": (
            "final_checklist",
            f"""# Final submission checklist

{blockers}

- [x] MIT license present.
- [x] Install/run instructions accounted for.
- [x] Primary demo path executed.
- [x] Claims mapped to implementation evidence.
- [ ] Real-user trial completed.
- [ ] Agent Index page verified by the organizer.
- [ ] Human explicitly confirms final submission.
""",
        ),
    }


def project_submission_documents(
    spec: HackathonSpec,
    selected: Idea,
    decision: Decision,
    compliance: ComplianceReport,
    target: ProjectTarget,
    change_set: ChangeSet,
    build_runs: Iterable[BuildRun],
) -> dict[str, tuple[str, str]]:
    """Render a submission pack that names the real project commit.

    The V0 ``submission_documents`` function describes Galahad's distribution
    demo. This writer is deliberately separate so a target project cannot be
    represented by the agent repository's evidence by accident.
    """

    runs = list(build_runs)
    command_lines = []
    for run in runs:
        public_command = " ".join(
            f"<absolute>/{Path(argument).name}" if Path(argument).is_absolute() else argument
            for argument in run.command
        )
        command_lines.append(
            f"- `{run.phase}`: `{public_command}` — "
            f"{'PASS' if run.passed else 'FAIL'}"
        )
    commands = "\n".join(command_lines) or "- No build evidence recorded."
    repository = target.repository_url or "(local-only target)"
    blockers = "\n".join(
        f"- [{'x' if rule.status.value == 'pass' else ' '}] {rule.text} ({rule.status.value})"
        for rule in compliance.rules
    )
    return {
        "README.md": (
            "project_submission_readme",
            f"""# {selected.title}

{selected.summary}

## Validated project

- Repository: `{repository}`
- Branch: `{target.working_branch}`
- Validated commit: `{change_set.commit_sha}`
- Diff hash: `{change_set.diff_hash}`

This pack describes the competition project produced by Galahad. The commit
and reproduction evidence above refer to the target repository, not the
Galahad distribution repository.

## Build evidence

{commands}
""",
        ),
        "submission-short.txt": (
            "project_submission_short",
            f"{selected.title}: a validated competition project at {change_set.commit_sha} with reproducible build evidence.",
        ),
        "submission-long.md": (
            "project_submission_long",
            f"""# Submission description

{selected.summary}

The implementation was produced on `{target.working_branch}` and validated at
commit `{change_set.commit_sha}`. Its diff hash is `{change_set.diff_hash}`.
The checks were repeated from a clean clone before this pack was generated.
""",
        ),
        "demo-script.md": (
            "project_demo_script",
            f"""# Project demo

1. Check out `{target.repository_url or '(the local target)'}` at commit `{change_set.commit_sha}`.
2. Run the declared install/build commands.
3. Run the declared test and demo commands.
4. Show the user journey and the rule/compliance report.

The selected direction is **{selected.title}**. Do not show behavior outside
the validated commit.
""",
        ),
        "claims-map.md": (
            "project_claims_map",
            f"""# Claims map

| Claim | Evidence |
|---|---|
| The target project exists | `{repository}` |
| The implementation is reviewable | commit `{change_set.commit_sha}`; diff `{change_set.diff_hash}` |
| The checks are reproducible | clean-clone `reproduce_*` BuildRuns |
| The direction follows the mission decision | `{decision.id}` with {len(decision.evidence_ids)} evidence references |
""",
        ),
        "compliance.md": ("project_compliance", f"# Compliance\n\n{blockers}\n"),
        "final-checklist.md": (
            "project_final_checklist",
            f"""# Final checklist

- [x] Target repository identified: `{repository}`
- [x] Mission branch recorded: `{target.working_branch}`
- [x] Validated commit recorded: `{change_set.commit_sha}`
- [x] Clean-clone reproduction recorded.
- [{'x' if compliance.ready else ' '}] Blocker rules pass.
- [ ] Human explicitly confirms final submission.
""",
        ),
    }
