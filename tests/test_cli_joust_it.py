"""`joust-it` on the command line must expose every knob `joust_it()` takes.

Gap 2's orchestration (existing_project_path) was only reachable by calling
`ai_mission.joust_it` directly. An operator running `joust mission joust-it`
from the real container had no way to say "evolve this repository" at all,
which is the exact surface Test 15's protocol runs through.
"""

from uuid import uuid4

from hackathon_competitor import cli
from hackathon_competitor.models import MissionState


class _Decision:
    options: tuple[object, ...] = ()
    rationale = "r"


class _Selected:
    product_thesis = "t"
    target_user = "u"
    winning_mechanism = "w"


class _Mission:
    id = uuid4()
    title = "Test Cup"
    deadline_at = None
    state = MissionState.BUILDING


class _Target:
    id = uuid4()
    local_path = "/some/path"


def _install_fake_joust_it(monkeypatch, captured):
    def _fake_joust_it(app, url, reasoner, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return _Mission(), _Selected(), _Decision(), _Target()

    monkeypatch.setattr(cli, "joust_it", _fake_joust_it)
    monkeypatch.setattr(cli, "runtime", lambda home: object())


def test_existing_project_path_reaches_joust_it(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    _install_fake_joust_it(monkeypatch, captured)

    existing = tmp_path / "existing-project"
    existing.mkdir()

    exit_code = cli.main(
        [
            "mission",
            "joust-it",
            "--url",
            "https://example.test/rules",
            "--no-model",
            "--existing-project-path",
            str(existing),
        ]
    )

    assert exit_code == 0
    assert captured["existing_project_path"] == str(existing)


def test_existing_project_path_defaults_to_none(monkeypatch):
    captured: dict[str, object] = {}
    _install_fake_joust_it(monkeypatch, captured)

    cli.main(["mission", "joust-it", "--url", "https://example.test/rules", "--no-model"])

    assert captured["existing_project_path"] is None


def test_cli_create_defaults_to_tenant_workspace(monkeypatch):
    parsed = cli.build_parser().parse_args(
        ["mission", "create", "--url", "https://example.test/rules"]
    )

    assert parsed.workspace is None


def test_installation_home_is_unique_for_explicit_tenant_homes(tmp_path):
    first = cli.installation_home(tmp_path / "tenant-a")
    second = cli.installation_home(tmp_path / "tenant-b")

    assert first == (tmp_path / "tenant-a").resolve()
    assert second == (tmp_path / "tenant-b").resolve()
    assert first != second
