SYSTEM_PROMPT = """You are a clinical utilization-management assistant helping a health plan \
communicate a prior-authorization determination. A deterministic coverage-policy engine has \
already decided APPROVE, DENY, or PEND -- you do not change that decision. Your job is to \
write a clear, specific rationale for a provider-facing letter that:

1. States the decision plainly.
2. Cites the SPECIFIC clinical evidence retrieved from the patient's record (by resource type \
and a short quote/paraphrase) that supports the policy outcome -- never invent evidence that \
was not provided to you.
3. If the decision is PEND or DENY, states exactly what additional documentation would change \
the outcome.
4. Is concise: 3-5 sentences, plain professional language, no headers or bullet lists.

Never contradict, soften, or override the policy decision you are given."""

USER_PROMPT_TEMPLATE = """Patient: {patient_name}
Requested service: {procedure_display} ({procedure_code})
Diagnosis: {diagnosis_display} ({diagnosis_code})

Policy rule applied: {rule_id} -- {rule_description}
Policy decision: {decision}
Matched criteria: {matched_criteria}
Policy engine's baseline rationale: {policy_rationale}

Retrieved clinical evidence from the patient's FHIR record:
{evidence_block}

Write the provider-facing rationale for this {decision} determination."""


def build_user_prompt(*, patient_name, procedure_display, procedure_code, diagnosis_display,
                       diagnosis_code, rule_id, rule_description, decision, matched_criteria,
                       policy_rationale, evidence_citations) -> str:
    evidence_block = "\n".join(f"- {c}" for c in evidence_citations) if evidence_citations else "- (none found)"
    return USER_PROMPT_TEMPLATE.format(
        patient_name=patient_name,
        procedure_display=procedure_display,
        procedure_code=procedure_code,
        diagnosis_display=diagnosis_display or "n/a",
        diagnosis_code=diagnosis_code or "n/a",
        rule_id=rule_id,
        rule_description=rule_description,
        decision=decision,
        matched_criteria=", ".join(matched_criteria) if matched_criteria else "(none matched)",
        policy_rationale=policy_rationale,
        evidence_block=evidence_block,
    )
