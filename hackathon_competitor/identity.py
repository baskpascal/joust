from __future__ import annotations

import os
from collections.abc import Mapping

from .models import AgentIdentity


PRODUCT_NAME = "Joust"
DISPLAY_NAME = "Joust"
BRAND = "Joust"
COMMAND_CTA = "Joust it."


def identity_from_environment(
    environment: Mapping[str, str] | None = None,
) -> AgentIdentity | None:
    """Return the configured identity without inventing an external id."""

    values = environment if environment is not None else os.environ
    agent_id = values.get("AGENT_ID", "").strip()
    if not agent_id:
        return None
    return AgentIdentity(
        agent_id=agent_id,
        product_name=PRODUCT_NAME,
        display_name=DISPLAY_NAME,
        brand=BRAND,
        command_cta=COMMAND_CTA,
    )
