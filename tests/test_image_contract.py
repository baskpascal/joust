import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_variant_uses_immutable_official_base_and_does_not_vendor_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert re.search(
        r"^FROM public\.ecr\.aws/.+:base-[0-9a-f]{40}@sha256:[0-9a-f]{64}$",
        dockerfile,
        re.MULTILINE,
    )
    assert not (ROOT / "image/s6-overlay/scripts/plow-init.py").exists()
    assert not (ROOT / "image/seed/SOUL.md").exists()
    assert (ROOT / "runtime/persona.md").is_file()
    assert "HERMES_HOME_MODE=3770" in dockerfile
    assert "find /opt/galahad -type d -exec chmod 0755" in dockerfile


def test_variant_persona_owns_the_public_agent_identity():
    persona = (ROOT / "runtime/persona.md").read_text()
    assert "Your public name is Galahad" in persona
    assert "Never introduce yourself by that label" in persona


def test_agent_index_client_and_supervision_are_pinned_and_wired():
    pin = (ROOT / "vendor/client.pin").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    service = ROOT / "image/s6-overlay/s6-rc.d/agent-index"
    assert re.search(r"^sha=[0-9a-f]{40}$", pin, re.MULTILINE)
    assert re.search(r"^sha256=[0-9a-f]{64}$", pin, re.MULTILINE)
    assert "sha256sum" in dockerfile
    assert (service / "type").read_text().strip() == "longrun"
    assert (service / "dependencies.d/plow-init").exists()
    assert (ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/agent-index").exists()


def test_periodic_report_does_not_receive_the_plow_token():
    run = (ROOT / "image/s6-overlay/s6-rc.d/agent-index/run").read_text()
    report_block = run.split("  esac\n", 1)[1]
    assert "PLOW_AGENT_TOKEN" not in report_block
    assert "AGENT_ID" in report_block


def test_secret_bearing_paths_are_excluded_from_git_and_build_context():
    for filename in (".gitignore", ".dockerignore"):
        text = (ROOT / filename).read_text()
        assert "plow-credentials" in text
        assert ".env" in text
    tracked_text = "\n".join(
        path.read_text(errors="ignore")
        for path in ROOT.rglob("*")
        if path.is_file()
        and not {".git", ".venv", "__pycache__", ".pytest_cache"}.intersection(path.parts)
        # The real local credential is intentionally present beside the
        # checkout while the container is running.  It is ignored by Git and
        # excluded from the Docker context; do not read it as source text in
        # this repository-wide secret scan.
        and path.name not in {"plow-credentials", ".env"}
    )
    assert not re.search(r"(?:sk|aik|plow)_[A-Za-z0-9_-]{24,}", tracked_text)
