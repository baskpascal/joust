from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

from ..models import Decision, Mission
from ..tool_gateway import WorkspaceFileTool


DEMO_SOURCE = """from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: demo.py <mission-status.json>", file=sys.stderr)
        return 2
    status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(f"Mission: {status['title']}")
    print(f"State: {status['state']}")
    print(f"Evidence: {status['evidence_count']}")
    print(f"Selected strategy: {status['selected_strategy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_demo_project(
    root: Path, mission: Mission, decision: Decision, evidence_count: int
) -> Path:
    tool = WorkspaceFileTool(root)
    tool.write_text("demo.py", DEMO_SOURCE)
    tool.write_text(
        "mission-status.json",
        json.dumps(
            {
                "title": mission.title,
                "state": mission.state.value,
                "evidence_count": evidence_count,
                "selected_strategy": decision.selected_option,
            },
            indent=2,
        ),
    )
    tool.write_text(
        "README.md",
        "# Galahad mission demo\n\nRun `python demo.py mission-status.json`.\n",
    )
    return root / "demo.py"


def validate_demo_project(demo_path: Path) -> str:
    py_compile.compile(str(demo_path), doraise=True)
    result = subprocess.run(
        [sys.executable, str(demo_path), str(demo_path.parent / "mission-status.json")],
        cwd=demo_path.parent,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"demo failed with {result.returncode}: {result.stderr.strip()}")
    required = ("Mission:", "State:", "Evidence:", "Selected strategy:")
    if not all(marker in result.stdout for marker in required):
        raise RuntimeError("demo output is missing required status fields")
    return f"exit_code=0\n{result.stdout.strip()}\n"
