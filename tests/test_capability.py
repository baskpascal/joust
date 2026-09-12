from types import SimpleNamespace

import pytest

from hackathon_competitor.capability import CapabilityRegistry
from hackathon_competitor.models import CapabilityResult


class ExampleCapability:
    name = "example"

    def execute(self, mission, task, context):
        return CapabilityResult(summary=context["summary"])


def test_capability_registry_dispatches_structured_results():
    registry = CapabilityRegistry([ExampleCapability()])
    result = registry.get("example").execute(
        SimpleNamespace(), SimpleNamespace(), {"summary": "done"}
    )
    assert result == CapabilityResult(summary="done")
    assert registry.names() == ("example",)


def test_capability_registry_rejects_duplicates_and_unknown_names():
    registry = CapabilityRegistry([ExampleCapability()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ExampleCapability())
    with pytest.raises(LookupError, match="not registered"):
        registry.get("missing")
