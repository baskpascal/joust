import json

from hackathon_competitor.github import GitHubCliAdapter


class FakeShell:
    def __init__(self):
        self.calls = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((argv, timeout_seconds))
        if argv[0:3] == ["gh", "repo", "view"]:
            return json.dumps(
                {
                    "nameWithOwner": "owner/project",
                    "defaultBranchRef": {"name": "main"},
                    "url": "https://github.com/owner/project",
                }
            )
        if argv[0:3] == ["gh", "repo", "clone"]:
            return "cloned"
        if argv[0:2] == ["gh", "pr"] and argv[2] == "create":
            return json.dumps(
                {
                    "url": "https://github.com/owner/project/pull/3",
                    "number": 3,
                    "headRefName": "galahad/mission",
                    "baseRefName": "main",
                }
            )
        if argv[0:2] == ["gh", "api"]:
            return json.dumps({"ref": "refs/heads/galahad/mission"})
        if argv[0:3] == ["gh", "pr", "checks"]:
            return "[]"
        if argv[0:2] == ["git", "push"]:
            return "pushed"
        raise AssertionError(argv)


def test_github_adapter_keeps_repository_and_publish_operations_structured(tmp_path):
    target_root = (tmp_path / "target-checkout").resolve()
    adapter = GitHubCliAdapter(str(target_root))
    assert adapter.shell.root == target_root
    shell = FakeShell()
    adapter.shell = shell

    assert adapter.repository("owner/project")["nameWithOwner"] == "owner/project"
    assert adapter.clone("owner/project", "target") == "cloned"
    assert adapter.create_branch("owner/project", "galahad/mission", "abc123").endswith(
        "galahad/mission"
    )
    assert adapter.push("origin", "galahad/mission") == "pushed"
    pull_request = adapter.create_pull_request(
        "owner/project",
        head="galahad/mission",
        base="main",
        title="Build slice",
        body="Validated by Galahad",
    )
    assert pull_request["number"] == 3
    assert adapter.checks("owner/project", "3") == []
    assert all(isinstance(argv, list) for argv, _ in shell.calls)
    assert all(timeout > 0 for _, timeout in shell.calls)
