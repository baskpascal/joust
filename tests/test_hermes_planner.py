import json

import pytest

import hackathon_competitor.hermes_planner as planner_module
from hackathon_competitor.ai import ModelUnavailable
from hackathon_competitor.hermes_planner import (
    HermesCompetitionPlanner,
    HermesOneShotReasoner,
    ObservationOnlyExecutor,
    ReadinessMeasurer,
)
from hackathon_competitor.models import (
    ActionCandidate,
    ActionExecution,
    ActionExecutionStatus,
    ActionResult,
    CompetitionActionType,
    CompetitionCycle,
    CompetitionObservation,
    Mission,
)
from hackathon_competitor.storage import Database


class Reasoner:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete(self, prompt):
        self.last_prompt = prompt
        return self.response


class CapturingShell:
    calls = []
    scripted_response = "{}"
    raises: BaseException | None = None

    def __init__(self, root, *, environment=None):
        self.root = root
        self.environment = environment

    def run(self, argv, *, timeout_seconds):
        self.calls.append((argv, timeout_seconds))
        if CapturingShell.raises is not None:
            raise CapturingShell.raises
        return CapturingShell.scripted_response


def _mission_observation(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Plan", objective="compete", workspace_path=str(tmp_path))
    database.save_mission(mission)
    observation = CompetitionObservation(mission_id=mission.id, cycle_id=mission.id)
    return database, mission, observation


def test_hermes_planner_validates_and_clamps_build_candidate(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    response = json.dumps(
        {
            "bottleneck": "No implementation",
            "candidates": [
                {
                    "name": "Build",
                    "description": "Implement entry",
                    "action_type": "BUILD_PROJECT",
                    "parameters": {"specification": "Build a tested CLI", "max_repairs": 99},
                    "expected_outcome_improvement": 1.0,
                    "time_cost": 1.0,
                    "technical_risk": 0.1,
                    "regression_probability": 0.1,
                }
            ],
        }
    )
    planner = HermesCompetitionPlanner(
        database,
        Reasoner(f"```json\n{response}\n```"),
        allowed_action_types={CompetitionActionType.BUILD_PROJECT},
        max_repairs=2,
    )

    plan = planner.assess(mission, observation)

    assert plan.candidates[0].action_type == CompetitionActionType.BUILD_PROJECT
    assert plan.candidates[0].parameters["max_repairs"] == 2


def test_hermes_planner_rejects_unregistered_action(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    response = json.dumps(
        {
            "bottleneck": "Publish",
            "candidates": [
                {
                    "name": "Push",
                    "description": "Push without approval",
                    "action_type": "PUBLISH",
                    "expected_outcome_improvement": 1.0,
                    "time_cost": 1.0,
                    "technical_risk": 0.1,
                    "regression_probability": 0.1,
                }
            ],
        }
    )
    planner = HermesCompetitionPlanner(
        database,
        Reasoner(response),
        allowed_action_types={CompetitionActionType.CUSTOM},
    )

    with pytest.raises(ValueError, match="unsupported action"):
        planner.assess(mission, observation)


def test_hermes_planner_requires_sources_for_research(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    response = json.dumps(
        {
            "bottleneck": "Unknown rules",
            "candidates": [
                {
                    "name": "Research",
                    "description": "Read official rules",
                    "action_type": "RESEARCH",
                    "parameters": {},
                    "expected_outcome_improvement": 0.2,
                    "time_cost": 1.0,
                    "technical_risk": 0.0,
                    "regression_probability": 0.0,
                }
            ],
        }
    )
    planner = HermesCompetitionPlanner(
        database,
        Reasoner(response),
        allowed_action_types={CompetitionActionType.RESEARCH},
    )

    with pytest.raises(ValueError, match="omitted official source URLs"):
        planner.assess(mission, observation)


def test_readiness_measurement_never_invents_leaderboard_score(tmp_path):
    _, mission, observation = _mission_observation(tmp_path)
    action = ActionCandidate(
        name="Observe",
        description="No mutation",
        action_type=CompetitionActionType.CUSTOM,
        expected_outcome_improvement=0.1,
        time_cost=1.0,
        technical_risk=0.0,
        regression_probability=0.0,
    )
    execution = ActionExecution(
        mission_id=mission.id,
        cycle_id=observation.cycle_id,
        action=action,
        status=ActionExecutionStatus.SUCCEEDED,
        result=ActionResult(summary="observed"),
    )

    measurement = ReadinessMeasurer().measure(mission, observation, execution)

    assert measurement.metric == "project_readiness"
    assert measurement.before == measurement.after == 0.0


def test_observation_only_executor_names_no_mutation(tmp_path):
    _, mission, _ = _mission_observation(tmp_path)
    action = ActionCandidate(
        name="Watch",
        description="Observe",
        expected_outcome_improvement=0.1,
        time_cost=1.0,
        technical_risk=0.0,
        regression_probability=0.0,
    )

    result = ObservationOnlyExecutor().execute(mission, None, action)

    assert "no project mutation" in result.summary.lower()


def test_oneshot_reasoner_disables_project_rules_and_tools(tmp_path, monkeypatch):
    CapturingShell.calls = []
    monkeypatch.setattr(planner_module, "LocalShellTool", CapturingShell)
    reasoner = HermesOneShotReasoner(tmp_path, timeout_seconds=37)

    assert reasoner.complete("plan") == "{}"

    argv, timeout = CapturingShell.calls[-1]
    assert "--safe-mode" in argv
    assert "--ignore-rules" in argv
    assert argv[argv.index("--provider") + 1] == "plow"
    assert argv[argv.index("--model") + 1] == "anthropic/claude-sonnet-5"
    assert argv[argv.index("--reasoning") + 1] == "minimal"
    assert argv[argv.index("-t") + 1] == ""
    assert timeout == 37


@pytest.mark.parametrize(
    ("status_text", "expected_code"),
    [
        ('HTTP 401: {"detail":"Invalid or revoked token"}\n', "MODEL_AUTHENTICATION_FAILED"),
        ('HTTP 403: {"detail":"forbidden"}\n', "MODEL_AUTHENTICATION_FAILED"),
        ('HTTP 429: {"detail":"rate limited"}\n', "MODEL_RATE_LIMITED"),
        ('HTTP 503: {"detail":"upstream unavailable"}\n', "MODEL_PROVIDER_UNAVAILABLE"),
    ],
)
def test_an_http_failure_the_cli_printed_is_never_read_as_a_completion(
    tmp_path, monkeypatch, status_text, expected_code
):
    """A 401/403/429/5xx body still contains valid JSON — it must never be
    mistaken for a model's answer just because `json_object()` could parse
    it."""

    CapturingShell.calls = []
    CapturingShell.scripted_response = status_text
    CapturingShell.raises = None
    monkeypatch.setattr(planner_module, "LocalShellTool", CapturingShell)
    reasoner = HermesOneShotReasoner(tmp_path)

    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("plan")

    assert excinfo.value.code == expected_code
    assert "Invalid or revoked token" in excinfo.value.detail or status_text.strip().startswith(
        "HTTP"
    )


def test_a_normal_answer_that_happens_to_start_with_the_word_http_passes_through(
    tmp_path, monkeypatch
):
    CapturingShell.calls = []
    CapturingShell.scripted_response = '{"note": "HTTPS is required for the demo link"}'
    CapturingShell.raises = None
    monkeypatch.setattr(planner_module, "LocalShellTool", CapturingShell)
    reasoner = HermesOneShotReasoner(tmp_path)

    assert reasoner.complete("plan") == '{"note": "HTTPS is required for the demo link"}'


def test_a_shell_timeout_becomes_a_typed_model_timeout(tmp_path, monkeypatch):
    CapturingShell.calls = []
    CapturingShell.scripted_response = "{}"
    CapturingShell.raises = TimeoutError("exceeded")
    monkeypatch.setattr(planner_module, "LocalShellTool", CapturingShell)
    reasoner = HermesOneShotReasoner(tmp_path, timeout_seconds=42)

    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("plan")

    assert excinfo.value.code == "MODEL_TIMEOUT"
    CapturingShell.raises = None


def test_planner_prompt_omits_durable_ids_and_bounds_context(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    response = json.dumps(
        {
            "bottleneck": "Observe",
            "candidates": [
                {
                    "name": "Watch",
                    "description": "Collect evidence",
                    "action_type": "CUSTOM",
                    "expected_outcome_improvement": 0.1,
                    "time_cost": 1.0,
                    "technical_risk": 0.0,
                    "regression_probability": 0.0,
                }
            ],
        }
    )
    reasoner = Reasoner(response)
    planner = HermesCompetitionPlanner(
        database,
        reasoner,
        allowed_action_types={CompetitionActionType.CUSTOM},
    )

    planner.assess(mission, observation)

    # Mission, cycle, evidence, and target UUIDs add noise but no planning value.
    assert reasoner.last_prompt is not None
    assert str(mission.id) not in reasoner.last_prompt
    assert str(observation.cycle_id) not in reasoner.last_prompt
    assert len(reasoner.last_prompt) < 12000


def test_planner_prompt_includes_project_summary_and_recent_outcomes(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    (tmp_path / "README.md").write_text("Uses the official Agent Index client.", encoding="utf-8")
    from hackathon_competitor.models import ProjectMode, ProjectTarget

    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(tmp_path),
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)
    completed = CompetitionCycle(
        mission_id=mission.id,
        sequence=1,
        stage="ADAPT",
        selected_action=ActionCandidate(
            name="Confirm rules",
            description="Read official rules",
            action_type=CompetitionActionType.RESEARCH,
            parameters={"sources": ["https://competition.invalid"]},
            expected_outcome_improvement=0.1,
            time_cost=1.0,
            technical_risk=0.0,
            regression_probability=0.0,
        ),
        execution_result="Captured official source",
        verified=True,
        measured_delta=0.0,
        completed_at=mission.updated_at,
    )
    database.save_competition_cycle(completed)
    response = json.dumps(
        {
            "bottleneck": "Build value",
            "candidates": [
                {
                    "name": "Observe",
                    "description": "Wait for change",
                    "action_type": "CUSTOM",
                    "expected_outcome_improvement": 0.1,
                    "time_cost": 1.0,
                    "technical_risk": 0.0,
                    "regression_probability": 0.0,
                }
            ],
        }
    )
    reasoner = Reasoner(response)
    planner = HermesCompetitionPlanner(
        database,
        reasoner,
        allowed_action_types={CompetitionActionType.CUSTOM},
    )

    planner.assess(mission, observation)

    assert "official Agent Index client" in reasoner.last_prompt
    assert "Captured official source" in reasoner.last_prompt
    assert "Do not repeat a successful zero-delta action" in reasoner.last_prompt


def test_planner_timeout_falls_back_to_audited_local_build(tmp_path):
    database, mission, observation = _mission_observation(tmp_path)
    from hackathon_competitor.models import ProjectMode, ProjectTarget

    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(tmp_path),
        test_commands=[["python", "-m", "pytest", "-q"]],
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)

    class TimeoutReasoner:
        def complete(self, prompt):
            raise TimeoutError("slow provider")

    planner = HermesCompetitionPlanner(
        database,
        TimeoutReasoner(),
        allowed_action_types={
            CompetitionActionType.BUILD_PROJECT,
            CompetitionActionType.CUSTOM,
        },
    )

    plan = planner.assess(mission, observation)

    assert plan.candidates[0].action_type == CompetitionActionType.BUILD_PROJECT
    assert "Do not push" in plan.candidates[0].parameters["specification"]
    assert any(
        event["event_type"] == "COMPETITION_PLANNER_FALLBACK"
        for event in database.events(mission.id)
    )
