from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from .approvals import ExternalActionService
from .github import GitHubTool
from .models import Approval, ApprovalLevel, ChangeSet, ProjectTarget
from .storage import Database


class GitHubPublicationError(RuntimeError):
    pass


class GitHubPublicationService:
    """Approval-bound push/PR operations for a validated mission change set."""

    def __init__(self, database: Database, github: GitHubTool):
        self.database = database
        self.github = github
        self.external = ExternalActionService(database)

    @staticmethod
    def _require_target(target: ProjectTarget, change_set: ChangeSet) -> tuple[str, str, str]:
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
        return target.repository_url, target.working_branch, change_set.commit_sha

    def request_push(self, target: ProjectTarget, change_set: ChangeSet) -> Approval:
        repository, branch, commit = self._require_target(target, change_set)
        action = f"push {repository} {branch} {commit} diff={change_set.diff_hash}"
        return self.external.request(change_set.mission_id, action, ApprovalLevel.CONFIRM)

    def push(
        self,
        approval_id: UUID,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        idempotency_key: str,
    ) -> str:
        repository, branch, commit = self._require_target(target, change_set)
        action = f"push {repository} {branch} {commit} diff={change_set.diff_hash}"
        approval = self.database.get_approval(approval_id)
        if approval.action != action:
            raise GitHubPublicationError("approval does not match the target commit or diff")
        return self.external.execute(
            approval_id,
            idempotency_key=idempotency_key,
            action=lambda: self.github.push("origin", branch),
        )

    def request_pull_request(
        self,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        title: str,
    ) -> Approval:
        repository, branch, commit = self._require_target(target, change_set)
        action = (
            f"pull_request {repository} {branch}->{target.default_branch} "
            f"{commit} diff={change_set.diff_hash} title={title}"
        )
        return self.external.request(change_set.mission_id, action, ApprovalLevel.CONFIRM)

    def create_pull_request(
        self,
        approval_id: UUID,
        target: ProjectTarget,
        change_set: ChangeSet,
        *,
        title: str,
        body: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        repository, branch, commit = self._require_target(target, change_set)
        action = (
            f"pull_request {repository} {branch}->{target.default_branch} "
            f"{commit} diff={change_set.diff_hash} title={title}"
        )
        approval = self.database.get_approval(approval_id)
        if approval.action != action:
            raise GitHubPublicationError("approval does not match the requested pull request")
        result = self.external.execute(
            approval_id,
            idempotency_key=idempotency_key,
            action=lambda: json.dumps(
                self.github.create_pull_request(
                    repository,
                    head=branch,
                    base=target.default_branch,
                    title=title,
                    body=body,
                ),
                sort_keys=True,
            ),
        )
        try:
            value = json.loads(result)
        except json.JSONDecodeError as exc:
            raise GitHubPublicationError("GitHub PR result was not JSON") from exc
        if not isinstance(value, dict):
            raise GitHubPublicationError("GitHub PR result was not an object")
        return value
