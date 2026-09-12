from pathlib import Path
from uuid import uuid4

from hackathon_competitor.capabilities.research import discover_sources, extract_spec

FIXTURE = Path(__file__).parent / "fixtures/generic_hackathon/index.html"


def test_generic_rules_page_is_discovered_and_conservatively_extracted():
    sources = discover_sources(str(FIXTURE))
    assert len(sources) == 2
    spec, evidence, contradictions = extract_spec(uuid4(), sources)
    assert spec.name == "Open Agents Challenge"
    assert (
        "Teams must use Python 3.11 or newer in the submitted agent." in spec.required_technologies
    )
    assert any("public repository" in item.text for item in spec.submission_requirements)
    assert any("fabricate users" in item for item in spec.prohibited_actions)
    assert contradictions == []
    assert all("upload every credential" not in item.claim for item in evidence)
