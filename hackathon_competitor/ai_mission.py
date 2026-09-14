"""The mission path where a model, not a hash, decides what to build.

`run_vertical_slice` walks a mission from a URL to a plan without ever reaching
a model: its ideas come from a fixed list of names, its scores from a SHA-256
of the title, and its winner from the largest of those numbers. That path is
kept as a regression fixture, and this is the one the product runs.

The shape is the same — read the competition, form strategies, choose one, get
to a project — but every judgement in it belongs to a recorded model call, and
when no model answers the mission stops in BLOCKED with the boundary named
instead of quietly producing the same artefacts anyway.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from .ai import InvocationRecorder, ModelUnavailable, Reasoner
from .capabilities.ai_strategy import StrategyRejected, plan_project, strategize
from .capabilities.research import SourceFetcher, SourceUnreadable, discover_sources, extract_spec
from .models import (
    Decision,
    Mission,
    MissionState,
    ProjectMode,
    ProjectTarget,
    SourceRecord,
    StrategyCandidate,
)
from .orchestrator import MissionOrchestrator

_STRATEGY_STATES = (
    MissionState.INTAKE,
    MissionState.DISCOVERY,
    MissionState.RULES_LOCK,
    MissionState.LANDSCAPE_ANALYSIS,
    MissionState.IDEATION,
    MissionState.STRATEGY_SELECTION,
)


class MissionBlocked(RuntimeError):
    """The mission stopped at a boundary it can name."""

    def __init__(self, mission_id: UUID, code: str, detail: str):
        self.mission_id = mission_id
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _block(
    orchestrator: MissionOrchestrator, mission: Mission, code: str, detail: str
) -> MissionBlocked:
    orchestrator.database.append_event(
        mission.id, "MISSION_BLOCKED", {"code": code, "detail": detail[:500]}
    )
    mission.blockers = [*mission.blockers, f"{code}: {detail}"[:300]]
    orchestrator.database.save_mission(mission)
    orchestrator.transition_state(mission, MissionState.BLOCKED)
    return MissionBlocked(mission.id, code, detail)


def joust_it(
    orchestrator: MissionOrchestrator,
    source_uri: str,
    reasoner: Reasoner,
    *,
    workspace_path: str | None = None,
    fetcher: SourceFetcher | None = None,
    projects_root: str | Path | None = None,
) -> tuple[Mission, StrategyCandidate, Decision, ProjectTarget]:
    """One competition URL in; a chosen strategy and a real project out."""

    workspace = str(Path(workspace_path or ".").resolve())
    mission = orchestrator.create_mission(
        title="Competition mission",
        objective="Find and execute the strongest evidence-backed way to win.",
        source_inputs=[source_uri],
        workspace_path=workspace,
    )
    mission = orchestrator.transition_state(mission, MissionState.INTAKE)
    mission = orchestrator.transition_state(mission, MissionState.DISCOVERY)

    try:
        sources = discover_sources(source_uri, fetcher=fetcher)
    except SourceUnreadable as error:
        raise _block(orchestrator, mission, "SOURCE_UNREADABLE", f"{error.reason}: {error.detail}")

    for source in sources:
        orchestrator.database.save_source(
            SourceRecord(
                mission_id=mission.id,
                uri=source.uri,
                authority=source.authority,
                source_type=source.source_type,
            )
        )
    try:
        spec, evidence, _ = extract_spec(mission.id, sources)
    except ValueError as error:
        raise _block(orchestrator, mission, "RULES_NOT_EXTRACTABLE", str(error))

    orchestrator.database.save_spec(spec)
    for item in evidence:
        orchestrator.database.save_evidence(item)
    mission.title = spec.name or mission.title
    mission.hackathon_spec_id = spec.id
    mission.competition_id = spec.id
    mission.deadline_at = spec.deadline_at
    orchestrator.database.save_mission(mission)

    mission = orchestrator.transition_state(mission, MissionState.RULES_LOCK)
    mission = orchestrator.transition_state(mission, MissionState.LANDSCAPE_ANALYSIS)
    mission = orchestrator.transition_state(mission, MissionState.IDEATION)

    recorder = InvocationRecorder(orchestrator.database, mission.id)
    try:
        candidates, selected, ai_decision, analysis = strategize(
            spec, evidence, reasoner, recorder
        )
    except ModelUnavailable as error:
        raise _block(orchestrator, mission, error.code, error.detail)
    except StrategyRejected as error:
        raise _block(orchestrator, mission, "AI_STRATEGY_REJECTED", str(error))

    mission = orchestrator.transition_state(mission, MissionState.STRATEGY_SELECTION)
    decision = Decision(
        mission_id=mission.id,
        question="What should this mission build to win?",
        options=[
            {
                "id": str(candidate.id),
                "title": candidate.product_thesis[:120],
                "summary": candidate.recurring_job,
            }
            for candidate in candidates
        ],
        selected_option=str(selected.id),
        rationale=ai_decision.rationale,
        evidence_ids=list(ai_decision.evidence_ids),
        # A model's choice is reversible and reconsidered on the same signals a
        # person would reconsider it on.
        confidence=0.7,
        depth_level=4,
        reversible=True,
        reconsider_if=[
            "the official rules change",
            "the winning mechanism turns out to be measured differently",
            "a stated assumption fails",
        ],
    )
    orchestrator.database.save_decision(decision)
    orchestrator.database.append_event(
        mission.id,
        "AI_STRATEGY_SELECTED",
        {
            "decision_id": str(decision.id),
            "ai_decision_id": str(ai_decision.id),
            "invocation_id": str(ai_decision.invocation_id),
            "candidates": len(candidates),
            "winning_mechanism": analysis[:500],
        },
    )
    mission.selected_strategy_id = decision.id
    mission.active_strategy_id = decision.id
    orchestrator.database.save_mission(mission)

    mission = orchestrator.transition_state(mission, MissionState.PLANNING)
    try:
        plan, _ = plan_project(spec, selected, reasoner, recorder)
    except ModelUnavailable as error:
        raise _block(orchestrator, mission, error.code, error.detail)
    except StrategyRejected as error:
        raise _block(orchestrator, mission, "AI_PROJECT_PLAN_REJECTED", str(error))

    root = Path(projects_root or Path(workspace).parent) / plan["repository_name"]
    root.mkdir(parents=True, exist_ok=True)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(root.resolve()),
        default_branch="main",
        language=plan["language"],
        framework=plan["framework"],
        install_commands=plan["install_commands"],
        test_commands=plan["test_commands"],
        lint_commands=plan["lint_commands"],
    )
    orchestrator.attach_project_target(target)
    orchestrator.database.append_event(
        mission.id,
        "AI_PROJECT_PLANNED",
        {
            "project_target_id": str(target.id),
            "repository_name": plan["repository_name"],
            "language": plan["language"],
        },
    )
    specification_path = orchestrator.artifact_root / str(mission.id) / "artifacts"
    specification_path.mkdir(parents=True, exist_ok=True)
    (specification_path / "FIRST_SLICE.md").write_text(
        plan["first_slice_specification"], encoding="utf-8"
    )
    mission = orchestrator.transition_state(mission, MissionState.BUILDING)
    return mission, selected, decision, target


__all__ = ["MissionBlocked", "joust_it"]
