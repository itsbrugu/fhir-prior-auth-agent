from app.agent import rules_engine

LUMBAR_RULE = {
    "id": "PA-MRI-LUMBAR-01",
    "on_satisfied": "APPROVE",
    "on_not_satisfied": "PEND",
    "rationale_satisfied": "Conservative care documented.",
    "rationale_not_satisfied": "No conservative care documented.",
    "require_any": [
        {
            "label": "6+ weeks of physical therapy",
            "type": "resource_text_contains",
            "resource_types": ["Procedure", "Observation"],
            "contains": ["physical therapy"],
            "min_matches": 1,
        },
        {
            "label": "Red-flag neuro findings",
            "type": "resource_text_contains",
            "resource_types": ["Condition"],
            "contains": ["radiculopathy", "cauda equina"],
            "min_matches": 1,
        },
    ],
}


def evidence(resource_type, text, resource_id="1"):
    return {"resource_type": resource_type, "resource_id": resource_id, "text": text, "date": ""}


def test_approves_when_conservative_therapy_documented():
    items = [evidence("Procedure", "Physical therapy session for low back pain")]
    result = rules_engine.evaluate(LUMBAR_RULE, items)
    assert result["satisfied"] is True
    assert result["decision"] == "APPROVE"
    assert "6+ weeks of physical therapy" in result["matched_criteria"]


def test_approves_when_red_flag_condition_present():
    items = [evidence("Condition", "Lumbar radiculopathy")]
    result = rules_engine.evaluate(LUMBAR_RULE, items)
    assert result["satisfied"] is True
    assert result["decision"] == "APPROVE"


def test_pends_when_no_criteria_met():
    items = [evidence("Observation", "Blood pressure 120/80")]
    result = rules_engine.evaluate(LUMBAR_RULE, items)
    assert result["satisfied"] is False
    assert result["decision"] == "PEND"
    assert result["matched_criteria"] == []


def test_wrong_resource_type_does_not_match():
    # "physical therapy" text on a Condition (not Procedure/Observation) shouldn't count.
    items = [evidence("Condition", "History of physical therapy referral")]
    result = rules_engine.evaluate(LUMBAR_RULE, items)
    assert result["satisfied"] is False


def test_get_rule_for_procedure_returns_none_for_unknown_code():
    assert rules_engine.get_rule_for_procedure("00000") is None
