from __future__ import annotations

from .capability import CapabilityRegistry, service_capability


INITIAL_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "research": (
        "hackathon_discovery",
        "rules_extraction",
        "rules_crosscheck",
        "web_research",
        "competitor_research",
        "sponsor_research",
        "technology_research",
        "historical_winner_research",
        "contradiction_search",
        "research_synthesis",
    ),
    "strategy": (
        "opportunity_mapping",
        "idea_generation",
        "idea_clustering",
        "idea_screening",
        "deep_idea_analysis",
        "strategy_debate",
        "strategy_selection",
        "premortem",
        "win_scenario_analysis",
        "risk_register",
    ),
    "architecture_product": (
        "prd_generation",
        "architecture_generation",
        "architecture_tournament",
        "implementation_planning",
        "acceptance_test_planning",
    ),
    "execution": (
        "workspace_setup",
        "coding_agent_handoff",
        "terminal_execution",
        "git_operations",
        "build_validation",
        "deployment_assistance",
    ),
    "evaluation": (
        "technical_judge",
        "product_judge",
        "innovation_judge",
        "ux_judge",
        "skeptical_judge",
        "sponsor_judge",
        "meta_judge",
        "red_team",
        "compliance_check",
        "test_gap_analysis",
    ),
    "submission": (
        "readme_generation",
        "submission_copy",
        "demo_tournament",
        "pitch_tournament",
    ),
}


def default_registry() -> CapabilityRegistry:
    names = [name for group in INITIAL_CAPABILITIES.values() for name in group]
    return CapabilityRegistry(service_capability(name) for name in names)
