from __future__ import annotations

import json
from typing import Any, Protocol

from .tool_gateway import LocalShellTool


class GitHubError(RuntimeError):
    pass


class GitHubTool(Protocol):
    def repository(self, repository: str) -> dict[str, Any]: ...
    def clone(self, repository: str, destination: str) -> str: ...
    def create_branch(self, repository: str, branch: str, base: str) -> str: ...
    def push(self, remote: str, branch: str) -> str: ...
    def create_pull_request(
        self, repository: str, *, head: str, base: str, title: str, body: str
    ) -> dict[str, Any]: ...
    def checks(self, repository: str, ref: str) -> list[dict[str, Any]]: ...


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
            ["repo", "view", repository, "--json", "nameWithOwner,defaultBranchRef,url"]
        )
        if not isinstance(value, dict):
            raise GitHubError("repository lookup returned a non-object")
        return value

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
            ["git", "push", remote, f"HEAD:{branch}"], timeout_seconds=120
        ).strip()

    def create_pull_request(
        self, repository: str, *, head: str, base: str, title: str, body: str
    ) -> dict[str, Any]:
        value = self._gh_json(
            [
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
