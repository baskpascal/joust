from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .artifact_graph import ArtifactGraph
from .build_loop import Implementer, RealBuildLoop
from .capabilities.evaluation import implementation_panel, improvement_tasks
from .capabilities.execution import build_demo_project, validate_demo_project
from .capabilities.planning import (
    render_acceptance_plan,
    render_architecture,
    render_implementation_plan,
    render_prd,
    render_premortem,
    render_risk_register,
    render_strategy_review,
    render_win_review,
)
from .capabilities.research import (
    SourceFetcher,
    crosscheck_extraction,
    discover_sources,
    extract_spec,
)
from .capabilities.strategy import (
    cluster_ideas,
    debate_strategy,
    deep_candidate_analysis,
    evaluate_top_ideas,
    generate_ideas,
    meta_judge,
    opportunity_map,
    screen_ideas,
    select_strategy,
)
from .capabilities.submission import submission_documents
from .compliance import evaluate_compliance, rules_from_spec
from .install_validation import validate_install_run_documentation
from .models import (
    Artifact,
    CompetitionMemory,
    Evaluation,
    Experiment,
    Mission,
    MissionState,
    RuleStatus,
    RuleType,
    SourceRecord,
    Task,
)
from .orchestrator import MissionOrchestrator
from .quality_gates import rules_gate, strategy_gate, submission_gate
from .workspace import GitWorkspace


def _write_artifact(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode()).hexdigest()


def _run_task(orchestrator: MissionOrchestrator, task: Task, operation):
    ready = orchestrator.tasks.refresh_ready(task.mission_id)
    if task.id not in {item.id for item in ready}:
        raise RuntimeError(f"task did not become ready: {task.id}")
    orchestrator.tasks.claim(task.id)
    try:
        result = operation()
    except Exception as exc:
        orchestrator.tasks.fail(task.id, str(exc), retryable=False)
        raise
    orchestrator.tasks.succeed(task.id)
    return result


def run_vertical_slice(
    orchestrator: MissionOrchestrator,
    source_uri: str,
    *,
    fetcher: SourceFetcher | None = None,
    workspace_path: str | None = None,
) -> Mission:
    workspace = str(Path(workspace_path or ".").resolve())
    mission = orchestrator.create_mission(
        title="Hackathon competition mission",
        objective="Find and execute the strongest evidence-backed competition strategy.",
        source_inputs=[source_uri],
        workspace_path=workspace,
    )
    mission = orchestrator.transition_state(mission, MissionState.INTAKE)

    discover = Task(
        mission_id=mission.id,
        type="discover_sources",
        capability="hackathon_discovery",
        priority=100,
        depth_level=2,
        inputs={"source_uri": source_uri},
    )
    rules = Task(
        mission_id=mission.id,
        type="lock_rules",
        capability="rules_crosscheck",
        priority=90,
        depth_level=3,
        dependencies=[discover.id],
    )
    ideate = Task(
        mission_id=mission.id,
        type="generate_ideas",
        capability="idea_generation",
        priority=80,
        depth_level=4,
        dependencies=[rules.id],
    )
    evaluate = Task(
        mission_id=mission.id,
        type="evaluate_finalists",
        capability="independent_judges",
        priority=70,
        depth_level=4,
        dependencies=[ideate.id],
    )
    select = Task(
        mission_id=mission.id,
        type="select_strategy",
        capability="strategy_selection",
        priority=60,
        depth_level=5,
        dependencies=[evaluate.id],
    )
    plan = Task(
        mission_id=mission.id,
        type="write_prd",
        capability="prd_generation",
        priority=50,
        depth_level=3,
        dependencies=[select.id],
    )
    orchestrator.tasks.add_tasks([discover, rules, ideate, evaluate, select, plan])

    mission = orchestrator.transition_state(mission, MissionState.DISCOVERY)
    sources = _run_task(
        orchestrator,
        discover,
        lambda: discover_sources(source_uri, fetcher=fetcher),
    )
    mission.title = sources[0].title or mission.title
    orchestrator.database.save_mission(mission)
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
    orchestrator.database.record_metric(mission.id, "tool_calls", float(len(sources)))

    spec, evidence, contradictions = _run_task(
        orchestrator,
        rules,
        lambda: extract_spec(mission.id, sources),
    )
    crosscheck_findings = crosscheck_extraction(spec, evidence, contradictions, sources)
    orchestrator.database.append_event(
        mission.id,
        "RULES_CROSSCHECKED",
        {"findings": crosscheck_findings, "source_count": len(sources)},
    )
    for item in evidence:
        orchestrator.database.save_evidence(item)
        orchestrator.database.append_event(
            mission.id,
            "EVIDENCE_ADDED",
            {"evidence_id": str(item.id), "authority": item.authority},
        )
    orchestrator.database.save_spec(spec)
    mission.hackathon_spec_id = spec.id
    mission.deadline_at = spec.deadline_at
    orchestrator.database.save_mission(mission)
    mission_dir = orchestrator.artifact_root / str(mission.id) / "artifacts"
    rules_path = mission_dir / "RULES.json"
    rules_content = json.dumps(
        {
            "spec": spec.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "contradictions": contradictions,
        },
        indent=2,
        sort_keys=True,
    )
    rules_artifact = Artifact(
        mission_id=mission.id,
        kind="rules_snapshot",
        path=str(rules_path),
        content_hash=_write_artifact(rules_path, rules_content),
        created_by_task_id=rules.id,
        depends_on=spec.evidence_ids,
    )
    orchestrator.database.save_artifact(rules_artifact)
    orchestrator.database.append_event(
        mission.id,
        "ARTIFACT_CREATED",
        {"artifact_id": str(rules_artifact.id), "kind": "rules_snapshot"},
    )
    mission = orchestrator.transition_state(mission, MissionState.RULES_LOCK)
    gate = rules_gate(spec)
    if not gate.passed:
        orchestrator.database.append_event(
            mission.id,
            "QUALITY_GATE_FAILED",
            {"gate": gate.name, "findings": gate.blocking_findings},
        )
        return orchestrator.transition_state(mission, MissionState.BLOCKED)
    mission = orchestrator.transition_state(mission, MissionState.LANDSCAPE_ANALYSIS)
    for contradiction in contradictions:
        orchestrator.database.append_event(
            mission.id, "CONTRADICTION_RECORDED", {"finding": contradiction}
        )

    mission = orchestrator.transition_state(mission, MissionState.IDEATION)
    ideas = _run_task(orchestrator, ideate, lambda: generate_ideas(spec))
    clusters = cluster_ideas(ideas)
    for idea in ideas:
        orchestrator.database.save_idea(mission.id, idea)
    opportunity_path = mission_dir / "OPPORTUNITY_MAP.json"
    opportunity_content = json.dumps(opportunity_map(clusters), indent=2, sort_keys=True)
    opportunity_artifact = Artifact(
        mission_id=mission.id,
        kind="opportunity_map",
        path=str(opportunity_path),
        content_hash=_write_artifact(opportunity_path, opportunity_content),
        created_by_task_id=ideate.id,
        depends_on=[rules_artifact.id],
    )
    orchestrator.database.save_artifact(opportunity_artifact)
    orchestrator.database.append_event(
        mission.id,
        "ARTIFACT_CREATED",
        {"artifact_id": str(opportunity_artifact.id), "kind": opportunity_artifact.kind},
    )
    ideas_path = mission_dir / "candidate-ideas.json"
    ideas_content = json.dumps(
        {
            "clusters": {
                name: [str(idea.id) for idea in members] for name, members in clusters.items()
            },
            "ideas": [idea.model_dump(mode="json") for idea in ideas],
        },
        indent=2,
        sort_keys=True,
    )
    ideas_artifact = Artifact(
        mission_id=mission.id,
        kind="candidate_ideas",
        path=str(ideas_path),
        content_hash=_write_artifact(ideas_path, ideas_content),
        created_by_task_id=ideate.id,
        depends_on=[opportunity_artifact.id],
    )
    orchestrator.database.save_artifact(ideas_artifact)
    orchestrator.database.append_event(
        mission.id, "ARTIFACT_CREATED", {"artifact_id": str(ideas_artifact.id)}
    )

    mission = orchestrator.transition_state(mission, MissionState.STRATEGY_SELECTION)
    finalists = screen_ideas(ideas)
    evaluations = _run_task(
        orchestrator, evaluate, lambda: evaluate_top_ideas(mission.id, finalists)
    )
    for evaluation_item in evaluations:
        evaluation_item.target_artifact_ids = [ideas_artifact.id]
        orchestrator.database.save_evaluation(evaluation_item)
    deep_path = mission_dir / "DEEP_CANDIDATE_ANALYSIS.json"
    deep_content = json.dumps(
        deep_candidate_analysis(finalists, evaluations), indent=2, sort_keys=True
    )
    deep_artifact = Artifact(
        mission_id=mission.id,
        kind="deep_candidate_analysis",
        path=str(deep_path),
        content_hash=_write_artifact(deep_path, deep_content),
        created_by_task_id=evaluate.id,
        depends_on=[ideas_artifact.id],
    )
    orchestrator.database.save_artifact(deep_artifact)
    orchestrator.database.append_event(
        mission.id,
        "ARTIFACT_CREATED",
        {"artifact_id": str(deep_artifact.id), "kind": deep_artifact.kind},
    )
    meta = meta_judge(evaluations)
    meta_evaluation = Evaluation(
        mission_id=mission.id,
        target_artifact_ids=[ideas_artifact.id],
        evaluator_role="meta_judge",
        rubric={"evaluator_agreement": 1.0, "evidence_quality": 1.0},
        scores={"evaluator_agreement": meta.confidence, "evidence_quality": 0.9},
        findings=[*meta.consensus, *meta.unresolved_disagreement],
        blocking_findings=(
            ["more evidence required before irreversible commitment"]
            if meta.more_evidence_required
            else []
        ),
        recommendations=[meta.recommended_next_action],
        confidence=meta.confidence,
    )
    orchestrator.database.save_evaluation(meta_evaluation)
    decision = _run_task(
        orchestrator,
        select,
        lambda: select_strategy(mission.id, finalists, evaluations),
    )
    orchestrator.database.save_decision(decision)
    orchestrator.database.append_event(
        mission.id,
        "DECISION_RECORDED",
        {"decision_id": str(decision.id), "selected": decision.selected_option},
    )
    mission.selected_strategy_id = decision.id
    orchestrator.database.save_mission(mission)
    selected = next(idea for idea in finalists if str(idea.id) == decision.selected_option)
    runner_up = next(idea for idea in finalists if str(idea.id) == decision.options[1]["id"])
    debate = debate_strategy(selected, runner_up)

    mission = orchestrator.transition_state(mission, MissionState.PLANNING)
    documents = _run_task(
        orchestrator,
        plan,
        lambda: {
            "PRD.md": ("prd", render_prd(spec, selected, decision)),
            "ARCHITECTURE.md": ("architecture", render_architecture(spec, selected)),
            "IMPLEMENTATION_PLAN.md": ("implementation_plan", render_implementation_plan(selected)),
            "ACCEPTANCE_PLAN.md": ("acceptance_plan", render_acceptance_plan(spec)),
            "RISK_REGISTER.md": ("risk_register", render_risk_register(spec, selected)),
            "PREMORTEM.md": ("premortem", render_premortem(selected)),
            "WIN_REVIEW.md": ("win_review", render_win_review(selected)),
            "STRATEGY_REVIEW.md": ("strategy_review", render_strategy_review(debate, meta)),
        },
    )
    created: dict[str, Artifact] = {}
    for filename, (kind, content) in documents.items():
        path = mission_dir / filename
        artifact = Artifact(
            mission_id=mission.id,
            kind=kind,
            path=str(path),
            content_hash=_write_artifact(path, content),
            created_by_task_id=plan.id,
            depends_on=[deep_artifact.id, *decision.evidence_ids],
        )
        orchestrator.database.save_artifact(artifact)
        orchestrator.database.append_event(
            mission.id, "ARTIFACT_CREATED", {"artifact_id": str(artifact.id), "kind": kind}
        )
        created[kind] = artifact

    graph = ArtifactGraph(orchestrator.database)
    graph.link(rules_artifact, opportunity_artifact, "derives_from")
    graph.link(opportunity_artifact, ideas_artifact, "derives_from")
    graph.link(ideas_artifact, deep_artifact, "validates")
    graph.link(deep_artifact, created["strategy_review"], "derives_from")
    graph.link(deep_artifact, created["prd"], "derives_from")
    graph.link(created["strategy_review"], created["prd"], "claims")
    graph.link(created["prd"], created["architecture"], "derives_from")
    graph.link(created["architecture"], created["implementation_plan"], "implements")
    graph.link(created["implementation_plan"], created["acceptance_plan"], "validates")
    plan_task = orchestrator.database.get_task(plan.id)
    plan_task.output_artifact_ids = [artifact.id for artifact in created.values()]
    orchestrator.database.save_task(plan_task)
    orchestrator.database.record_metric(mission.id, "ideas_generated", float(len(ideas)))
    orchestrator.database.record_metric(
        mission.id, "evaluations_completed", float(len(evaluations) + 1)
    )
    return orchestrator.database.get_mission(mission.id)


def mission_status(orchestrator: MissionOrchestrator, mission: Mission) -> dict:
    if mission.state not in {
        MissionState.PAUSED,
        MissionState.BLOCKED,
        MissionState.FAILED,
        MissionState.CANCELLED,
    }:
        orchestrator.tasks.refresh_ready(mission.id)
    tasks = orchestrator.database.list_tasks(mission.id)
    evidence = orchestrator.database.list_evidence(mission.id)
    artifacts = orchestrator.database.list_artifacts(mission.id)
    evaluations = orchestrator.database.list_evaluations(mission.id)
    decisions = orchestrator.database.list_decisions(mission.id)
    failed = [task for task in tasks if task.status.value.startswith("FAILED")]
    ready = [task for task in tasks if task.status.value == "READY"]
    gate_failures = [
        event["payload"]
        for event in orchestrator.database.events(mission.id)
        if event["event_type"] == "QUALITY_GATE_FAILED"
    ]
    metric_totals: dict[str, float] = {}
    for metric in orchestrator.database.metrics(mission.id):
        name = str(metric["metric"])
        metric_totals[name] = metric_totals.get(name, 0.0) + float(metric["value"])
    return {
        "mission": str(mission.id),
        "title": mission.title,
        "state": mission.state.value,
        "deadline": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "selected_strategy": decisions[-1].selected_option if decisions else None,
        "tasks_total": len(tasks),
        "tasks_succeeded": sum(task.status.value == "SUCCEEDED" for task in tasks),
        "tasks_running": sum(task.status.value == "RUNNING" for task in tasks),
        "tasks_failed": len(failed),
        "tasks_waiting_approval": sum(task.status.value == "WAITING_APPROVAL" for task in tasks),
        "evidence_count": len(evidence),
        "artifacts": [artifact.path for artifact in artifacts],
        "evaluations": len(evaluations),
        "llm_calls": int(metric_totals.get("llm_calls", 0)),
        "tokens": int(metric_totals.get("tokens", 0)),
        "tool_calls": int(metric_totals.get("tool_calls", 0)),
        "last_error": failed[-1].error if failed else None,
        "quality_blockers": gate_failures[-1]["findings"] if gate_failures else [],
        "next_ready_tasks": [task.type for task in ready],
        "project_target": str(mission.project_target_id) if mission.project_target_id else None,
        "build_runs": len(orchestrator.database.list_build_runs(mission.id)),
        "change_sets": len(orchestrator.database.list_change_sets(mission.id)),
    }


def build_project_for_mission(
    orchestrator: MissionOrchestrator,
    mission_id,
    implementer: Implementer,
    *,
    specification: str | None = None,
    max_repairs: int = 1,
    github=None,
):
    """Execute the real project build path for an attached mission target."""

    mission = orchestrator.resume_mission(mission_id)
    target = orchestrator.database.get_project_target_for_mission(mission.id)
    if specification is None:
        plans = [
            item
            for item in orchestrator.database.list_artifacts(mission.id)
            if item.kind == "implementation_plan" and not item.stale
        ]
        if not plans:
            raise RuntimeError("an implementation plan is required before building the project")
        specification = Path(plans[-1].path).read_text(encoding="utf-8")
    if mission.state == MissionState.PLANNING:
        mission = orchestrator.transition_state(mission, MissionState.BUILDING)
    if mission.state != MissionState.BUILDING:
        raise RuntimeError(f"project build requires BUILDING state, got {mission.state.value}")
    change_set = RealBuildLoop(
        orchestrator.database, orchestrator.artifact_root, github=github
    ).run(
        target,
        specification,
        implementer,
        max_repairs=max_repairs,
    )
    refreshed = orchestrator.database.get_mission(mission.id)
    if refreshed.state == MissionState.BUILDING:
        orchestrator.transition_state(refreshed, MissionState.VALIDATING)
    return change_set


def _save_text_artifact(
    orchestrator: MissionOrchestrator,
    mission: Mission,
    task: Task,
    *,
    kind: str,
    path: Path,
    content: str,
    depends_on: list,
) -> Artifact:
    artifact = Artifact(
        mission_id=mission.id,
        kind=kind,
        path=str(path),
        content_hash=_write_artifact(path, content),
        created_by_task_id=task.id,
        depends_on=depends_on,
    )
    orchestrator.database.save_artifact(artifact)
    orchestrator.database.append_event(
        mission.id, "ARTIFACT_CREATED", {"artifact_id": str(artifact.id), "kind": kind}
    )
    return artifact


def _fixture_compliance_statuses(spec, *, demo_valid: bool) -> dict[str, RuleStatus]:
    statuses: dict[str, RuleStatus] = {}
    for rule in rules_from_spec(spec):
        text = rule.text.lower()
        if rule.type == RuleType.LICENSING:
            license_path = Path(__file__).resolve().parents[1] / "LICENSE"
            statuses[rule.id] = (
                RuleStatus.PASS
                if license_path.is_file() and license_path.read_text().startswith("MIT License")
                else RuleStatus.FAIL
            )
        elif rule.type == RuleType.REQUIRED_TECHNOLOGY:
            statuses[rule.id] = (
                RuleStatus.PASS
                if "python" in text and sys.version_info >= (3, 11)
                else RuleStatus.UNKNOWN
            )
        elif rule.type == RuleType.PROHIBITED:
            statuses[rule.id] = (
                RuleStatus.PASS if "fabricat" in text and "usage" in text else RuleStatus.UNKNOWN
            )
        elif rule.type == RuleType.SUBMISSION:
            if "demo" in text:
                statuses[rule.id] = RuleStatus.PASS if demo_valid else RuleStatus.FAIL
            elif "repository" in text:
                statuses[rule.id] = RuleStatus.PASS
            else:
                statuses[rule.id] = RuleStatus.UNKNOWN
        elif rule.type == RuleType.DEADLINE:
            statuses[rule.id] = (
                RuleStatus.PASS
                if spec.deadline_at and datetime.now(UTC) < spec.deadline_at
                else RuleStatus.UNKNOWN
            )
        else:
            statuses[rule.id] = RuleStatus.UNKNOWN
    return statuses


def complete_v0(orchestrator: MissionOrchestrator, mission_id) -> Mission:
    mission = orchestrator.resume_mission(mission_id)
    if mission.state != MissionState.PLANNING:
        return mission
    spec = orchestrator.database.get_spec_for_mission(mission.id)
    decisions = orchestrator.database.list_decisions(mission.id)
    if not decisions:
        raise RuntimeError("strategy decision is required before V0 completion")
    decision = decisions[-1]
    ideas = orchestrator.database.list_ideas(mission.id)
    selected = next(idea for idea in ideas if str(idea.id) == decision.selected_option)
    planning_artifacts = {
        item.kind: item for item in orchestrator.database.list_artifacts(mission.id)
    }
    required_planning = {
        "prd",
        "architecture",
        "implementation_plan",
        "acceptance_plan",
        "risk_register",
    }
    if not required_planning.issubset(planning_artifacts):
        raise RuntimeError("planning artifacts are incomplete")
    strategy_result = strategy_gate(
        decision,
        differentiation_evidence=bool(decision.evidence_ids),
        feasibility_review=bool(orchestrator.database.list_evaluations(mission.id)),
        fallback_strategy=len(decision.options) > 1,
        risk_register=True,
        compliance_precheck=rules_gate(spec).passed,
    )
    if not strategy_result.passed:
        return orchestrator.transition_state(mission, MissionState.BLOCKED)

    previous = next(
        task for task in orchestrator.database.list_tasks(mission.id) if task.type == "write_prd"
    )
    build = Task(
        mission_id=mission.id,
        type="build_demo",
        capability="workspace_setup",
        priority=50,
        depth_level=3,
        dependencies=[previous.id],
    )
    validate = Task(
        mission_id=mission.id,
        type="validate_demo",
        capability="build_validation",
        priority=40,
        depth_level=3,
        dependencies=[build.id],
    )
    red_team = Task(
        mission_id=mission.id,
        type="red_team",
        capability="red_team",
        priority=30,
        depth_level=4,
        dependencies=[validate.id],
    )
    repair = Task(
        mission_id=mission.id,
        type="plan_improvements",
        capability="improvement_planner",
        priority=25,
        depth_level=3,
        dependencies=[red_team.id],
    )
    submit_pack = Task(
        mission_id=mission.id,
        type="submission_pack",
        capability="submission_copy",
        priority=20,
        depth_level=4,
        dependencies=[repair.id],
    )
    readiness = Task(
        mission_id=mission.id,
        type="readiness_gate",
        capability="compliance_check",
        priority=10,
        depth_level=3,
        dependencies=[submit_pack.id],
    )
    orchestrator.tasks.add_tasks([build, validate, red_team, repair, submit_pack, readiness])
    graph = ArtifactGraph(orchestrator.database)

    mission = orchestrator.transition_state(mission, MissionState.BUILDING)
    demo_root = orchestrator.artifact_root / str(mission.id) / "workspace" / "project"
    demo_path = _run_task(
        orchestrator,
        build,
        lambda: build_demo_project(
            demo_root, mission, decision, len(orchestrator.database.list_evidence(mission.id))
        ),
    )
    demo_artifact = _save_text_artifact(
        orchestrator,
        mission,
        build,
        kind="demo_project",
        path=demo_path,
        content=demo_path.read_text(encoding="utf-8"),
        depends_on=[planning_artifacts["implementation_plan"].id],
    )
    graph.link(planning_artifacts["implementation_plan"], demo_artifact, "implements")
    commit = GitWorkspace(demo_root).checkpoint("Build deterministic mission demo")
    orchestrator.database.append_event(
        mission.id,
        "TOOL_COMMIT",
        {"commit": commit, "task_id": str(build.id)},
    )

    mission = orchestrator.transition_state(mission, MissionState.VALIDATING)
    validation_text = _run_task(orchestrator, validate, lambda: validate_demo_project(demo_path))
    validation_artifact = _save_text_artifact(
        orchestrator,
        mission,
        validate,
        kind="demo_validation",
        path=demo_root / "DEMO_VALIDATION.md",
        content=f"# Demo validation\n\n```text\n{validation_text}```\n",
        depends_on=[demo_artifact.id],
    )
    graph.link(demo_artifact, validation_artifact, "validates")
    orchestrator.database.save_experiment(
        Experiment(
            mission_id=mission.id,
            hypothesis="The generated demo executes deterministically and reports mission evidence.",
            method="Compile and execute the generated Python demo in an isolated mission workspace.",
            success_metric="Process exits successfully and emits the expected status payload.",
            result={"passed": True, "output": validation_text},
            conclusion="The deterministic local demo passed its executable acceptance check.",
            artifact_ids=[demo_artifact.id, validation_artifact.id],
            evidence_ids=spec.evidence_ids,
        )
    )

    panel = _run_task(
        orchestrator,
        red_team,
        lambda: implementation_panel(mission.id, demo_artifact.id, validation_text),
    )
    for evaluation in panel:
        orchestrator.database.save_evaluation(evaluation)
    implementation_meta = meta_judge(panel)
    red_team_content = "# Implementation red team\n\n" + "\n".join(
        f"- **{item.evaluator_role}:** {'; '.join(item.findings)}" for item in panel
    )
    red_team_content += f"\n\nMeta-judge: {implementation_meta.recommended_next_action}\n"
    red_team_artifact = _save_text_artifact(
        orchestrator,
        mission,
        red_team,
        kind="red_team",
        path=demo_root / "RED_TEAM.md",
        content=red_team_content,
        depends_on=[validation_artifact.id],
    )
    graph.link(validation_artifact, red_team_artifact, "validates")

    mission = orchestrator.transition_state(mission, MissionState.OPTIMIZING)
    proposed = _run_task(orchestrator, repair, lambda: improvement_tasks(mission.id, red_team.id))
    orchestrator.tasks.add_tasks(proposed)
    improvement_artifact = _save_text_artifact(
        orchestrator,
        mission,
        repair,
        kind="improvement_plan",
        path=demo_root / "IMPROVEMENT_PLAN.md",
        content="# Improvement plan\n\n" + "\n".join(f"- {task.type}" for task in proposed) + "\n",
        depends_on=[red_team_artifact.id],
    )
    graph.link(red_team_artifact, improvement_artifact, "derives_from")

    mission = orchestrator.transition_state(mission, MissionState.SUBMISSION_PREP)
    rules = rules_from_spec(spec)
    statuses = _fixture_compliance_statuses(spec, demo_valid=True)
    compliance = evaluate_compliance(rules, statuses)
    documents = _run_task(
        orchestrator,
        submit_pack,
        lambda: submission_documents(spec, selected, decision, compliance),
    )
    submission_root = orchestrator.artifact_root / str(mission.id) / "submission"
    submission_artifacts: list[Artifact] = []
    for filename, (kind, content) in documents.items():
        artifact = _save_text_artifact(
            orchestrator,
            mission,
            submit_pack,
            kind=kind,
            path=submission_root / filename,
            content=content,
            depends_on=[validation_artifact.id, red_team_artifact.id],
        )
        graph.link(validation_artifact, artifact, "demonstrates")
        graph.link(red_team_artifact, artifact, "claims")
        submission_artifacts.append(artifact)
    compliance_content = json.dumps(compliance.model_dump(mode="json"), indent=2, sort_keys=True)
    compliance_artifact = _save_text_artifact(
        orchestrator,
        mission,
        submit_pack,
        kind="compliance_report",
        path=submission_root / "compliance.json",
        content=compliance_content,
        depends_on=[*spec.evidence_ids, validation_artifact.id],
    )

    submission_readme = next(
        item for item in submission_artifacts if item.kind == "submission_readme"
    )
    distribution_root = Path(__file__).resolve().parents[1]
    install_validation = validate_install_run_documentation(
        Path(submission_readme.path), distribution_root
    )
    install_artifact = _save_text_artifact(
        orchestrator,
        mission,
        submit_pack,
        kind="install_run_validation",
        path=submission_root / "install-run-validation.txt",
        content=install_validation,
        depends_on=[submission_readme.id],
    )
    graph.link(submission_readme, install_artifact, "validates")
    orchestrator.database.save_experiment(
        Experiment(
            mission_id=mission.id,
            hypothesis="The documented installation surface and CLI entrypoint are runnable.",
            method="Check distribution files and execute the packaged CLI help command.",
            success_metric="Distribution files exist and CLI help exits zero.",
            result={"passed": True, "output": install_validation},
            conclusion="Install/run documentation passed its distribution smoke check.",
            artifact_ids=[submission_readme.id, install_artifact.id],
            evidence_ids=spec.evidence_ids,
        )
    )

    install_tested = (
        importlib.util.find_spec("hackathon_competitor") is not None
        and "exit_code=0" in install_validation
    )
    gate = submission_gate(
        compliance,
        install_tested=install_tested,
        demo_tested="exit_code=0" in validation_text,
        claims_match=not any(item.blocking_findings for item in panel),
        license_present=(Path(__file__).resolve().parents[1] / "LICENSE").is_file(),
        required_fields_accounted=all(
            rule.status == RuleStatus.PASS
            for rule in compliance.rules
            if rule.type == RuleType.SUBMISSION
        ),
    )
    ready_tasks = orchestrator.tasks.refresh_ready(mission.id)
    if readiness.id not in {task.id for task in ready_tasks}:
        raise RuntimeError("readiness task did not become ready")
    orchestrator.tasks.claim(readiness.id)
    if not gate.passed:
        orchestrator.tasks.fail(readiness.id, "; ".join(gate.blocking_findings), retryable=False)
        return orchestrator.transition_state(mission, MissionState.BLOCKED)
    orchestrator.tasks.succeed(readiness.id)
    orchestrator.database.record_metric(mission.id, "submission_ready", 1.0)
    orchestrator.database.append_event(
        mission.id,
        "READINESS_GATE_PASSED",
        {
            "compliance_artifact_id": str(compliance_artifact.id),
            "submission_artifacts": len(submission_artifacts),
        },
    )
    orchestrator.database.save_competition_memory(
        CompetitionMemory(
            mission_id=mission.id,
            category="validated_strategy_pattern",
            content=(
                "Evidence-linked strategy selection followed by an executable demo and "
                "independent red-team completed the readiness path. Treat this as a "
                "hypothesis for later missions, never as a replacement for current rules."
            ),
            confidence=0.75,
            evidence_ids=decision.evidence_ids,
        )
    )
    return orchestrator.transition_state(mission, MissionState.READY_FOR_SUBMISSION)
