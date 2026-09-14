import pytest

from hackathon_competitor.approvals import ApprovalRequired
from hackathon_competitor.github_publish import (
    GitHubPublicationError,
    GitHubPublicationService,
    GitHubRepositoryService,
)
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
        self.created_repositories = []

    def create_repository(self, repository, *, visibility):
        self.created_repositories.append((repository, visibility))
        return self.repository(repository)

    def repository(self, repository):
        return {
            "nameWithOwner": repository,
            "visibility": "PUBLIC",
            "url": f"https://github.com/{repository}",
        }

    def push(self, remote, branch):
        self.pushes.append((remote, branch))
        return "pushed"

    def create_pull_request(self, repository, *, head, base, title, body):
        self.pull_requests.append((repository, head, base, title, body))
        return {"url": "https://github.com/owner/project/pull/4", "number": 4}

    def branch_sha(self, repository, branch):
        return "commit"

    def pull_request(self, repository, number):
        return {
            "url": "https://github.com/owner/project/pull/4",
            "number": number,
            "state": "open",
            "head": "joust/mission",
            "base": "main",
        }


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
        working_branch="joust/mission",
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
    action = service.request_push(target, change_set, idempotency_key="push-1")

    with pytest.raises(ApprovalRequired):
        service.push(action.id, target, change_set)
    assert not github.pushes

    decided = service.external.approvals.decide(
        action.approval_id, granted=True, explicit_confirmation=True, note="reviewed commit"
    )
    assert decided.status == ApprovalStatus.GRANTED
    assert service.push(action.id, target, change_set)["sha"] == "commit"
    assert service.push(action.id, target, change_set)["sha"] == "commit"
    assert github.pushes == [("owner/project", "joust/mission")]


def test_github_publish_rejects_default_branch_and_mismatched_pr(tmp_path):
    database, target, change_set = _setup(tmp_path)
    github = FakeGitHub()
    service = GitHubPublicationService(database, github)
    target.working_branch = target.default_branch
    with pytest.raises(GitHubPublicationError, match="default branch"):
        service.request_push(target, change_set, idempotency_key="push-default")

    target.working_branch = "joust/mission"
    action = service.request_pull_request(
        target, change_set, title="Build slice", idempotency_key="pr-1"
    )
    service.external.approvals.decide(action.approval_id, granted=True, explicit_confirmation=True)
    target.working_branch = "joust/other"
    with pytest.raises(GitHubPublicationError, match="approval"):
        service.create_pull_request(
            action.id,
            target,
            change_set,
            title="Build slice",
            body="body",
        )


def test_pull_request_success_requires_observed_remote_state(tmp_path):
    database, target, change_set = _setup(tmp_path)
    github = FakeGitHub()
    service = GitHubPublicationService(database, github)
    action = service.request_pull_request(
        target, change_set, title="Build slice", idempotency_key="pr-1"
    )
    service.external.approvals.decide(action.approval_id, granted=True, explicit_confirmation=True)

    result = service.create_pull_request(
        action.id,
        target,
        change_set,
        title="Build slice",
        body="body",
    )

    assert result["number"] == 4
    assert github.pull_requests == [
        ("owner/project", "joust/mission", "main", "Build slice", "body")
    ]


def test_repository_creation_is_approved_initialized_and_observed(tmp_path):
    database, target, _ = _setup(tmp_path)
    github = FakeGitHub()
    service = GitHubRepositoryService(database, github)
    action = service.request_creation(
        target.mission_id,
        repository="owner/joust-entry",
        visibility="public",
        initial_branch="main",
        initial_sha="commit",
        idempotency_key="repo-create-1",
    )
    service.external.approvals.decide(action.approval_id, granted=True, explicit_confirmation=True)

    result = service.create(action.id)

    assert result["repository"] == "owner/joust-entry"
    assert result["sha"] == "commit"
    assert github.created_repositories == [("owner/joust-entry", "public")]
    assert github.pushes == [("https://github.com/owner/joust-entry.git", "main")]
