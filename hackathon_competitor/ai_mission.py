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

import hashlib
import json
from pathlib import Path
from uuid import UUID

from .ai import InvocationRecorder, ModelUnavailable, Reasoner, json_object
from .capabilities.ai_strategy import StrategyRejected, plan_project, strategize
from .capabilities.research import SourceFetcher, SourceUnreadable, discover_sources, extract_spec
from .models import (
    AIDecision,
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
                content_hash=hashlib.sha256(source.text.encode()).hexdigest(),
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


def _mission_facts(orchestrator: MissionOrchestrator, mission: Mission) -> dict:
    """Everything an answer is allowed to be built from: what is stored.

    A question about a mission must be answered from the mission, not from the
    model's memory of similar projects, so this is assembled once and the model
    is given nothing else.
    """

    database = orchestrator.database
    try:
        spec = database.get_spec_for_mission(mission.id)
    except KeyError:
        spec = None
    try:
        target = database.get_project_target_for_mission(mission.id)
    except KeyError:
        target = None
    candidates = database.list_strategy_candidates(mission.id)
    ai_decisions = database.list_ai_decisions(mission.id)
    active = {
        str(candidate.id): candidate
        for candidate in candidates
    }
    selected_ids = [
        decision.selected_option
        for decision in ai_decisions
        if decision.decision_type in {"strategy_selection", "strategy_reassessment"}
    ]
    current = active.get(selected_ids[-1]) if selected_ids else None
    change_sets = database.list_change_sets(mission.id) if hasattr(
        database, "list_change_sets"
    ) else []
    return {
        "mission_id": str(mission.id),
        "state": mission.state.value,
        "competition": spec.name if spec else None,
        "competition_url": spec.canonical_url if spec else None,
        "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "blockers": mission.blockers,
        "operator_instructions": [
            decision.rationale
            for decision in ai_decisions
            if decision.decision_type == "strategy_reassessment"
        ],
        "strategies_considered": [
            {
                "id": str(candidate.id),
                "product_thesis": candidate.product_thesis,
                "target_user": candidate.target_user,
                "winning_mechanism": candidate.winning_mechanism,
                "risks": candidate.risks,
            }
            for candidate in candidates
        ],
        "current_strategy": str(current.id) if current else None,
        "project": None
        if target is None
        else {
            "path": target.local_path,
            "language": target.language,
            "branch": target.working_branch,
            "test_commands": target.test_commands,
        },
        "change_sets": [
            {
                "commit_sha": item.commit_sha,
                "files": item.files[:20],
                "status": item.status,
                "generated_by": None
                if item.generated_by is None
                else {
                    "provider": item.generated_by.provider,
                    "model": item.generated_by.model,
                },
            }
            for item in change_sets
        ],
        "model_invocations": [
            {"purpose": item.purpose, "provider": item.provider, "status": item.status.value}
            for item in database.list_model_invocations(mission.id)
        ],
    }


def ask(
    orchestrator: MissionOrchestrator,
    mission_id: UUID,
    question: str,
    reasoner: Reasoner,
) -> str:
    """Answer a question about a mission from that mission's stored state."""

    mission = orchestrator.database.get_mission(mission_id)
    facts = _mission_facts(orchestrator, mission)
    prompt = (
        "Answer the question about this competition mission using only the facts "
        "below. They are the mission's stored state. If the facts do not contain the "
        "answer, say exactly what is missing instead of supplying it. Do not offer to "
        "do anything; just answer. Keep it under 200 words, plain prose, no markdown "
        "headings.\n\n"
        f"question={question}\n\nfacts={json.dumps(facts, sort_keys=True, default=str)}"
    )
    recorder = InvocationRecorder(orchestrator.database, mission.id)
    text, _ = recorder.run(reasoner, purpose="mission_question", prompt=prompt, context=facts)
    return text.strip()


def redirect(
    orchestrator: MissionOrchestrator,
    mission_id: UUID,
    instruction: str,
    reasoner: Reasoner,
) -> tuple[StrategyCandidate, AIDecision]:
    """Take a new constraint from the operator without losing the mission.

    Nothing is deleted: the strategies already generated stay, the evidence
    stays, and the earlier selection stays on the record as the decision it was.
    What changes is which strategy is active and why, and the instruction that
    changed it is stored next to the reason.
    """

    mission = orchestrator.database.get_mission(mission_id)
    candidates = orchestrator.database.list_strategy_candidates(mission.id)
    if not candidates:
        raise MissionBlocked(
            mission.id,
            "NO_STRATEGY_TO_REDIRECT",
            "this mission has no stored strategy candidates",
        )
    facts = _mission_facts(orchestrator, mission)
    listing = [
        {
            "id": str(candidate.id),
            "index": index,
            "product_thesis": candidate.product_thesis,
            "target_user": candidate.target_user,
            "recurring_job": candidate.recurring_job,
            "winning_mechanism": candidate.winning_mechanism,
            "risks": candidate.risks,
        }
        for index, candidate in enumerate(candidates)
    ]
    prompt = (
        "The operator has changed the mission's direction. Re-choose among the "
        "strategies already generated for this competition, under the new instruction. "
        "You may only choose one of the listed candidates. Explain the change in terms "
        "of the instruction and of what the mission already knows, and say what work "
        "done so far still stands.\n\n"
        "Return exactly one JSON object, no markdown:\n"
        '{"selected_index": 0, "rationale": "...", "what_still_stands": "..."}\n\n'
        f"instruction={instruction}\n"
        f"candidates={json.dumps(listing, sort_keys=True, default=str)}\n"
        f"mission={json.dumps(facts, sort_keys=True, default=str)}"
    )
    recorder = InvocationRecorder(orchestrator.database, mission.id)
    text, invocation = recorder.run(
        reasoner,
        purpose="strategy_reassessment",
        prompt=prompt,
        context={"instruction": instruction, "candidates": listing},
    )
    payload = json_object(text)
    index = payload.get("selected_index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(candidates):
        raise MissionBlocked(
            mission.id,
            "REDIRECT_SELECTION_INVALID",
            f"the model chose an index outside the candidate set: {index!r}",
        )
    rationale = str(payload.get("rationale") or "").strip()
    if len(rationale) < 40:
        raise MissionBlocked(
            mission.id, "REDIRECT_UNEXPLAINED", "the model changed course without saying why"
        )
    selected = candidates[index]
    ai_decision = recorder.record_decision(
        invocation,
        decision_type="strategy_reassessment",
        alternatives=listing,
        selected_option=str(selected.id),
        rationale=f"{instruction.strip()} -> {rationale}",
    )
    decision = Decision(
        mission_id=mission.id,
        question=f"What should this mission pursue now? ({instruction.strip()[:120]})",
        options=[
            {"id": item["id"], "title": item["product_thesis"][:120], "summary": item["recurring_job"]}
            for item in listing
        ],
        selected_option=str(selected.id),
        rationale=rationale,
        confidence=0.7,
        depth_level=4,
        reversible=True,
        reconsider_if=["the operator changes direction again", "the new constraint is resolved"],
    )
    orchestrator.database.save_decision(decision)
    # The earlier selection stays on the record; only the active strategy moves.
    mission.active_strategy_id = decision.id
    orchestrator.database.save_mission(mission)
    orchestrator.database.append_event(
        mission.id,
        "STRATEGY_REASSESSED",
        {
            "instruction": instruction[:500],
            "ai_decision_id": str(ai_decision.id),
            "invocation_id": str(invocation.id),
            "selected": str(selected.id),
            "what_still_stands": str(payload.get("what_still_stands") or "")[:500],
        },
    )
    return selected, ai_decision


__all__ = ["MissionBlocked", "ask", "joust_it", "redirect"]
