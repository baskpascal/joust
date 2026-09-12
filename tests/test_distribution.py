import subprocess
import zipfile
from pathlib import Path

import pytest

from hackathon_competitor.distribution import build_public_bundle, validate_public_bundle


def _commit_distribution_fixture(root: Path) -> None:
    files = {
        ".gitattributes": ".knightwatch export-ignore\n",
        ".knightwatch/siblings": "private review metadata\n",
        "Dockerfile": "FROM scratch\n",
        "LICENSE": "MIT License\n",
        "README.md": "Docker Compose docker build plow-credentials AGENT_ID\n",
        "compose.yml": "services: {}\n",
        "pyproject.toml": "[project]\nname='fixture'\nversion='0.0.0'\n",
        "vendor/client.pin": "sha=0123456789abcdef\npath=client.py\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Galahad Test",
            "-c",
            "user.email=galahad@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )


def test_public_bundle_uses_committed_tree_and_export_ignores_internal_metadata(tmp_path):
    _commit_distribution_fixture(tmp_path)
    (tmp_path / "plow-credentials").write_text("secret", encoding="utf-8")

    summary = build_public_bundle(tmp_path, tmp_path / "dist/galahad.zip")

    assert summary["files"] == 7
    assert len(summary["sha256"]) == 64
    with zipfile.ZipFile(summary["path"]) as archive:
        assert "galahad/plow-credentials" not in archive.namelist()
        assert "galahad/.knightwatch/siblings" not in archive.namelist()


def test_public_bundle_rejects_secret_bearing_path(tmp_path):
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        for name in (
            "Dockerfile",
            "LICENSE",
            "README.md",
            "compose.yml",
            "pyproject.toml",
            "vendor/client.pin",
        ):
            content = "MIT License\n" if name == "LICENSE" else "Docker Compose docker build plow-credentials AGENT_ID\n"
            archive.writestr(f"galahad/{name}", content)
        archive.writestr("galahad/plow-credentials", "secret")

    with pytest.raises(ValueError, match="forbidden paths"):
        validate_public_bundle(bundle)
