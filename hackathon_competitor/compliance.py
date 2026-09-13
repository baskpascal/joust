from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .models import (
    BuildRun,
    ComplianceReport,
    HackathonSpec,
    ProjectTarget,
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


def inspect_project_target(
    spec: HackathonSpec,
    target: ProjectTarget,
    *,
    build_runs: Iterable[BuildRun] = (),
) -> ComplianceReport:
    """Evaluate rules against the mission project, never against Galahad itself."""

    root = Path(target.local_path).resolve()
    runs = list(build_runs)
    passed_phases = {run.phase for run in runs if run.passed}
    statuses: dict[str, RuleStatus] = {}
    for rule in rules_from_spec(spec):
        text = rule.text.lower()
        if rule.type == RuleType.LICENSING:
            license_path = root / "LICENSE"
            statuses[rule.id] = (
                RuleStatus.PASS
                if license_path.is_file()
                and license_path.read_text(encoding="utf-8", errors="replace")
                .lstrip()
                .startswith("MIT License")
                else RuleStatus.FAIL
            )
        elif rule.type == RuleType.REQUIRED_TECHNOLOGY:
            language = (target.language or "").lower()
            framework = (target.framework or "").lower()
            has_python = any(root.rglob("*.py")) if root.is_dir() else False
            statuses[rule.id] = (
                RuleStatus.PASS
                if "python" in text and ("python" in language or has_python)
                else RuleStatus.PASS
                if framework and framework in text
                else RuleStatus.UNKNOWN
            )
        elif rule.type == RuleType.SUBMISSION:
            if "repository" in text or "source code" in text:
                statuses[rule.id] = (
                    RuleStatus.PASS
                    if target.repository_url or (root / ".git").is_dir()
                    else RuleStatus.UNKNOWN
                )
            elif "demo" in text or "video" in text:
                statuses[rule.id] = (
                    RuleStatus.PASS if "run" in passed_phases else RuleStatus.UNKNOWN
                )
            else:
                statuses[rule.id] = RuleStatus.UNKNOWN
        elif rule.type == RuleType.PROHIBITED:
            # A prohibition is a behavioral claim. Without an explicit audit
            # artifact, stay conservative instead of treating source absence
            # as proof of compliance.
            statuses[rule.id] = RuleStatus.UNKNOWN
        elif rule.type == RuleType.DEADLINE:
            statuses[rule.id] = RuleStatus.UNKNOWN
        else:
            statuses[rule.id] = RuleStatus.UNKNOWN
    return evaluate_compliance(rules_from_spec(spec), statuses)
