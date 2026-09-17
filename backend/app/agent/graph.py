"""LangGraph agent that automates a single prior-authorization determination.

Nodes:
  fetch_patient_context     -> pulls the patient's FHIR record from HAPI
  check_coverage_rules      -> deterministic policy engine decision
  retrieve_clinical_evidence-> RAG lookup of the most relevant supporting evidence
  llm_reasoning              -> Claude writes the provider-facing rationale
  record_audit_trail        -> persists the final result

Every node also writes its own audit step to the SQLite store as it runs, so
the API can report live progress while the graph is still executing.
"""

import operator
from typing import Annotated, Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from app import store
from app.agent import rules_engine
from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.fhir_client import fhir_client
from app.rag import embed_store


class AgentState(TypedDict):
    request_id: str
    patient_id: str
    procedure_code: str
    procedure_display: str
    diagnosis_code: Optional[str]
    diagnosis_display: Optional[str]

    patient_name: str
    evidence_items: list
    rule: Optional[dict]
    rule_result: Optional[dict]
    retrieved_evidence: list
    decision: Optional[str]
    rationale: Optional[str]
    error: Optional[str]

    audit_log: Annotated[list, operator.add]


def _patient_display_name(patient: dict) -> str:
    names = patient.get("name") or []
    if not names:
        return patient.get("id", "unknown patient")
    n = names[0]
    given = " ".join(n.get("given", []))
    family = n.get("family", "")
    return f"{given} {family}".strip() or patient.get("id", "unknown patient")


async def fetch_patient_context(state: AgentState) -> dict:
    context = await fhir_client.get_patient_context(state["patient_id"])
    patient_name = _patient_display_name(context["patient"])
    summary = f"Fetched {len(context['evidence_items'])} clinical resources for {patient_name}."
    store.append_audit_step(state["request_id"], "fetch_patient_context", summary)
    return {
        "patient_name": patient_name,
        "evidence_items": context["evidence_items"],
        "audit_log": [{"step": "fetch_patient_context", "summary": summary}],
    }


async def check_coverage_rules(state: AgentState) -> dict:
    rule = rules_engine.get_rule_for_procedure(state["procedure_code"])
    if rule is None:
        summary = f"No coverage rule configured for procedure {state['procedure_code']}."
        store.append_audit_step(state["request_id"], "check_coverage_rules", summary)
        return {
            "rule": None,
            "rule_result": None,
            "error": summary,
            "audit_log": [{"step": "check_coverage_rules", "summary": summary}],
        }

    result = rules_engine.evaluate(rule, state["evidence_items"])
    summary = (
        f"Rule {rule['id']} evaluated -> {result['decision']} "
        f"({'criteria met' if result['satisfied'] else 'criteria NOT met'})."
    )
    detail = "Matched: " + (", ".join(result["matched_criteria"]) or "none")
    store.append_audit_step(state["request_id"], "check_coverage_rules", summary, detail)
    return {
        "rule": rule,
        "rule_result": result,
        "audit_log": [{"step": "check_coverage_rules", "summary": summary, "detail": detail}],
    }


async def retrieve_clinical_evidence(state: AgentState) -> dict:
    if state.get("rule") is None:
        return {"retrieved_evidence": []}

    embed_store.index_patient(state["patient_id"], state["evidence_items"])
    query = f"{state['procedure_display']} {state['rule']['description']}"
    citations = embed_store.retrieve(state["patient_id"], query, k=5)

    summary = f"Retrieved {len(citations)} relevant evidence passages via RAG."
    store.append_audit_step(state["request_id"], "retrieve_clinical_evidence", summary)
    return {
        "retrieved_evidence": citations,
        "audit_log": [{"step": "retrieve_clinical_evidence", "summary": summary}],
    }


async def llm_reasoning(state: AgentState) -> dict:
    if state.get("rule") is None or state.get("rule_result") is None:
        decision = "PEND"
        rationale = state.get("error") or "Unable to evaluate this request against a known coverage policy."
        store.append_audit_step(state["request_id"], "llm_reasoning", "Skipped Claude call: no applicable rule.")
        return {"decision": decision, "rationale": rationale, "audit_log": [
            {"step": "llm_reasoning", "summary": "Skipped Claude call: no applicable rule."}
        ]}

    rule = state["rule"]
    result = state["rule_result"]

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = build_user_prompt(
        patient_name=state["patient_name"],
        procedure_display=state["procedure_display"],
        procedure_code=state["procedure_code"],
        diagnosis_display=state.get("diagnosis_display"),
        diagnosis_code=state.get("diagnosis_code"),
        rule_id=rule["id"],
        rule_description=rule["description"],
        decision=result["decision"],
        matched_criteria=result["matched_criteria"],
        policy_rationale=result["rationale"],
        evidence_citations=state.get("retrieved_evidence") or result["matched_evidence"],
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    rationale = "".join(block.text for block in response.content if block.type == "text").strip()

    summary = f"Claude drafted the provider-facing rationale for decision {result['decision']}."
    store.append_audit_step(state["request_id"], "llm_reasoning", summary)
    return {
        "decision": result["decision"],
        "rationale": rationale,
        "audit_log": [{"step": "llm_reasoning", "summary": summary}],
    }


async def record_audit_trail(state: AgentState) -> dict:
    rule = state.get("rule")
    result = state.get("rule_result")

    # Log the step BEFORE writing the terminal status -- append_audit_step
    # marks the request RUNNING, and that write must not be the last one to
    # land or the request would never surface as COMPLETE/ERROR to the API.
    summary = f"Final decision recorded: {state.get('decision')}."
    store.append_audit_step(state["request_id"], "record_audit_trail", summary)

    if state.get("error") and result is None:
        store.set_error(state["request_id"], state["error"])
    else:
        store.set_result(
            request_id=state["request_id"],
            decision=state["decision"],
            rationale=state["rationale"],
            evidence_citations=state.get("retrieved_evidence") or (result["matched_evidence"] if result else []),
            matched_criteria=result["matched_criteria"] if result else [],
            rule_id=rule["id"] if rule else None,
        )

    return {"audit_log": [{"step": "record_audit_trail", "summary": summary}]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("fetch_patient_context", fetch_patient_context)
    graph.add_node("check_coverage_rules", check_coverage_rules)
    graph.add_node("retrieve_clinical_evidence", retrieve_clinical_evidence)
    graph.add_node("llm_reasoning", llm_reasoning)
    graph.add_node("record_audit_trail", record_audit_trail)

    graph.set_entry_point("fetch_patient_context")
    graph.add_edge("fetch_patient_context", "check_coverage_rules")
    graph.add_edge("check_coverage_rules", "retrieve_clinical_evidence")
    graph.add_edge("retrieve_clinical_evidence", "llm_reasoning")
    graph.add_edge("llm_reasoning", "record_audit_trail")
    graph.add_edge("record_audit_trail", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_prior_auth(request_id: str, patient_id: str, procedure_code: str,
                          procedure_display: str, diagnosis_code: Optional[str],
                          diagnosis_display: Optional[str]) -> None:
    graph = get_graph()
    initial_state: AgentState = {
        "request_id": request_id,
        "patient_id": patient_id,
        "procedure_code": procedure_code,
        "procedure_display": procedure_display,
        "diagnosis_code": diagnosis_code,
        "diagnosis_display": diagnosis_display,
        "patient_name": "",
        "evidence_items": [],
        "rule": None,
        "rule_result": None,
        "retrieved_evidence": [],
        "decision": None,
        "rationale": None,
        "error": None,
        "audit_log": [],
    }
    try:
        await graph.ainvoke(initial_state)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        store.set_error(request_id, str(exc))
