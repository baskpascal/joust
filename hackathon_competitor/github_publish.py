from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from .approvals import ExternalActionService
from .github import GitHubTool
from .models import (
    ApprovalLevel,
    ChangeSet,
    ExternalActionKind,
    ExternalActionRisk,
    ObservedExternalResult,
    ProjectTarget,
    ProposedExternalAction,
)
from .storage import Database


class GitHubPublicationError(RuntimeError):
    pass


class GitHubRepositoryService:
    """Approval-bound creation of an independent competition repository."""

    def __init__(self, database: Database, github: GitHubTool):
        self.database = database
        self.github = github
        self.external = ExternalActionService(database)

    def request_creation(
        self,
        mission_id: UUID,
        *,
        repository: str,
        visibility: str,
        initial_branch: str,
        initial_sha: str,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        description = (
            f"create {visibility} repository {repository} and initialize "
            f"{initial_branch} at {initial_sha}"
        )
        return self.external.propose(
            mission_id,
            kind=ExternalActionKind.REPOSITORY_CREATE,
            target=repository,
            description=description,
            risk=ExternalActionRisk.REMOTE_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={"visibility": visibility, "initial_branch": initial_branch},
            expected_state={
                "repository": repository,
                "visibility": visibility.upper(),
                "branch": initial_branch,
                "sha": initial_sha,
            },
        )

    def create(self, action_id: UUID) -> dict[str, Any]:
        proposed = self.database.get_external_action(action_id)
        visibility = proposed.payload.get("visibility")
        branch = proposed.payload.get("initial_branch")
        expected_sha = proposed.expected_state.get("sha")
        if not all(isinstance(item, str) and item for item in (visibility, branch, expected_sha)):
            raise GitHubPublicationError("repository proposal is missing initialization state")

        def execute(_key: str) -> dict[str, Any]:
            created = self.github.create_repository(proposed.target, visibility=visibility)
            self.github.push(f"https://github.com/{proposed.target}.git", branch)
            return created

        def observe(_result: Any) -> ObservedExternalResult:
            actual_repo = self.github.repository(proposed.target)
            actual_sha = self.github.branch_sha(proposed.target, branch)
            actual = {
                "repository": actual_repo.get("nameWithOwner"),
                "visibility": actual_repo.get("visibility"),
                "branch": branch,
                "sha": actual_sha,
                "url": actual_repo.get("url"),
            }
            matches = all(
                (
                    actual["repository"] == proposed.expected_state["repository"],
                    actual["visibility"] == proposed.expected_state["visibility"],
                    actual_sha == expected_sha,
                )
            )
            return ObservedExternalResult(
                actual_state=actual,
                matches_expected=matches,
                source_uri=str(actual.get("url") or f"https://github.com/{proposed.target}"),
                summary=(
                    "repository exists with the approved visibility and initial commit"
                    if matches
                    else "repository state does not match the approved initialization"
                ),
            )

        return self.external.execute(action_id, executor=execute, observer=observe).actual_state


class GitHubPublicationService:
    """Approval-bound push/PR operations for a validated mission change set."""

    def __init__(self, database: Database, github: GitHubTool):
        self.database = database
        self.github = github
        self.external = ExternalActionService(database)

    @staticmethod
    def _require_target(target: ProjectTarget, change_set: ChangeSet) -> tuple[str, str, str, str]:
        if target.mission_id != change_set.mission_id:
            raise GitHubPublicationError("target and change set belong to different missions")
        if not target.repository_url:
            raise GitHubPublicationError("GitHub publication requires a repository URL")
        if not target.working_branch:
            raise GitHubPublicationError("validated change set has no working branch")
        if target.working_branch == target.default_branch:
            raise GitHubPublicationError("direct publication to the default branch is forbidden")
        if not change_set.commit_sha:
            raise GitHubPublicationError("validated change set has no commit SHA")
        if change_set.status != "validated":
            raise GitHubPublicationError("only a validated change set can be published")
        if target.repository_owner and target.repository_name:
            repository = f"{target.repository_owner}/{target.repository_name}"
        else:
            parsed = urlparse(target.repository_url)
            repository = parsed.path.strip("/").removesuffix(".git")
            if not repository or "/" not in repository:
                repository = target.repository_url
        return repository, target.repository_url, target.working_branch, change_set.commit_sha

    def request_push(
        self,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        repository, _push_target, branch, commit = self._require_target(target, change_set)
        action = f"push {repository} {branch} {commit} diff={change_set.diff_hash}"
        return self.external.propose(
            change_set.mission_id,
            kind=ExternalActionKind.PUSH,
            target=repository,
            description=action,
            risk=ExternalActionRisk.REMOTE_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={"branch": branch, "commit": commit, "diff_hash": change_set.diff_hash},
            expected_state={"branch": branch, "sha": commit},
        )

    def push(
        self,
        action_id: UUID,
        target: ProjectTarget,
        change_set: ChangeSet,
    ) -> dict[str, Any]:
        repository, push_target, branch, commit = self._require_target(target, change_set)
        proposed = self.database.get_external_action(action_id)
        if proposed.expected_state != {"branch": branch, "sha": commit}:
            raise GitHubPublicationError("approval does not match the target commit or diff")
        observation = self.external.execute(
            action_id,
            executor=lambda _key: {"output": self.github.push(push_target, branch)},
            observer=lambda _result: self._observe_push(repository, branch, commit),
        )
        return observation.actual_state

    def _observe_push(self, repository: str, branch: str, commit: str) -> ObservedExternalResult:
        remote_sha = self.github.branch_sha(repository, branch)
        return ObservedExternalResult(
            actual_state={"branch": branch, "sha": remote_sha},
            matches_expected=remote_sha == commit,
            source_uri=f"https://github.com/{repository}/tree/{branch}",
            summary=(
                "remote branch matches the validated local commit"
                if remote_sha == commit
                else f"remote SHA {remote_sha} does not match expected {commit}"
            ),
        )

    def request_pull_request(
        self,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        title: str,
        idempotency_key: str,
    ) -> ProposedExternalAction:
        repository, _push_target, branch, commit = self._require_target(target, change_set)
        action = (
            f"pull_request {repository} {branch}->{target.default_branch} "
            f"{commit} diff={change_set.diff_hash} title={title}"
        )
        return self.external.propose(
            change_set.mission_id,
            kind=ExternalActionKind.PULL_REQUEST,
            target=repository,
            description=action,
            risk=ExternalActionRisk.REMOTE_MUTATION,
            approval_level=ApprovalLevel.CONFIRM,
            idempotency_key=idempotency_key,
            payload={"head": branch, "base": target.default_branch, "title": title},
            expected_state={"head": branch, "base": target.default_branch, "state": "open"},
        )

    def create_pull_request(
        self,
        action_id: UUID,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        repository, _push_target, branch, commit = self._require_target(target, change_set)
        action = (
            f"pull_request {repository} {branch}->{target.default_branch} "
            f"{commit} diff={change_set.diff_hash} title={title}"
        )
        proposed = self.database.get_external_action(action_id)
        if proposed.description != action:
            raise GitHubPublicationError("approval does not match the requested pull request")
        observation = self.external.execute(
            action_id,
            executor=lambda _key: self.github.create_pull_request(
                repository,
                head=branch,
                base=target.default_branch,
                title=title,
                body=body,
            ),
            observer=lambda result: self._observe_pull_request(
                repository, result, branch, target.default_branch
            ),
        )
        return observation.actual_state

    def _observe_pull_request(
        self,
        repository: str,
        result: Any,
        head: str,
        base: str,
    ) -> ObservedExternalResult:
        if not isinstance(result, dict) or not isinstance(result.get("number"), int):
            raise GitHubPublicationError("GitHub PR result omitted its number")
        actual = self.github.pull_request(repository, result["number"])
        matches = (
            actual.get("head") == head
            and actual.get("base") == base
            and actual.get("state") == "open"
        )
        return ObservedExternalResult(
            actual_state=actual,
            matches_expected=matches,
            source_uri=str(actual.get("url") or f"https://github.com/{repository}/pulls"),
            summary=(
                "pull request is open with the approved head and base"
                if matches
                else "observed pull request does not match the approved head/base state"
            ),
        )
