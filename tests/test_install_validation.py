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


def test_compose_build_phrasing_is_also_accepted(tmp_path):
    """The real repository README builds the image through Compose
    (`docker compose up --build -d`), not a bare `docker build` — a stale
    `docker build`-only marker check silently broke against the real README
    after an earlier rewrite, undetected because every test used a synthetic
    fixture. Either phrasing is a real answer to "how is the image built"."""

    readme = tmp_path / "README.md"
    readme.write_text(
        "Run `docker compose up --build -d` with `plow-credentials`, `AGENT_ID`, "
        "and Docker Compose.",
        encoding="utf-8",
    )
    assert validate_install_run_documentation(readme, ROOT).startswith("exit_code=0")


def test_the_real_repository_readme_passes_its_own_install_validation(tmp_path):
    """The actual regression: run this against the real README, not a
    fixture. This must never go stale again without a test noticing."""

    assert validate_install_run_documentation(ROOT / "README.md", ROOT).startswith("exit_code=0")
