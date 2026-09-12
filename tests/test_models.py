from uuid import uuid4

import pytest
from pydantic import ValidationError

from hackathon_competitor.models import Evidence, Mission, Task


def test_contracts_reject_unknown_fields():
    with pytest.raises(ValidationError):
        Mission(title="x", objective="x", workspace_path=".", invented=True)


def test_depth_and_confidence_are_bounded():
    with pytest.raises(ValidationError):
        Task(mission_id=uuid4(), type="x", capability="x", depth_level=6)
    with pytest.raises(ValidationError):
        Evidence(
            mission_id=uuid4(),
            claim="x",
            source_type="official",
            confidence=1.1,
            authority="official",
        )
