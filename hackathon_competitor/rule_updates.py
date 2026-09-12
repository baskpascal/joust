from __future__ import annotations

import hashlib
import json
from uuid import UUID

from .artifact_graph import ArtifactGraph
from .capabilities.research import (
    SourceFetcher,
    crosscheck_extraction,
    discover_sources,
    extract_spec,
)
from .models import Artifact, MissionState, SourceRecord, Task, TaskStatus
from .orchestrator import MissionOrchestrator


def _signature(spec) -> dict:
    payload = spec.model_dump(
        mode="json",
        exclude={"id", "version", "evidence_ids"},
    )
    for field in ("submission_requirements", "eligibility_requirements"):
        for requirement in payload[field]:
            requirement["evidence_ids"] = []
    return payload


def refresh_official_rules(
    orchestrator: MissionOrchestrator,
    mission_id: UUID,
    source_uri: str,
    *,
    fetcher: SourceFetcher | None = None,
):
    mission = orchestrator.resume_mission(mission_id)
    old_spec = orchestrator.database.get_spec_for_mission(mission.id)
    task = Task(
        mission_id=mission.id,
        type="refresh_official_rules",
        capability="continuous_research",
        status=TaskStatus.PENDING,
        priority=100,
        depth_level=3,
        inputs={"source_uri": source_uri},
    )
    orchestrator.tasks.add_tasks([task])
    orchestrator.tasks.refresh_ready(mission.id)
    orchestrator.tasks.claim(task.id)
    try:
        sources = discover_sources(source_uri, fetcher=fetcher)
        new_spec, evidence, contradictions = extract_spec(mission.id, sources)
        crosscheck_findings = crosscheck_extraction(new_spec, evidence, contradictions, sources)
    except Exception as exc:
        orchestrator.tasks.fail(task.id, str(exc), retryable=True)
        raise

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
    orchestrator.database.append_event(
        mission.id,
        "RULES_CROSSCHECKED",
        {"findings": crosscheck_findings, "source_count": len(sources)},
    )
    orchestrator.database.record_metric(mission.id, "tool_calls", float(len(sources)))
    if _signature(new_spec) == _signature(old_spec):
        orchestrator.tasks.succeed(task.id)
        orchestrator.database.append_event(
            mission.id, "RULES_CHECKED_NO_CHANGE", {"source_uri": source_uri}
        )
        return old_spec

    new_spec.version = old_spec.version + 1
    for item in evidence:
        orchestrator.database.save_evidence(item)
        orchestrator.database.append_event(
            mission.id,
            "EVIDENCE_ADDED",
            {"evidence_id": str(item.id), "authority": item.authority},
        )
    orchestrator.database.save_spec(new_spec)
    mission.hackathon_spec_id = new_spec.id
    orchestrator.database.save_mission(mission)

    previous_rules = [
        item
        for item in orchestrator.database.list_artifacts(mission.id)
        if item.kind == "rules_snapshot" and not item.stale
    ]
    if not previous_rules:
        orchestrator.tasks.fail(task.id, "current rules snapshot is missing", retryable=False)
        raise RuntimeError("current rules snapshot is missing")
    old_artifact = previous_rules[-1]
    stale = ArtifactGraph(orchestrator.database).upstream_changed(old_artifact.id)

    content = json.dumps(
        {
            "spec": new_spec.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "contradictions": contradictions,
        },
        indent=2,
        sort_keys=True,
    )
    path = (
        orchestrator.artifact_root
        / str(mission.id)
        / "artifacts"
        / f"RULES-v{new_spec.version}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    new_artifact = Artifact(
        mission_id=mission.id,
        kind="rules_snapshot",
        path=str(path),
        version=new_spec.version,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        created_by_task_id=task.id,
        depends_on=new_spec.evidence_ids,
    )
    orchestrator.database.save_artifact(new_artifact)
    ArtifactGraph(orchestrator.database).link(old_artifact, new_artifact, "supersedes")
    orchestrator.database.append_event(
        mission.id,
        "OFFICIAL_RULES_UPDATED",
        {
            "old_version": old_spec.version,
            "new_version": new_spec.version,
            "stale_artifacts": len(stale),
        },
    )
    orchestrator.tasks.succeed(task.id)

    reviews = [
        Task(
            mission_id=mission.id,
            type=f"review_stale_{artifact.kind}",
            capability="artifact_review",
            priority=80,
            depth_level=3,
            dependencies=[task.id],
            inputs={"artifact_id": str(artifact.id), "blocking": True},
        )
        for artifact in stale
        if artifact.kind
        in {"prd", "architecture", "demo_script", "pitch", "claims_map", "final_checklist"}
    ]
    orchestrator.tasks.add_tasks(reviews)
    if mission.state not in {MissionState.CANCELLED, MissionState.POSTMORTEM}:
        mission = orchestrator.transition_state(mission, MissionState.BLOCKED)
    return new_spec
