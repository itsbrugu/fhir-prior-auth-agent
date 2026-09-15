"""Deterministic coverage-criteria rules engine.

This is the auditable policy layer: given a procedure code and the patient's
fetched FHIR evidence items, it decides whether documented criteria are met
using plain substring matching against resource text -- no LLM involved.
The LLM layer downstream explains this result; it never changes it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import settings

_rules_cache: list[dict] | None = None


def _load_rules() -> list[dict]:
    global _rules_cache
    if _rules_cache is None:
        path = Path(settings.rules_path)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _rules_cache = data["rules"]
    return _rules_cache


def get_rule_for_procedure(procedure_code: str) -> dict | None:
    for rule in _load_rules():
        if rule["procedure_code"] == procedure_code:
            return rule
    return None


def _evaluate_criterion(criterion: dict, evidence_items: list[dict]) -> tuple[bool, list[dict]]:
    resource_types = set(criterion.get("resource_types", []))
    contains = [c.lower() for c in criterion.get("contains", [])]
    min_matches = criterion.get("min_matches", 1)

    matches = []
    for item in evidence_items:
        if resource_types and item["resource_type"] not in resource_types:
            continue
        text_lower = item["text"].lower()
        if any(term in text_lower for term in contains):
            matches.append(item)

    return len(matches) >= min_matches, matches


def evaluate(rule: dict, evidence_items: list[dict]) -> dict:
    """Returns {satisfied, decision, rationale, matched_criteria, matched_evidence}."""
    satisfied_labels = []
    matched_evidence = []

    for criterion in rule.get("require_any", []):
        met, matches = _evaluate_criterion(criterion, evidence_items)
        if met:
            satisfied_labels.append(criterion["label"])
            matched_evidence.extend(matches)

    satisfied = len(satisfied_labels) > 0

    # require_all (if present) must ALL additionally hold
    for criterion in rule.get("require_all", []):
        met, matches = _evaluate_criterion(criterion, evidence_items)
        if not met:
            satisfied = False
        else:
            matched_evidence.extend(matches)

    decision = rule["on_satisfied"] if satisfied else rule["on_not_satisfied"]
    rationale = rule["rationale_satisfied"] if satisfied else rule["rationale_not_satisfied"]

    return {
        "satisfied": satisfied,
        "decision": decision,
        "rationale": rationale.strip(),
        "matched_criteria": satisfied_labels,
        "matched_evidence": [
            f"{m['resource_type']}/{m['resource_id']}: {m['text']}" for m in matched_evidence
        ],
    }
