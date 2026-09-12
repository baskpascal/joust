from pathlib import Path

import pytest

from hackathon_competitor.install_validation import validate_install_run_documentation


ROOT = Path(__file__).resolve().parents[1]


def test_repository_install_run_documentation_is_executable(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "Run `docker build .` with `plow-credentials`, `AGENT_ID`, and Docker Compose.",
        encoding="utf-8",
    )
    assert validate_install_run_documentation(readme, ROOT).startswith("exit_code=0")


def test_install_validation_rejects_incomplete_instructions(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Just run it.", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        validate_install_run_documentation(readme, ROOT)
