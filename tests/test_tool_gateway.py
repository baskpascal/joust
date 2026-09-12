import sys

import pytest

from hackathon_competitor.tool_gateway import LocalShellTool, WorkspaceFileTool


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
