from hackathon_competitor.cli import doctor


def test_doctor_reports_required_runtime_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ID", "galahad")
    monkeypatch.setenv("PLOW_MCP_URL", "https://relay.invalid/mcp")
    checks, healthy = doctor(tmp_path)
    assert healthy
    assert checks["database"]["ok"]
    assert checks["skills"]["ok"]
    assert checks["agent_index_service"]["ok"]


def test_doctor_fails_closed_without_agent_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.setenv("PLOW_MCP_URL", "https://relay.invalid/mcp")
    checks, healthy = doctor(tmp_path)
    assert not healthy
    assert not checks["agent_id"]["ok"]
