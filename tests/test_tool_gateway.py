import os
import sys

import pytest

from hackathon_competitor.tool_gateway import (
    CodingAgentCommandTool,
    LocalShellTool,
    PlowLatchAdapter,
    WorkspaceFileTool,
)


def test_workspace_file_tool_confines_reads_and_writes(tmp_path):
    tool = WorkspaceFileTool(tmp_path / "workspace")
    tool.write_text("notes/result.md", "safe")
    assert tool.read_text("notes/result.md") == "safe"
    with pytest.raises(PermissionError, match="escapes"):
        tool.write_text("../outside.txt", "unsafe")


def test_local_shell_uses_argument_vector_without_shell_expansion(tmp_path):
    tool = LocalShellTool(tmp_path)
    output = tool.run(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "$(unsafe)"],
        timeout_seconds=5,
    )
    assert output.strip() == "$(unsafe)"


def test_local_shell_can_run_with_a_filtered_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PLOW_AGENT_TOKEN", "must-not-leak")
    tool = LocalShellTool(
        tmp_path,
        environment={"PATH": os.environ["PATH"], "JOUST_SAFE": "yes"},
    )
    output = tool.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.getenv('PLOW_AGENT_TOKEN', 'absent')); print(os.getenv('JOUST_SAFE'))",
        ],
        timeout_seconds=5,
    )
    assert output.splitlines() == ["absent", "yes"]


def test_local_shell_surfaces_nonzero_exit(tmp_path):
    tool = LocalShellTool(tmp_path)
    with pytest.raises(RuntimeError, match="status 7"):
        tool.run([sys.executable, "-c", "raise SystemExit(7)"], timeout_seconds=5)


def test_local_shell_enforces_timeout(tmp_path):
    tool = LocalShellTool(tmp_path)
    with pytest.raises(TimeoutError):
        tool.run(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            timeout_seconds=0.01,
        )


def test_coding_agent_handoff_uses_a_file_and_argument_vector(tmp_path):
    tool = CodingAgentCommandTool(
        tmp_path,
        [
            sys.executable,
            "-c",
            "import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text())",
        ],
    )
    assert tool.implement("Implement the acceptance check.").strip() == (
        "Implement the acceptance check."
    )


class FakePlowBackend:
    def __init__(self):
        self.calls = []

    def invoke(self, tool, payload, *, timeout_seconds):
        self.calls.append((tool, payload, timeout_seconds))
        return {"content": f"{tool}:ok"}


def test_vendor_adapter_keeps_calls_structured():
    backend = FakePlowBackend()
    adapter = PlowLatchAdapter(backend)
    assert adapter.open("https://example.test") == "browser.open:ok"
    assert adapter.run(["printf", "safe"], timeout_seconds=5) == "shell.run:ok"
    adapter.write_text("result.md", "safe")
    assert backend.calls[1] == ("shell.run", {"argv": ["printf", "safe"]}, 5)
    assert backend.calls[2][0] == "file.write"
    assert adapter.policies["browser.open"].retryable is True
