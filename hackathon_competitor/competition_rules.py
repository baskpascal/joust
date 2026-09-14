from __future__ import annotations

from .models import CompetitionRule, CompetitionRuleStatus
from .storage import Database

_CRITICAL_CATEGORIES = {
    "deadline",
    "eligibility",
    "judging",
    "leaderboard",
    "mandatory_integration",
    "prohibited",
    "scoring",
    "submission",
}


class CompetitionRuleService:
    """Persist rule observations and make supersession explicit."""

    def __init__(self, database: Database):
        self.database = database

    def record(self, rule: CompetitionRule) -> CompetitionRule:
        if rule.supersedes_rule_id is not None:
            prior = next(
                (
                    item
                    for item in self.database.list_competition_rules(rule.mission_id)
                    if item.id == rule.supersedes_rule_id
                ),
                None,
            )
            if prior is None:
                raise ValueError("superseded rule does not exist in this mission")
            if prior.status != CompetitionRuleStatus.ACTIVE:
                raise ValueError("only an active competition rule can be superseded")
            prior.status = CompetitionRuleStatus.SUPERSEDED
            self.database.save_competition_rule(prior)
            self.database.append_event(
                rule.mission_id,
                "COMPETITION_RULE_SUPERSEDED",
                {
                    "prior_rule_id": str(prior.id),
                    "new_rule_id": str(rule.id),
                    "category": rule.category,
                },
            )
        rule.status = CompetitionRuleStatus.ACTIVE
        self.database.save_competition_rule(rule)
        self.database.append_event(
            rule.mission_id,
            "COMPETITION_RULE_OBSERVED",
            {
                "rule_id": str(rule.id),
                "category": rule.category,
                "authority": rule.authority,
                "status": rule.status.value,
            },
        )
        if rule.supersedes_rule_id is not None and rule.category.lower() in _CRITICAL_CATEGORIES:
            self.database.append_event(
                rule.mission_id,
                "STRATEGY_REASSESSMENT_REQUIRED",
                {
                    "rule_id": str(rule.id),
                    "supersedes_rule_id": str(rule.supersedes_rule_id),
                    "category": rule.category,
                },
            )
        return rule
