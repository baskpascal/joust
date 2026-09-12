from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def validate_install_run_documentation(readme: Path, distribution_root: Path) -> str:
    text = readme.read_text(encoding="utf-8")
    required_markers = ("docker build", "plow-credentials", "AGENT_ID", "Docker Compose")
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise ValueError(f"install/run documentation is missing: {missing}")
    required_files = (distribution_root / "Dockerfile", distribution_root / "compose.yml")
    absent = [str(path) for path in required_files if not path.is_file()]
    if absent:
        raise FileNotFoundError(f"documented distribution files are missing: {absent}")
    result = subprocess.run(
        [sys.executable, "-m", "hackathon_competitor.cli", "--help"],
        cwd=distribution_root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0 or "mission" not in result.stdout or "doctor" not in result.stdout:
        raise RuntimeError(f"documented CLI is not runnable: {result.stderr.strip()}")
    return "exit_code=0\nCLI help and documented distribution files validated.\n"
