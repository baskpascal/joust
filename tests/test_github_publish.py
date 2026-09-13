import pytest

from hackathon_competitor.approvals import ApprovalRequired
from hackathon_competitor.github_publish import GitHubPublicationError, GitHubPublicationService
from hackathon_competitor.models import (
    ApprovalStatus,
    ChangeSet,
    Mission,
    ProjectMode,
    ProjectTarget,
)
from hackathon_competitor.storage import Database


class FakeGitHub:
    def __init__(self):
        self.pushes = []
        self.pull_requests = []

    def push(self, remote, branch):
        self.pushes.append((remote, branch))
        return "pushed"

    def create_pull_request(self, repository, *, head, base, title, body):
        self.pull_requests.append((repository, head, base, title, body))
        return {"url": "https://github.com/owner/project/pull/4", "number": 4}


def _setup(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="github", objective="publish", workspace_path=str(tmp_path))
    database.save_mission(mission)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(tmp_path / "project"),
        repository_url="owner/project",
        working_branch="galahad/mission",
    )
    change_set = ChangeSet(
        mission_id=mission.id,
        project_target_id=target.id,
        base_sha="base",
        diff_hash="diff",
        files=["main.py"],
        commit_sha="commit",
        status="validated",
    )
    database.save_project_target(target)
    database.save_change_set(change_set)
    return database, target, change_set


def test_github_publish_requires_matching_explicit_approval(tmp_path):
    database, target, change_set = _setup(tmp_path)
    github = FakeGitHub()
    service = GitHubPublicationService(database, github)
    approval = service.request_push(target, change_set)

    with pytest.raises(ApprovalRequired):
        service.push(approval.id, target, change_set, idempotency_key="push-1")
    assert not github.pushes

    decided = service.external.approvals.decide(
        approval.id, granted=True, explicit_confirmation=True, note="reviewed commit"
    )
    assert decided.status == ApprovalStatus.GRANTED
    assert service.push(approval.id, target, change_set, idempotency_key="push-1") == "pushed"
    assert service.push(approval.id, target, change_set, idempotency_key="push-1") == "pushed"
    assert github.pushes == [("origin", "galahad/mission")]


def test_github_publish_rejects_default_branch_and_mismatched_pr(tmp_path):
    database, target, change_set = _setup(tmp_path)
    github = FakeGitHub()
    service = GitHubPublicationService(database, github)
    target.working_branch = target.default_branch
    with pytest.raises(GitHubPublicationError, match="default branch"):
        service.request_push(target, change_set)

    target.working_branch = "galahad/mission"
    approval = service.request_pull_request(target, change_set, title="Build slice")
    service.external.approvals.decide(approval.id, granted=True, explicit_confirmation=True)
    target.working_branch = "galahad/other"
    with pytest.raises(GitHubPublicationError, match="approval"):
        service.create_pull_request(
            approval.id,
            target,
            change_set,
            title="Build slice",
            body="body",
            idempotency_key="pr-1",
        )
