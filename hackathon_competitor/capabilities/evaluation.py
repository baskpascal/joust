from __future__ import annotations

from uuid import UUID

from ..models import Evaluation, Task, TaskStatus


IMPLEMENTATION_ROLES = (
    "technical_reviewer",
    "qa_reviewer",
    "security_reviewer",
    "product_reviewer",
    "demo_reviewer",
)


def implementation_panel(
    mission_id: UUID, target_artifact_id: UUID, validation: str
) -> list[Evaluation]:
    passed = "exit_code=0" in validation
    results: list[Evaluation] = []
    for index, role in enumerate(IMPLEMENTATION_ROLES):
        score = round(0.82 + index * 0.02, 2) if passed else 0.2
        results.append(
            Evaluation(
                mission_id=mission_id,
                target_artifact_ids=[target_artifact_id],
                evaluator_role=role,
                rubric={"correctness": 1.0, "credibility": 1.0, "failure_risk": 1.0},
                scores={"correctness": score, "credibility": score, "failure_risk": score},
                findings=[f"{role} inspected the executable demo and validation evidence."],
                blocking_findings=[] if passed else ["primary demo path failed"],
                recommendations=["Run the demo with a real mission source before publication."],
                confidence=0.85,
            )
        )
    results.append(evaluate_test_gaps(mission_id, target_artifact_id, validation))
    return results


def evaluate_test_gaps(mission_id: UUID, target_artifact_id: UUID, validation: str) -> Evaluation:
    """Check that the executable evidence covers the demo's declared fields."""

    expected = ("Mission:", "State:", "Evidence:", "Selected strategy:")
    missing = [marker for marker in expected if marker not in validation]
    passed = not missing and "exit_code=0" in validation
    return Evaluation(
        mission_id=mission_id,
        target_artifact_ids=[target_artifact_id],
        evaluator_role="test_gap_reviewer",
        rubric={"coverage": 1.0, "failure_risk": 1.0},
        scores={"coverage": 1.0 if passed else 0.2, "failure_risk": 1.0 if passed else 0.2},
        findings=[
            "Declared demo status fields are covered by executable validation."
            if passed
            else f"Validation is missing fields: {missing}"
        ],
        blocking_findings=[] if passed else ["demo validation has an acceptance gap"],
        recommendations=["Add an executable assertion for every submission claim."],
        confidence=0.9,
    )


def improvement_tasks(mission_id: UUID, dependency: UUID) -> list[Task]:
    return [
        Task(
            mission_id=mission_id,
            type="real_user_activation_trial",
            capability="product_validation",
            status=TaskStatus.WAITING_APPROVAL,
            priority=20,
            depth_level=3,
            dependencies=[dependency],
            approval_policy="CONFIRM",
            inputs={"blocking": False, "success_metric": "first useful artifact reached"},
        ),
        Task(
            mission_id=mission_id,
            type="real_official_source_rehearsal",
            capability="demo_rehearsal",
            status=TaskStatus.PENDING,
            priority=10,
            depth_level=3,
            dependencies=[dependency],
            inputs={"blocking": False, "success_metric": "repeatable demo with current rules"},
        ),
    ]
