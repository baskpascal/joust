"""The check an installer runs before anything is built.

Three people attempted to install Joust through the Agent Index and none of
them got it running.  These cases fix the advice each failure gives, because
wrong advice costs an installer more than no advice.
"""

import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preflight.py"
_spec = importlib.util.spec_from_file_location("joust_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(_spec)
# dataclasses resolves annotations through sys.modules, so a module loaded
# straight from a path has to be registered before it is executed.
sys.modules[_spec.name] = preflight
_spec.loader.exec_module(preflight)


def test_the_script_runs_without_the_project_installed():
    """It has to work from a bare clone, before any dependency exists."""

    assert "hackathon_competitor" not in SCRIPT.read_text(encoding="utf-8")


def test_a_missing_credential_explains_how_to_mint_one(tmp_path):
    check = preflight.check_credential(tmp_path, {})
    assert not check.ok
    assert "plow-agents mint" in check.remedy


def test_a_protected_credential_passes(tmp_path):
    token = tmp_path / "plow-credentials"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o600)
    if stat.S_IMODE(token.stat().st_mode) != 0o600:
        pytest.skip("this filesystem cannot hold POSIX modes")
    assert preflight.check_credential(tmp_path, {}).ok


def test_a_readable_credential_on_a_normal_filesystem_asks_for_chmod(tmp_path, monkeypatch):
    token = tmp_path / "plow-credentials"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o644)
    monkeypatch.setattr(preflight, "_holds_posix_modes", lambda directory: True)
    check = preflight.check_credential(tmp_path, {})
    assert not check.ok
    assert check.remedy.startswith("chmod 600")


def test_a_filesystem_that_cannot_protect_the_token_says_where_to_move_it(tmp_path, monkeypatch):
    """The trap that caught the author: a checkout on a Windows drive."""

    token = tmp_path / "plow-credentials"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o644)
    monkeypatch.setattr(preflight, "_holds_posix_modes", lambda directory: False)
    check = preflight.check_credential(tmp_path, {})
    assert not check.ok
    assert "PLOW_CREDENTIALS_PATH" in check.remedy
    assert check.facts["filesystem_holds_posix_modes"] is False


def test_the_configured_credential_path_is_the_one_inspected(tmp_path):
    elsewhere = tmp_path / "home" / "credentials"
    elsewhere.parent.mkdir()
    elsewhere.write_text("token", encoding="utf-8")
    elsewhere.chmod(0o600)
    if stat.S_IMODE(elsewhere.stat().st_mode) != 0o600:
        pytest.skip("this filesystem cannot hold POSIX modes")
    check = preflight.check_credential(tmp_path, {"PLOW_CREDENTIALS_PATH": str(elsewhere)})
    assert check.ok
    assert str(elsewhere) in check.detail


def test_agent_id_must_be_set_and_is_described_as_permanent():
    assert not preflight.check_agent_id({}).ok
    assert "must not change" in preflight.check_agent_id({}).remedy
    assert preflight.check_agent_id({"AGENT_ID": "joust-live"}).ok


def test_a_docker_that_will_not_answer_points_at_wsl_integration(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda command, timeout=20.0: (1, "The command 'docker' could not be found\nin this distro"),
    )
    check = preflight.check_docker()
    assert not check.ok
    assert "WSL integration" in check.remedy
    assert "Reinstall" not in check.remedy
    assert "\n" not in check.detail


def test_an_absent_docker_is_reported_as_absent(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    check = preflight.check_docker()
    assert not check.ok
    assert "not on PATH" in check.detail


def test_low_disk_warns_without_blocking(tmp_path, monkeypatch):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: os.terminal_size((0, 0)) and _Usage()
    )
    check = preflight.check_disk(tmp_path)
    assert not check.ok
    assert check.blocking is False


class _Usage:
    total = 10 * 1024**3
    used = 9 * 1024**3
    free = 1 * 1024**3


def test_render_states_the_verdict_and_the_next_command():
    ready = [preflight.Check("git", ok=True, detail="/usr/bin/git")]
    assert "Ready." in preflight.render(ready)
    assert "docker compose up --build -d" in preflight.render(ready)

    blocked = ready + [preflight.Check("docker daemon", ok=False, detail="no response")]
    assert "Not ready: docker daemon" in preflight.render(blocked)


def test_main_exits_non_zero_when_a_blocking_check_fails(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.delenv("PLOW_CREDENTIALS_PATH", raising=False)
    assert preflight.main(["--root", str(tmp_path), "--json"]) == 1
    payload = capsys.readouterr().out
    assert '"ready": false' in payload
