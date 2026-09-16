import json

from hackathon_competitor.github import (
    GitHubCliAdapter,
    GitHubConnectionObserver,
    GitHubRuntimeObserver,
)
from hackathon_competitor.models import Mission
from hackathon_competitor.storage import Database


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
            return "https://github.com/owner/project/pull/3\n"
        if argv[0:2] == ["gh", "pr"] and argv[2] == "view":
            return json.dumps(
                {
                    "url": "https://github.com/owner/project/pull/3",
                    "number": 3,
                    "headRefName": "joust/mission",
                    "baseRefName": "main",
                }
            )
        if argv[0:2] == ["gh", "api"]:
            if "check-runs" in argv[-1]:
                return json.dumps(
                    {
                        "check_runs": [
                            {
                                "name": "tests",
                                "status": "completed",
                                "conclusion": "success",
                                "html_url": "https://github.com/owner/project/actions/runs/1",
                            }
                        ]
                    }
                )
            if argv[-1] == "user":
                return json.dumps({"login": "owner"})
            if argv[-1] == "repos/owner/project":
                return json.dumps(
                    {
                        "full_name": "owner/project",
                        "html_url": "https://github.com/owner/project",
                        "default_branch": "main",
                        "permissions": {"pull": True, "push": True, "admin": False},
                    }
                )
            if argv[-1] == "repos/owner/project/branches/main":
                return json.dumps({"name": "main", "protected": True})
            if "pulls?state=open" in argv[-1]:
                return json.dumps(
                    [
                        {
                            "number": 4,
                            "state": "open",
                            "head": {"ref": "joust/mission"},
                            "base": {"ref": "main"},
                            "html_url": "https://github.com/owner/project/pull/4",
                        }
                    ]
                )
            if "actions/runs" in argv[-1]:
                return json.dumps(
                    {
                        "workflow_runs": [
                            {
                                "id": 7,
                                "name": "CI",
                                "status": "completed",
                                "conclusion": "success",
                                "head_sha": "abc123",
                                "html_url": "https://github.com/owner/project/actions/runs/7",
                            }
                        ]
                    }
                )
            return json.dumps({"ref": "refs/heads/joust/mission"})
        if argv[0:2] == ["git", "push"]:
            return "pushed"
        raise AssertionError(argv)


class ExistingRepositoryShell(FakeShell):
    def run(self, argv, *, timeout_seconds):
        self.calls.append((argv, timeout_seconds))
        if argv[0:3] == ["gh", "repo", "create"]:
            raise RuntimeError("repository already exists")
        if argv[0:3] == ["gh", "repo", "view"]:
            return json.dumps(
                {
                    "nameWithOwner": "owner/project",
                    "defaultBranchRef": {"name": ""},
                    "url": "https://github.com/owner/project",
                    "visibility": "PUBLIC",
                }
            )
        return super().run(argv, timeout_seconds=timeout_seconds)


def test_github_adapter_keeps_repository_and_publish_operations_structured(tmp_path):
    target_root = (tmp_path / "target-checkout").resolve()
    adapter = GitHubCliAdapter(str(target_root))
    assert adapter.shell.root == target_root
    shell = FakeShell()
    adapter.shell = shell

    assert adapter.repository("owner/project")["nameWithOwner"] == "owner/project"
    assert adapter.clone("owner/project", "target") == "cloned"
    assert adapter.create_branch("owner/project", "joust/mission", "abc123").endswith(
        "joust/mission"
    )
    assert adapter.push("origin", "joust/mission") == "pushed"
    push_call = next(argv for argv, _ in shell.calls if argv[0:2] == ["git", "push"])
    assert push_call[-1] == "HEAD:refs/heads/joust/mission"
    pull_request = adapter.create_pull_request(
        "owner/project",
        head="joust/mission",
        base="main",
        title="Build slice",
        body="Validated by Joust",
    )
    assert pull_request["number"] == 3
    assert adapter.checks("owner/project", "abc123") == [
        {
            "name": "tests",
            "state": "success",
            "link": "https://github.com/owner/project/actions/runs/1",
        }
    ]
    checks_call = next(argv for argv, _ in shell.calls if "check-runs" in argv[-1])
    assert checks_call[0:4] == ["gh", "api", "-H", "Accept: application/vnd.github+json"]
    assert all(isinstance(argv, list) for argv, _ in shell.calls)
    assert all(timeout > 0 for _, timeout in shell.calls)


def test_github_runtime_preflight_is_read_only_structured_and_evidenced(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="GitHub", objective="observe", workspace_path=str(tmp_path))
    database.save_mission(mission)
    adapter = GitHubCliAdapter(str(tmp_path))
    shell = FakeShell()
    adapter.shell = shell

    snapshot = GitHubRuntimeObserver(database, adapter).observe(
        mission.id, "owner/project", "abc123"
    )

    assert snapshot.authenticated_account == "owner"
    assert snapshot.canonical_repository == "owner/project"
    assert snapshot.repo_accessible
    assert snapshot.push_permission
    assert snapshot.branch_protected
    assert snapshot.open_pull_requests[0]["number"] == 4
    assert snapshot.checks[0]["state"] == "success"
    assert snapshot.action_runs[0]["head_sha"] == "abc123"
    assert any(item.source_type == "github_runtime" for item in database.list_evidence(mission.id))
    assert all("create" not in argv for argv, _ in shell.calls)
    assert all(argv[0:2] != ["git", "push"] for argv, _ in shell.calls)


def test_connection_status_reports_login_and_repository_permission_without_tokens(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="GitHub", objective="observe", workspace_path=str(tmp_path))
    database.save_mission(mission)
    adapter = GitHubCliAdapter(str(tmp_path))
    shell = FakeShell()
    adapter.shell = shell

    status = adapter.connection_status("https://github.com/owner/project.git")
    assert status.connected is True
    assert status.login == "owner"
    assert status.can_push_to_target is True
    assert status.repository == "owner/project"
    assert "token" not in status.model_dump()
    assert [argv for argv, _ in shell.calls] == [
        ["gh", "api", "user"],
        ["gh", "api", "repos/owner/project"],
    ]

    observed = GitHubConnectionObserver(database, adapter).observe(
        mission.id, "owner/project"
    )
    assert observed.login == "owner"
    assert any(item.source_type == "github_connection" for item in database.list_evidence(mission.id))
    event_types = [item["event_type"] for item in database.events(mission.id)]
    assert event_types.count("GITHUB_CONNECTION_OBSERVED") == 1


def test_connection_status_is_disconnected_when_gh_session_is_unavailable(tmp_path):
    class DisconnectedShell:
        def run(self, argv, *, timeout_seconds):
            raise RuntimeError("not logged in; token=must-not-leak")

    adapter = GitHubCliAdapter(str(tmp_path))
    adapter.shell = DisconnectedShell()

    status = adapter.connection_status()

    assert status.connected is False
    assert status.login is None


def test_installation_home_pins_gh_config_and_prevents_global_identity_leak(tmp_path):
    creator_config = tmp_path / "creator-config"
    installation_a = tmp_path / "installation-a"
    installation_b = tmp_path / "installation-b"
    adapter_a = GitHubCliAdapter(
        str(tmp_path / "project-a"),
        installation_home=installation_a,
        environment={"GH_CONFIG_DIR": str(creator_config)},
    )
    adapter_b = GitHubCliAdapter(
        str(tmp_path / "project-b"), installation_home=installation_b
    )

    assert adapter_a.shell.environment["GH_CONFIG_DIR"] == str(installation_a / ".config" / "gh")
    assert adapter_b.shell.environment["GH_CONFIG_DIR"] == str(installation_b / ".config" / "gh")
    assert adapter_a.shell.environment["GH_CONFIG_DIR"] != adapter_b.shell.environment["GH_CONFIG_DIR"]


def test_repository_creation_recovers_when_the_exact_repository_already_exists(tmp_path):
    adapter = GitHubCliAdapter(str(tmp_path))
    adapter.shell = ExistingRepositoryShell()

    result = adapter.create_repository("owner/project", visibility="public")

    assert result["nameWithOwner"] == "owner/project"
