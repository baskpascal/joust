from pathlib import Path

from hackathon_competitor.cli import _runtime_marker_present, doctor


def test_doctor_reports_required_runtime_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ID", "galahad")
    monkeypatch.setenv("PLOW_MCP_URL", "https://relay.invalid/mcp")
    checks, healthy = doctor(tmp_path)
    assert healthy
    assert checks["database"]["ok"]
    assert checks["workspace"]["ok"]
    assert checks["skills"]["ok"]
    assert checks["agent_index_service"]["ok"]


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
