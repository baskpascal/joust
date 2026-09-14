from datetime import UTC, datetime, timedelta
from uuid import uuid4

from hackathon_competitor.compliance import inspect_project_target
from hackathon_competitor.models import (
    BuildRun,
    HackathonSpec,
    ProjectMode,
    ProjectTarget,
    Requirement,
)


def test_project_inspector_checks_target_license_and_repository(tmp_path):
    mission_id = uuid4()
    project = tmp_path / "project"
    project.mkdir()
    (project / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (project / "app.py").write_text("print('ok')\n", encoding="utf-8")
    spec = HackathonSpec(
        mission_id=mission_id,
        name="TestFest",
        required_technologies=["Use Python 3.11 or newer."],
        submission_requirements=[
            Requirement(id="repo", text="Submit a public repository."),
            Requirement(id="demo", text="Provide a demo."),
        ],
        prohibited_actions=["Do not fabricate usage."],
    )
    target = ProjectTarget(
        mission_id=mission_id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(project),
        repository_url="https://github.com/owner/project",
        language="Python",
    )
    report = inspect_project_target(
        spec,
        target,
        build_runs=[
            BuildRun(
                mission_id=mission_id,
                project_target_id=target.id,
                command=["python", "-m", "pytest"],
                phase="run",
                passed=True,
            )
        ],
    )
    statuses = {rule.id: rule.status.value for rule in report.rules}
    assert statuses["repo"] == "pass"
    assert statuses["required-tech-0"] == "pass"
    assert statuses["demo"] == "pass"
    assert statuses["prohibited-0"] == "unknown"
    assert not report.ready


def test_project_inspector_does_not_use_agent_license(tmp_path):
    mission_id = uuid4()
    project = tmp_path / "project"
    project.mkdir()
    spec = HackathonSpec(
        mission_id=mission_id,
        name="TestFest",
        eligibility_requirements=[
            Requirement(id="license", text="The project must use the MIT license.")
        ],
    )
    target = ProjectTarget(
        mission_id=mission_id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(project),
    )
    report = inspect_project_target(spec, target)
    assert report.rules[0].status.value == "fail"


def test_project_inspector_evaluates_known_deadline(tmp_path):
    mission_id = uuid4()
    project = tmp_path / "project"
    project.mkdir()
    target = ProjectTarget(
        mission_id=mission_id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(project),
    )
    future = HackathonSpec(
        mission_id=mission_id,
        name="Future",
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
    )
    past = future.model_copy(update={"deadline_at": datetime.now(UTC) - timedelta(hours=1)})
    assert inspect_project_target(future, target).rules[-1].status.value == "pass"
    assert inspect_project_target(past, target).rules[-1].status.value == "fail"
