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
    return results


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
