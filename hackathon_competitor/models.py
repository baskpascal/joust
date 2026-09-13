from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionState(StrEnum):
    CREATED = "CREATED"
    INTAKE = "INTAKE"
    DISCOVERY = "DISCOVERY"
    RULES_LOCK = "RULES_LOCK"
    LANDSCAPE_ANALYSIS = "LANDSCAPE_ANALYSIS"
    IDEATION = "IDEATION"
    STRATEGY_SELECTION = "STRATEGY_SELECTION"
    PLANNING = "PLANNING"
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    OPTIMIZING = "OPTIMIZING"
    SUBMISSION_PREP = "SUBMISSION_PREP"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED = "SUBMITTED"
    POSTMORTEM = "POSTMORTEM"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MissionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    STOPPED_BY_USER = "STOPPED_BY_USER"
    IRRECOVERABLY_BLOCKED = "IRRECOVERABLY_BLOCKED"


class CompetitionType(StrEnum):
    BUILD = "BUILD"
    AGENT_USAGE = "AGENT_USAGE"
    DATA_SCIENCE = "DATA_SCIENCE"
    OPTIMIZATION = "OPTIMIZATION"
    SECURITY = "SECURITY"
    GAME = "GAME"
    BENCHMARK = "BENCHMARK"
    GENERIC = "GENERIC"


class CompetitionRuleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class CompeteStage(StrEnum):
    OBSERVE = "OBSERVE"
    ASSESS = "ASSESS"
    STRATEGIZE = "STRATEGIZE"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    MEASURE = "MEASURE"
    ADAPT = "ADAPT"


class CompetitionActionType(StrEnum):
    BUILD_PROJECT = "BUILD_PROJECT"
    RESEARCH = "RESEARCH"
    TEST_PROJECT = "TEST_PROJECT"
    PREPARE_SUBMISSION = "PREPARE_SUBMISSION"
    PUBLISH = "PUBLISH"
    DEPLOY = "DEPLOY"
    CUSTOM = "CUSTOM"


class ActionExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ProjectMode(StrEnum):
    EXISTING_REPO = "existing_repo"
    NEW_REPO = "new_repo"
    LOCAL_ONLY = "local_only"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class RuleType(StrEnum):
    ELIGIBILITY = "eligibility"
    REQUIRED_TECHNOLOGY = "required_technology"
    PROHIBITED = "prohibited"
    SUBMISSION = "submission"
    LICENSING = "licensing"
    DEADLINE = "deadline"
    JUDGING = "judging"


class RuleSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class RuleStatus(StrEnum):
    UNKNOWN = "unknown"
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class ApprovalLevel(StrEnum):
    AUTO = "AUTO"
    CONFIRM = "CONFIRM"
    HUMAN_ONLY = "HUMAN_ONLY"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class Criterion(Contract):
    name: str
    description: str = ""
    weight: float = 1.0


class Requirement(Contract):
    id: str
    text: str
    blocking: bool = True
    evidence_ids: list[UUID] = Field(default_factory=list)


class Resource(Contract):
    name: str
    uri: str
    description: str = ""


class Mission(Contract):
    id: UUID = Field(default_factory=uuid4)
    title: str
    state: MissionState = MissionState.CREATED
    status: MissionStatus = MissionStatus.ACTIVE
    objective: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deadline_at: datetime | None = None
    timezone: str | None = None
    source_inputs: list[str] = Field(default_factory=list)
    hackathon_spec_id: UUID | None = None
    competition_id: UUID | None = None
    entrant_profile_id: UUID | None = None
    selected_strategy_id: UUID | None = None
    active_strategy_id: UUID | None = None
    project_target_id: UUID | None = None
    submission_id: UUID | None = None
    current_bottleneck: str | None = None
    current_best_action: str | None = None
    mission_score: float | None = Field(default=None, ge=0.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    blockers: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    workspace_path: str


class EntrantProfile(Contract):
    id: UUID = Field(default_factory=uuid4)
    display_name: str
    attribution_name: str | None = None
    github_identity: str | None = None
    discord_identity: str | None = None
    platform_identities: dict[str, str] = Field(default_factory=dict)
    team_members: list[str] = Field(default_factory=list)
    default_public_attribution: str | None = None


class ProjectTarget(Contract):
    """The concrete codebase a mission is allowed to inspect and change."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    mode: ProjectMode
    local_path: str
    repository_url: str | None = None
    repository_owner: str | None = None
    repository_name: str | None = None
    default_branch: str = "main"
    working_branch: str | None = None
    language: str | None = None
    framework: str | None = None
    install_commands: list[list[str]] = Field(default_factory=list)
    dev_commands: list[list[str]] = Field(default_factory=list)
    build_commands: list[list[str]] = Field(default_factory=list)
    test_commands: list[list[str]] = Field(default_factory=list)
    lint_commands: list[list[str]] = Field(default_factory=list)
    run_commands: list[list[str]] = Field(default_factory=list)
    deployment_requirement: str | None = None
    deploy_target: str | None = None
    base_commit_sha: str | None = None
    final_commit_sha: str | None = None
    # Optional names explicitly approved for the target's local build process.
    # The default environment is intentionally reduced to a small, non-secret
    # base set by ``build_loop.project_environment``.
    environment_allowlist: list[str] = Field(default_factory=list)


class RepositorySnapshot(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    project_target_id: UUID
    repository_url: str | None = None
    branch: str | None = None
    commit_sha: str
    tree_hash: str | None = None
    dirty: bool = False
    captured_at: datetime = Field(default_factory=utcnow)


class BuildRun(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    project_target_id: UUID
    commit_sha: str | None = None
    command: list[str]
    phase: str
    exit_code: int | None = None
    log_path: str | None = None
    output_artifact_id: UUID | None = None
    passed: bool = False
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None


class ChangeSet(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    project_target_id: UUID
    base_sha: str
    diff_hash: str
    files: list[str] = Field(default_factory=list)
    commit_sha: str | None = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=utcnow)


class HackathonSpec(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    name: str
    organizer: str | None = None
    canonical_url: str | None = None
    competition_type: CompetitionType = CompetitionType.GENERIC
    start_at: datetime | None = None
    build_deadline_at: datetime | None = None
    submission_deadline_at: datetime | None = None
    final_snapshot_at: datetime | None = None
    result_at: datetime | None = None
    deadline_at: datetime | None = None
    deadline_explicitly_unknown: bool = False
    judging_mode: str | None = None
    leaderboard_model: str | None = None
    judging_criteria: list[Criterion] = Field(default_factory=list)
    scoring_rules: list[str] = Field(default_factory=list)
    required_technologies: list[str] = Field(default_factory=list)
    mandatory_integrations: list[str] = Field(default_factory=list)
    allowed_technologies: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    submission_requirements: list[Requirement] = Field(default_factory=list)
    eligibility_requirements: list[Requirement] = Field(default_factory=list)
    sponsor_resources: list[Resource] = Field(default_factory=list)
    submission_platform: str | None = None
    rule_sources: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    rules_locked: bool = False
    version: int = Field(default=1, ge=1)
    evidence_ids: list[UUID] = Field(default_factory=list)


class CompetitionRule(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    source_id: UUID | None = None
    observed_at: datetime = Field(default_factory=utcnow)
    effective_at: datetime | None = None
    category: str
    statement: str
    normalized_constraint: str
    authority: str
    confidence: float = Field(ge=0.0, le=1.0)
    supersedes_rule_id: UUID | None = None
    status: CompetitionRuleStatus = CompetitionRuleStatus.ACTIVE


class CompetitionSpec(HackathonSpec):
    """Joust-facing name for the backward-compatible competition contract."""


class ActionCandidate(Contract):
    name: str
    description: str
    action_type: CompetitionActionType = CompetitionActionType.CUSTOM
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_outcome_improvement: float = Field(ge=0.0)
    time_cost: float = Field(gt=0.0)
    technical_risk: float = Field(ge=0.0)
    regression_probability: float = Field(ge=0.0, le=1.0)

    @property
    def utility(self) -> float:
        denominator = self.time_cost + self.technical_risk + self.regression_probability
        return self.expected_outcome_improvement / denominator


class CompetitionCycle(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    sequence: int = Field(ge=1)
    stage: CompeteStage = CompeteStage.OBSERVE
    observation: str | None = None
    observation_evidence_ids: list[UUID] = Field(default_factory=list)
    bottleneck: str | None = None
    candidate_actions: list[ActionCandidate] = Field(default_factory=list)
    selected_action: ActionCandidate | None = None
    execution_result: str | None = None
    execution_succeeded: bool | None = None
    verification_finding: str | None = None
    verification_evidence_ids: list[UUID] = Field(default_factory=list)
    verified: bool | None = None
    metric_before: float | None = None
    metric_after: float | None = None
    measured_delta: float | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class CompetitionObservation(Contract):
    """A durable observation of competition and project state for one cycle."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    cycle_id: UUID
    observed_at: datetime = Field(default_factory=utcnow)
    deadline_at: datetime | None = None
    deadline_state: str = "unknown"
    active_rule_ids: list[UUID] = Field(default_factory=list)
    project_target_id: UUID | None = None
    repository_exists: bool = False
    repository_revision: str | None = None
    repository_dirty: bool | None = None
    latest_change_status: str | None = None
    build_summary: dict[str, int] = Field(default_factory=dict)
    github_checks: list[dict[str, Any]] = Field(default_factory=list)
    deployment_health: dict[str, Any] | None = None
    submission_state: str | None = None
    score_signals: dict[str, float] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ActionResult(Contract):
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    change_set_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class ActionExecution(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    cycle_id: UUID
    action: ActionCandidate
    status: ActionExecutionStatus = ActionExecutionStatus.RUNNING
    result: ActionResult | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class Task(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    parent_id: UUID | None = None
    type: str
    capability: str
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    depth_level: int = Field(default=1, ge=1, le=5)
    dependencies: list[UUID] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_artifact_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    max_retries: int = Field(default=2, ge=0)
    retry_count: int = Field(default=0, ge=0)
    approval_policy: str = "AUTO"
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_after: datetime | None = None
    error: str | None = None


class Evidence(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    claim: str
    source_type: str
    source_uri: str | None = None
    source_artifact_id: UUID | None = None
    excerpt: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    authority: str
    retrieved_at: datetime = Field(default_factory=utcnow)
    valid_until: datetime | None = None


class SourceRecord(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    uri: str
    authority: str
    source_type: str
    content_hash: str
    retrieved_at: datetime = Field(default_factory=utcnow)
    status: str = "available"


class CompetitionMemory(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    category: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class Decision(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    question: str
    options: list[dict[str, Any]]
    selected_option: str
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    depth_level: int = Field(ge=1, le=5)
    reversible: bool
    reconsider_if: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class Artifact(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    kind: str
    path: str
    version: int = Field(default=1, ge=1)
    content_hash: str
    status: str = "current"
    created_by_task_id: UUID
    depends_on: list[UUID] = Field(default_factory=list)
    stale: bool = False


class Evaluation(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    target_artifact_ids: list[UUID] = Field(default_factory=list)
    evaluator_role: str
    rubric: dict[str, float]
    scores: dict[str, float]
    findings: list[str] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class Rule(Contract):
    id: str
    text: str
    type: RuleType
    severity: RuleSeverity
    evidence_ids: list[UUID] = Field(default_factory=list)
    verification_method: str
    status: RuleStatus = RuleStatus.UNKNOWN


class Experiment(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    hypothesis: str
    method: str
    success_metric: str
    result: dict[str, Any] | None = None
    conclusion: str | None = None
    artifact_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class Approval(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    action: str
    level: ApprovalLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None
    decision_note: str | None = None


class DebateRecord(Contract):
    proposal: str
    pro_arguments: list[str]
    con_arguments: list[str]
    alternative_proposal: str
    evidence_comparison: list[str]
    judge_decision: str


class MetaJudgeResult(Contract):
    consensus: list[str]
    unresolved_disagreement: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_next_action: str
    more_evidence_required: bool


class ComplianceReport(Contract):
    rules: list[Rule]
    blocker_failures: list[str]
    blocker_unknowns: list[str]
    ready: bool


class QualityGateResult(Contract):
    name: str
    passed: bool
    blocking_findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DeadlineGuidance(Contract):
    mode: str
    hours_remaining: float
    max_reasoning_depth: int = Field(ge=1, le=5)
    architecture_frozen: bool
    risky_changes_require_confirmation: bool
    priorities: list[str]


class Idea(Contract):
    id: UUID = Field(default_factory=uuid4)
    title: str
    summary: str
    batch: str
    dimensions: dict[str, float]
    evidence_ids: list[UUID] = Field(default_factory=list)


class CapabilityResult(Contract):
    summary: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    proposed_tasks: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
