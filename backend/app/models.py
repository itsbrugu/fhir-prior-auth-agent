from typing import Optional

from pydantic import BaseModel


class PriorAuthRequestIn(BaseModel):
    patient_id: str
    procedure_code: str
    procedure_display: str
    diagnosis_code: Optional[str] = None
    diagnosis_display: Optional[str] = None


class PriorAuthRequestOut(BaseModel):
    request_id: str
    status: str


class AuditStep(BaseModel):
    step: str
    summary: str
    detail: Optional[str] = None
    timestamp: str


class PriorAuthStatus(BaseModel):
    request_id: str
    patient_id: str
    procedure_code: str
    procedure_display: str
    diagnosis_code: Optional[str] = None
    diagnosis_display: Optional[str] = None
    status: str  # PENDING | RUNNING | COMPLETE | ERROR
    decision: Optional[str] = None  # APPROVE | DENY | PEND
    rationale: Optional[str] = None
    evidence_citations: list[str] = []
    matched_criteria: list[str] = []
    rule_id: Optional[str] = None
    error: Optional[str] = None
    audit_steps: list[AuditStep] = []
    created_at: str
    updated_at: str


class PatientSummary(BaseModel):
    patient_id: str
    name: str
    scenario_label: str
    suggested_procedure_code: str
    suggested_procedure_display: str
    suggested_diagnosis_code: Optional[str] = None
    suggested_diagnosis_display: Optional[str] = None
