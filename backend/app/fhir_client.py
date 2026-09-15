"""Thin wrapper around a HAPI FHIR server's REST API."""

from __future__ import annotations

import httpx

from app.config import settings

EVIDENCE_RESOURCE_TYPES = [
    "Condition",
    "Observation",
    "Procedure",
    "MedicationRequest",
    "DiagnosticReport",
]


def _extract_text(resource: dict) -> str:
    """Pull every human-readable string out of a FHIR resource for search/RAG use."""
    parts: list[str] = []

    def add(value):
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    for concept_key in ("code", "valueCodeableConcept"):
        concept = resource.get(concept_key)
        if isinstance(concept, dict):
            add(concept.get("text"))
            for coding in concept.get("coding", []) or []:
                add(coding.get("display"))

    for note in resource.get("note", []) or []:
        if isinstance(note, dict):
            add(note.get("text"))

    narrative = resource.get("text")
    if isinstance(narrative, dict):
        add(narrative.get("div"))

    for reason in resource.get("reasonCode", []) or []:
        if isinstance(reason, dict):
            for coding in reason.get("coding", []) or []:
                add(coding.get("display"))

    conclusion = resource.get("conclusion")
    add(conclusion)

    return " | ".join(parts) if parts else ""


class FhirClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.fhir_base_url).rstrip("/")

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
        resp = await client.get(f"{self.base_url}/{path}", params=params, headers={"Accept": "application/fhir+json"})
        resp.raise_for_status()
        return resp.json()

    async def get_patient(self, patient_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            return await self._get(client, f"Patient/{patient_id}")

    async def get_resources_for_patient(self, resource_type: str, patient_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            bundle = await self._get(client, resource_type, params={"patient": patient_id, "_count": 100})
        return [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]

    async def list_patients(self, count: int = 50) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            bundle = await self._get(client, "Patient", params={"_count": count})
        return [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]

    async def get_patient_context(self, patient_id: str) -> dict:
        """Fetch a patient plus all clinically-relevant resources, flattened into
        searchable evidence items for both the rules engine and the RAG layer."""
        patient = await self.get_patient(patient_id)

        resources_by_type: dict[str, list[dict]] = {}
        for resource_type in EVIDENCE_RESOURCE_TYPES:
            resources_by_type[resource_type] = await self.get_resources_for_patient(resource_type, patient_id)

        evidence_items = []
        for resource_type, resources in resources_by_type.items():
            for resource in resources:
                text = _extract_text(resource)
                if text:
                    evidence_items.append(
                        {
                            "resource_type": resource_type,
                            "resource_id": resource.get("id", ""),
                            "text": text,
                            "date": resource.get("recordedDate")
                            or resource.get("effectiveDateTime")
                            or resource.get("performedDateTime")
                            or resource.get("issued")
                            or resource.get("authoredOn")
                            or "",
                        }
                    )

        return {
            "patient": patient,
            "resources_by_type": resources_by_type,
            "evidence_items": evidence_items,
        }


fhir_client = FhirClient()
