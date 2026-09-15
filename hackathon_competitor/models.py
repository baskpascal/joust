from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class MonitorOutcome(StrEnum):
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    FAILED = "FAILED"
    LEASED_OUT = "LEASED_OUT"
    BACKING_OFF = "BACKING_OFF"


class StructuredSignalType(StrEnum):
    RULE = "RULE"
    METRIC = "METRIC"
    DEADLINE = "DEADLINE"
    LEADERBOARD = "LEADERBOARD"


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


class ExternalActionKind(StrEnum):
    REPOSITORY_CREATE = "repository_create"
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    DEPLOY = "deploy"
    AGENT_INDEX_UPDATE = "agent_index_update"
    VERIFICATION_REQUEST = "verification_request"
    FINAL_SUBMISSION = "final_submission"


class ExternalActionRisk(StrEnum):
    REMOTE_MUTATION = "REMOTE_MUTATION"
    PRODUCTION_MUTATION = "PRODUCTION_MUTATION"
    ACCOUNT_MUTATION = "ACCOUNT_MUTATION"
    IRREVERSIBLE_SUBMISSION = "IRREVERSIBLE_SUBMISSION"


class ExternalActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    AWAITING_EXTERNAL = "AWAITING_EXTERNAL"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


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


class AgentIdentity(Contract):
    """Installation-level identity; ``agent_id`` is immutable once bound."""

    agent_id: str = Field(min_length=1)
    product_name: str = "Joust"
    display_name: str = "Joust"
    brand: str = "Joust"
    command_cta: str = "Joust it."
    bound_at: datetime = Field(default_factory=utcnow)


class MonitorBackoffState(Contract):
    mission_id: UUID
    monitor_type: str
    consecutive_failures: int = Field(default=0, ge=0)
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    last_successful_observation_id: UUID | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class MonitorRunResult(Contract):
    outcome: MonitorOutcome
    mission_id: UUID
    monitor_type: str
    cycle_id: UUID | None = None
    observation_id: UUID | None = None
    fingerprint: str | None = None
    next_attempt_at: datetime | None = None


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
    # Set when a strategy pivot (``ai_mission.redirect``) replaces this target
    # with a new one for the same mission. A superseded target's evidence
    # (build runs, change sets) stays exactly as it is; nothing reads or
    # writes to it once superseded, and it is never returned by
    # ``get_project_target_for_mission``.
    superseded_at: datetime | None = None
    superseded_reason: str | None = None


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
    verification_only: bool = False
    generated_by: ModelProvenance | None = None
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


class SourceObservation(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    source_uri: str
    authority: str
    observed_at: datetime = Field(default_factory=utcnow)
    raw_text: str
    content_hash: str
    evidence_id: UUID


class Extraction(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    source_observation_id: UUID
    extractor: str
    extractor_version: str
    extracted_at: datetime = Field(default_factory=utcnow)
    signal_ids: list[UUID] = Field(default_factory=list)


class StructuredSignal(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    extraction_id: UUID
    source_observation_id: UUID
    source_evidence_id: UUID
    signal_type: StructuredSignalType
    observed_at: datetime = Field(default_factory=utcnow)
    authority: str
    confidence: float = Field(ge=0.0, le=1.0)


class RuleObservation(StructuredSignal):
    signal_type: Literal[StructuredSignalType.RULE] = StructuredSignalType.RULE
    category: str
    statement: str
    normalized_constraint: str


class MetricSignal(StructuredSignal):
    signal_type: Literal[StructuredSignalType.METRIC] = StructuredSignalType.METRIC
    metric: str
    value: float
    unit: str | None = None


class DeadlineSignal(StructuredSignal):
    signal_type: Literal[StructuredSignalType.DEADLINE] = StructuredSignalType.DEADLINE
    deadline_type: str
    deadline_at: datetime


class LeaderboardSignal(StructuredSignal):
    signal_type: Literal[StructuredSignalType.LEADERBOARD] = StructuredSignalType.LEADERBOARD
    agent_id: str
    rank: int | None = Field(default=None, ge=1)
    users: int | None = Field(default=None, ge=0)
    successful_installs: int | None = Field(default=None, ge=0)
    token_usage: int | None = Field(default=None, ge=0)


class PlowMetricsSnapshot(Contract):
    agent_id: str
    rank: int | None = Field(default=None, ge=1)
    users: int | None = Field(default=None, ge=0)
    successful_installs: int | None = Field(default=None, ge=0)
    token_usage: int | None = Field(default=None, ge=0)
    active_days: int | None = Field(default=None, ge=0)
    verified: bool
    captured_at: datetime = Field(default_factory=utcnow)


class CompetitionMetricsDelta(Contract):
    rank_change: int | None = None
    users_delta: int | None = None
    successful_installs_delta: int | None = None
    token_usage_delta: int | None = None
    token_growth_rate: float | None = None
    acquisition_growth_rate: float | None = None
    competitor_growth_rate: float | None = None


class CompetitionMetricInterpretation(Contract):
    bottleneck: str
    next_best_action: str
    rationale: str
    delta: CompetitionMetricsDelta


class GitHubRuntimeSnapshot(Contract):
    repository: str
    canonical_repository: str
    repository_url: str
    ref: str
    authenticated_account: str
    repo_accessible: bool
    push_permission: bool
    default_branch: str
    branch_protected: bool
    open_pull_requests: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    action_runs: list[dict[str, Any]] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utcnow)


class CurrentCompetitionState(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    version: int = Field(ge=1)
    reconciled_at: datetime = Field(default_factory=utcnow)
    active_rule_ids: list[UUID] = Field(default_factory=list)
    signal_ids: list[UUID] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    deadlines: dict[str, datetime] = Field(default_factory=dict)
    leaderboard: dict[str, dict[str, int | None]] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)


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


class AssessmentPlan(Contract):
    bottleneck: str
    candidates: list[ActionCandidate]


class Measurement(Contract):
    before: float
    after: float
    metric: str


class AdaptationPlan(Contract):
    next_bottleneck: str | None = None
    next_best_action: str | None = None
    mission_score: float | None = Field(default=None, ge=0.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    terminal_status: MissionStatus | None = None


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


class ProposedCommand(Contract):
    """A command that needs a human's yes before it runs, held durably.

    A command already rejected by `security_policy.classify_command` never
    becomes one of these — this contract exists only for a command that is
    genuinely permitted to run *with* approval, so the record itself only
    ever represents something a person could reasonably say yes to. What a
    user sees is `intent_summary`; `command` is the underlying text, present
    for evidence and an optional "technical details" disclosure, never the
    thing a user is asked to parse.
    """

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    command: str
    intent_summary: str
    category: str = "diagnostic"
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    decided_at: datetime | None = None
    decision_note: str | None = None


class AgentIndexEligibility(Contract):
    """Observed eligibility gate from the Agent Index publication flow."""

    agent_id: str
    registered: bool
    # None is not False. An unobserved input is an uncertainty, and reporting
    # it as a failed requirement would be as wrong as reporting it as met.
    license_is_mit: bool | None
    reporting_healthy: bool | None
    verified: bool
    eligible_to_win: bool
    blockers: list[str] = Field(default_factory=list)
    source_uri: str
    observed_at: datetime = Field(default_factory=utcnow)


class ProposedExternalAction(Contract):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    kind: ExternalActionKind
    target: str
    description: str
    risk: ExternalActionRisk
    approval_level: ApprovalLevel
    idempotency_key: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_state: dict[str, Any] = Field(default_factory=dict)
    approval_id: UUID
    status: ExternalActionStatus = ExternalActionStatus.PROPOSED
    execution_result: dict[str, Any] | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ObservedExternalResult(Contract):
    actual_state: dict[str, Any]
    matches_expected: bool
    source_uri: str
    summary: str
    # A third outcome for actions a third party must complete. Joust delivered
    # its side and observed the remote, and the remote has not acted yet. This
    # is neither success nor failure, and collapsing it into either one is the
    # synthetic claim the evidence system exists to prevent.
    pending_external: bool = False
    observed_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _pending_is_not_success(self) -> "ObservedExternalResult":
        if self.pending_external and self.matches_expected:
            raise ValueError("a pending external result cannot also match the expected state")
        return self


class ExternalActionObservation(ObservedExternalResult):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    action_id: UUID
    evidence_id: UUID


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


class ModelInvocationStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelInvocation(Contract):
    """One call to a real model, recorded whether or not it answered.

    Without this, nothing in the database distinguishes a decision a model
    made from a decision a hash made. The hashes are of the prompt and the
    context, not their text: the record proves which inputs produced which
    output without copying a competition's pages into the state database.
    """

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    purpose: str
    provider: str
    model: str
    input_context_hash: str
    prompt_hash: str
    started_at: datetime
    finished_at: datetime | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    status: ModelInvocationStatus
    output_artifact_ids: list[UUID] = Field(default_factory=list)
    error: str | None = None


class AIDecision(Contract):
    """An observable decision attributed to one invocation.

    It stores what was chosen, what it was chosen over, and a concise stated
    reason — never a private reasoning trace.
    """

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    invocation_id: UUID
    decision_type: str
    alternatives_considered: list[dict[str, Any]] = Field(default_factory=list)
    selected_option: str
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ModelProvenance(Contract):
    provider: str
    model: str
    invocation_id: UUID


class RepositoryContext(Contract):
    """What already exists in an attached project, read once before strategy.

    Test 15 found the actual gap this closes: a strategy proposed with no
    knowledge of an existing repository has no way to say "this already has
    tokenize() and reading_time_minutes(); build the new feature on top of
    those" — the reuse that did happen only happened because the
    implementation step could see the files directly. This is a read-only,
    static snapshot; nothing that produced it executed anything from the
    repository it describes.
    """

    local_path: str
    language: str | None = None
    framework: str | None = None
    tree: list[str] = Field(default_factory=list)
    readme_excerpt: str | None = None
    test_files: list[str] = Field(default_factory=list)
    public_api: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    current_branch: str | None = None
    commit_count: int = 0
    latest_commit_message: str | None = None


class StrategyCandidate(Contract):
    """One materially distinct way to compete, as a model proposed it."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    invocation_id: UUID
    product_thesis: str
    target_user: str
    recurring_job: str
    winning_mechanism: str
    technical_plan: str
    distribution_plan: str
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    expected_competitive_advantage: str
    created_at: datetime = Field(default_factory=utcnow)
