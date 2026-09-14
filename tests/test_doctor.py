from pathlib import Path

from hackathon_competitor.cli import _runtime_marker_present, credential_check, doctor


def test_doctor_reports_required_runtime_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ID", "joust")
    monkeypatch.setenv("PLOW_MCP_URL", "https://relay.invalid/mcp")
    checks, _healthy = doctor(tmp_path)
    # Every check this process actually controls. Overall health additionally
    # depends on the host's credential file, which is deliberately covered by
    # its own test rather than asserted through whatever the machine happens
    # to have on disk.
    for name in (
        "state_directory",
        "workspace",
        "database",
        "git",
        "skills",
        "plow_tools",
        "agent_id",
        "agent_index_service",
    ):
        assert checks[name]["ok"], (name, checks[name])


def test_absent_credentials_are_healthy_and_loose_modes_are_not(tmp_path):
    missing = tmp_path / "plow-credentials"
    assert credential_check([missing]) == {"ok": True, "present": False}

    missing.write_text("token")
    missing.chmod(0o600)
    assert credential_check([missing])["ok"]

    missing.chmod(0o644)
    check = credential_check([missing])
    assert not check["ok"]
    assert check["mode"] == "0o644"


def test_doctor_fails_closed_without_agent_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.setenv("PLOW_MCP_URL", "https://relay.invalid/mcp")
    checks, healthy = doctor(tmp_path)
    assert not healthy
    assert not checks["agent_id"]["ok"]


def test_runtime_marker_requires_a_nonempty_regular_file(tmp_path):
    marker = tmp_path / "PLOW_MCP_URL"
    assert not _runtime_marker_present(marker)
    marker.write_text("")
    assert not _runtime_marker_present(marker)
    marker.write_text("configured")
    assert _runtime_marker_present(marker)
    assert not _runtime_marker_present(Path(tmp_path))
