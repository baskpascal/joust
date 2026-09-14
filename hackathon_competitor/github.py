from __future__ import annotations

import json
from uuid import UUID
from typing import Any, Protocol

from .models import Evidence, GitHubRuntimeSnapshot
from .storage import Database
from .tool_gateway import LocalShellTool


class GitHubError(RuntimeError):
    pass


class GitHubTool(Protocol):
    def repository(self, repository: str) -> dict[str, Any]: ...
    def create_repository(self, repository: str, *, visibility: str) -> dict[str, Any]: ...
    def clone(self, repository: str, destination: str) -> str: ...
    def create_branch(self, repository: str, branch: str, base: str) -> str: ...
    def push(self, remote: str, branch: str) -> str: ...
    def create_pull_request(
        self, repository: str, *, head: str, base: str, title: str, body: str
    ) -> dict[str, Any]: ...
    def checks(self, repository: str, ref: str) -> list[dict[str, Any]]: ...
    def branch_sha(self, repository: str, branch: str) -> str: ...
    def pull_request(self, repository: str, number: int) -> dict[str, Any]: ...
    def runtime_snapshot(self, repository: str, ref: str) -> GitHubRuntimeSnapshot: ...


class GitHubCliAdapter:
    """GitHub boundary using the user's authenticated `gh` CLI session."""

    def __init__(self, repository_root: str):
        self.shell = LocalShellTool(repository_root)

    def _gh_json(self, argv: list[str]) -> dict[str, Any] | list[dict[str, Any]]:
        output = self.shell.run(["gh", *argv], timeout_seconds=60)
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise GitHubError("gh returned invalid JSON") from exc
        if not isinstance(value, (dict, list)):
            raise GitHubError("gh returned an unsupported JSON shape")
        return value

    def repository(self, repository: str) -> dict[str, Any]:
        value = self._gh_json(
            [
                "repo",
                "view",
                repository,
                "--json",
                "nameWithOwner,defaultBranchRef,url,visibility",
            ]
        )
        if not isinstance(value, dict):
            raise GitHubError("repository lookup returned a non-object")
        return value

    def create_repository(self, repository: str, *, visibility: str) -> dict[str, Any]:
        if visibility not in {"public", "private", "internal"}:
            raise ValueError("repository visibility must be public, private, or internal")
        if not repository.strip() or repository.startswith("-"):
            raise ValueError("invalid GitHub repository")
        try:
            self.shell.run(
                [
                    "gh",
                    "repo",
                    "create",
                    repository,
                    f"--{visibility}",
                    "--description",
                    "Joust competition entry and verified remote-action rehearsal",
                ],
                timeout_seconds=120,
            )
        except RuntimeError as create_error:
            # A process can stop after GitHub accepts creation but before Joust
            # persists the executor result. Suppress the original error only
            # when a fresh read proves that the exact target now exists.
            try:
                existing = self.repository(repository)
            except Exception:  # noqa: BLE001 - retain the original mutation error
                raise create_error
            if str(existing.get("nameWithOwner", "")).casefold() != repository.casefold():
                raise create_error
            return existing
        return self.repository(repository)

    def clone(self, repository: str, destination: str) -> str:
        if not repository.strip() or not destination.strip():
            raise ValueError("repository and destination are required for clone")
        return self.shell.run(
            ["gh", "repo", "clone", repository, destination], timeout_seconds=120
        ).strip()

    def create_branch(self, repository: str, branch: str, base: str) -> str:
        if not branch or branch.startswith("-"):
            raise ValueError("invalid GitHub branch")
        result = self._gh_json(
            [
                "api",
                f"repos/{repository}/git/refs",
                "-f",
                f"ref=refs/heads/{branch}",
                "-f",
                f"sha={base}",
            ]
        )
        if not isinstance(result, dict) or not isinstance(result.get("ref"), str):
            raise GitHubError("GitHub did not return the created ref")
        return str(result["ref"])

    def push(self, remote: str, branch: str) -> str:
        if not branch or branch.startswith("-"):
            raise ValueError("invalid push branch")
        return self.shell.run(
            ["git", "push", remote, f"HEAD:refs/heads/{branch}"], timeout_seconds=120
        ).strip()

    def create_pull_request(
        self, repository: str, *, head: str, base: str, title: str, body: str
    ) -> dict[str, Any]:
        output = self.shell.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repository,
                "--head",
                head,
                "--base",
                base,
                "--title",
                title,
                "--body",
                body,
            ],
            timeout_seconds=120,
        ).strip()
        urls = [line.strip() for line in output.splitlines() if line.strip().startswith("https://")]
        if not urls:
            raise GitHubError("GitHub did not return a pull request URL")
        value = self._gh_json(
            [
                "pr",
                "view",
                urls[-1],
                "--repo",
                repository,
                "--json",
                "url,number,headRefName,baseRefName",
            ]
        )
        if not isinstance(value, dict) or not value.get("url"):
            raise GitHubError("GitHub did not return a pull request")
        return value

    def checks(self, repository: str, ref: str) -> list[dict[str, Any]]:
        value = self._gh_json(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repository}/commits/{ref}/check-runs?per_page=100",
            ]
        )
        if not isinstance(value, dict) or not isinstance(value.get("check_runs"), list):
            raise GitHubError("GitHub checks returned an unsupported response")
        checks: list[dict[str, Any]] = []
        for check in value["check_runs"]:
            if not isinstance(check, dict):
                continue
            checks.append(
                {
                    "name": check.get("name"),
                    "state": check.get("conclusion") or check.get("status"),
                    "link": check.get("html_url"),
                }
            )
        return checks

    def branch_sha(self, repository: str, branch: str) -> str:
        if not branch or branch.startswith("-"):
            raise ValueError("invalid GitHub branch")
        value = self._gh_json(["api", f"repos/{repository}/git/ref/heads/{branch}"])
        if not isinstance(value, dict):
            raise GitHubError("GitHub branch ref returned a non-object")
        target = value.get("object")
        if not isinstance(target, dict) or not isinstance(target.get("sha"), str):
            raise GitHubError("GitHub branch ref omitted its commit SHA")
        return target["sha"]

    def pull_request(self, repository: str, number: int) -> dict[str, Any]:
        value = self._gh_json(["api", f"repos/{repository}/pulls/{number}"])
        if not isinstance(value, dict):
            raise GitHubError("GitHub pull request returned a non-object")
        return {
            "number": value.get("number"),
            "state": value.get("state"),
            "head": (value.get("head") or {}).get("ref"),
            "base": (value.get("base") or {}).get("ref"),
            "url": value.get("html_url"),
        }

    def runtime_snapshot(self, repository: str, ref: str) -> GitHubRuntimeSnapshot:
        user = self._gh_json(["api", "user"])
        repo = self._gh_json(["api", f"repos/{repository}"])
        if not isinstance(user, dict) or not isinstance(user.get("login"), str):
            raise GitHubError("GitHub authentication did not return an account")
        if not isinstance(repo, dict):
            raise GitHubError("GitHub repository lookup returned a non-object")
        permissions = repo.get("permissions")
        default_branch = repo.get("default_branch")
        canonical_repository = repo.get("full_name")
        repository_url = repo.get("html_url")
        if (
            not isinstance(permissions, dict)
            or not isinstance(default_branch, str)
            or not isinstance(canonical_repository, str)
            or not isinstance(repository_url, str)
        ):
            raise GitHubError("GitHub repository response omitted permissions or default branch")
        branch = self._gh_json(["api", f"repos/{repository}/branches/{default_branch}"])
        pulls = self._gh_json(["api", f"repos/{repository}/pulls?state=open&per_page=100"])
        runs = self._gh_json(["api", f"repos/{repository}/actions/runs?per_page=20"])
        if not isinstance(branch, dict):
            raise GitHubError("GitHub branch response was not an object")
        if not isinstance(pulls, list):
            raise GitHubError("GitHub pull request response was not a list")
        if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
            raise GitHubError("GitHub Actions response omitted workflow runs")
        return GitHubRuntimeSnapshot(
            repository=repository,
            canonical_repository=canonical_repository,
            repository_url=repository_url,
            ref=ref,
            authenticated_account=user["login"],
            repo_accessible=True,
            push_permission=permissions.get("push") is True,
            default_branch=default_branch,
            branch_protected=branch.get("protected") is True,
            open_pull_requests=[
                {
                    "number": item.get("number"),
                    "state": item.get("state"),
                    "head": (item.get("head") or {}).get("ref"),
                    "base": (item.get("base") or {}).get("ref"),
                    "url": item.get("html_url"),
                }
                for item in pulls
                if isinstance(item, dict)
            ],
            checks=self.checks(repository, ref),
            action_runs=[
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "head_sha": item.get("head_sha"),
                    "url": item.get("html_url"),
                }
                for item in runs["workflow_runs"]
                if isinstance(item, dict)
            ],
        )


class GitHubRuntimeObserver:
    def __init__(self, database: Database, github: GitHubTool):
        self.database = database
        self.github = github

    def observe(self, mission_id: UUID, repository: str, ref: str) -> GitHubRuntimeSnapshot:
        snapshot = self.github.runtime_snapshot(repository, ref)
        evidence = Evidence(
            mission_id=mission_id,
            claim=f"Authenticated GitHub runtime observed {repository}@{ref}",
            source_type="github_runtime",
            source_uri=f"{snapshot.repository_url}/commit/{ref}",
            excerpt=snapshot.model_dump_json(),
            confidence=1.0,
            authority="github-api",
            retrieved_at=snapshot.observed_at,
        )
        self.database.save_evidence(evidence)
        self.database.append_event(
            mission_id,
            "GITHUB_RUNTIME_OBSERVED",
            {
                "evidence_id": str(evidence.id),
                "repository": repository,
                "canonical_repository": snapshot.canonical_repository,
                "ref": ref,
                "authenticated_account": snapshot.authenticated_account,
                "push_permission": snapshot.push_permission,
                "branch_protected": snapshot.branch_protected,
                "checks": len(snapshot.checks),
                "action_runs": len(snapshot.action_runs),
            },
        )
        return snapshot
