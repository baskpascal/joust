from __future__ import annotations

from .models import (
    ComplianceReport,
    HackathonSpec,
    Rule,
    RuleSeverity,
    RuleStatus,
    RuleType,
)


def rules_from_spec(spec: HackathonSpec) -> list[Rule]:
    rules: list[Rule] = []
    for requirement in spec.eligibility_requirements:
        rule_type = (
            RuleType.LICENSING if "license" in requirement.text.lower() else RuleType.ELIGIBILITY
        )
        rules.append(
            Rule(
                id=requirement.id,
                text=requirement.text,
                type=rule_type,
                severity=RuleSeverity.BLOCKER,
                evidence_ids=requirement.evidence_ids,
                verification_method="repository and participant eligibility review",
            )
        )
    for index, text in enumerate(spec.required_technologies):
        rules.append(
            Rule(
                id=f"required-tech-{index}",
                text=text,
                type=RuleType.REQUIRED_TECHNOLOGY,
                severity=RuleSeverity.BLOCKER,
                evidence_ids=spec.evidence_ids,
                verification_method="implementation and dependency inspection",
            )
        )
    for index, text in enumerate(spec.prohibited_actions):
        rules.append(
            Rule(
                id=f"prohibited-{index}",
                text=text,
                type=RuleType.PROHIBITED,
                severity=RuleSeverity.BLOCKER,
                evidence_ids=spec.evidence_ids,
                verification_method="repository, telemetry, and behavior audit",
            )
        )
    for requirement in spec.submission_requirements:
        rules.append(
            Rule(
                id=requirement.id,
                text=requirement.text,
                type=RuleType.SUBMISSION,
                severity=RuleSeverity.BLOCKER,
                evidence_ids=requirement.evidence_ids,
                verification_method="submission artifact inspection",
            )
        )
    rules.append(
        Rule(
            id="deadline",
            text="Submit before the official deadline.",
            type=RuleType.DEADLINE,
            severity=RuleSeverity.BLOCKER,
            evidence_ids=spec.evidence_ids,
            verification_method="official timestamp comparison",
        )
    )
    return rules


def evaluate_compliance(rules: list[Rule], statuses: dict[str, RuleStatus]) -> ComplianceReport:
    evaluated = [
        rule.model_copy(update={"status": statuses.get(rule.id, RuleStatus.UNKNOWN)})
        for rule in rules
    ]
    failures = [
        rule.id
        for rule in evaluated
        if rule.severity == RuleSeverity.BLOCKER and rule.status == RuleStatus.FAIL
    ]
    unknowns = [
        rule.id
        for rule in evaluated
        if rule.severity == RuleSeverity.BLOCKER and rule.status == RuleStatus.UNKNOWN
    ]
    return ComplianceReport(
        rules=evaluated,
        blocker_failures=failures,
        blocker_unknowns=unknowns,
        ready=not failures and not unknowns,
    )
