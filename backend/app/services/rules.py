import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RuleSpec:
    category: str
    field: str
    operator: str
    pattern: str
    priority: int


@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    source: str


def message_text(subject: str | None, sender: str | None, body: str | None) -> str:
    return "\n".join(part for part in (subject or "", sender or "", body or "") if part).strip()


def _field_value(field: str, subject: str, sender: str, body: str) -> str:
    if field == "subject":
        return subject
    if field == "sender":
        return sender
    if field == "body":
        return body
    return f"{subject}\n{sender}\n{body}"


def rule_matches(rule: RuleSpec, subject: str, sender: str, body: str) -> bool:
    haystack = _field_value(rule.field, subject, sender, body)
    pattern = rule.pattern or ""
    if rule.operator == "contains":
        return pattern.casefold() in haystack.casefold()
    if rule.operator == "equals":
        return pattern.casefold() == haystack.strip().casefold()
    if rule.operator == "regex":
        try:
            return re.search(pattern, haystack, flags=re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def apply_rules(
    rules: list[RuleSpec],
    subject: str | None,
    sender: str | None,
    body: str | None,
) -> Classification | None:
    subject_s = subject or ""
    sender_s = sender or ""
    body_s = body or ""
    ordered = sorted(rules, key=lambda rule: rule.priority, reverse=True)
    for rule in ordered:
        if rule_matches(rule, subject_s, sender_s, body_s):
            return Classification(category=rule.category, confidence=0.99, source="rule")
    return None
