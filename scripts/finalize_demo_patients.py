"""Finalizes the demo patient set from the output of curate_patients.py.

Synthea's generic disease modules produce realistic but very generic
Condition entries (e.g. "Chronic low back pain (finding)") without always
generating the specific downstream Procedure/DiagnosticReport evidence a
real utilization-management reviewer would look for (e.g. a documented
physical-therapy course, or an MRI report confirming a meniscal tear).

To get one clean, honest demonstration of each decision path, this script:
  1. Keeps exactly 4 of the 8 candidates from curate_patients.py, two per
     demo scenario -- selected because inspection showed they naturally
     contain (or naturally lack) the evidence our policy rules look for.
  2. For the two "as-is" patients, makes NO content changes -- their
     PEND / DENY outcome is genuinely how Synthea generated them.
  3. For the two "augmented" patients, adds exactly ONE additional,
     clearly-synthetic FHIR resource (a Procedure or DiagnosticReport)
     representing the missing evidence, so the demo can also show a clean
     APPROVE path. This is disclosed here and in docs/COMPLIANCE_NOTE.md --
     nothing about these patients was ever real to begin with.
  4. Writes backend/rules/scenarios.json describing all four for the UI.

Note: resource counts are NOT trimmed by recency here. Synthea's exported
bundles are internally self-referential (Condition -> Encounter -> Practitioner
etc. via urn:uuid), so dropping older entries breaks those references when
the bundle is POSTed to HAPI as a transaction. curate_patients.py already
keeps file sizes reasonable by dropping whole (unreferenced) resource types.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATIENTS_DIR = ROOT / "data" / "patients"
RAW_FHIR_DIR = ROOT / "data" / "raw_synthea" / "fhir"
REFERENCE_DIR = ROOT / "data" / "reference"
SCENARIOS_PATH = ROOT / "backend" / "rules" / "scenarios.json"

CONDITIONAL_REF_RE = re.compile(r"^(Organization|Location|Practitioner)\?identifier=[^|]*\|(.+)$")

DISCARD_FILES = [
    "a36727ea-e1e1-4798-86c2-8ad4418ab4ad.json",
    "47059596-e567-b1dc-16e5-de4150e50d86.json",
    "5a961577-b63a-2702-052e-aea384d2b070.json",
    "b72668b6-8b11-b439-c8cc-081b2d9d34a3.json",
]

LUMBAR_APPROVE_FILE = "3739fcf1-ff34-56de-b292-f036912be316.json"
LUMBAR_PEND_FILE = "b8e979c8-c402-8d42-c138-5fc9be3122e3.json"
KNEE_DENY_FILE = "4b764027-2ac8-e24b-e7a9-c56d07cec076.json"
KNEE_APPROVE_FILE = "4f172893-a4f8-04fd-c147-0c9c42aeef77.json"


def find_patient_id(bundle: dict) -> str:
    for entry in bundle["entry"]:
        if entry["resource"]["resourceType"] == "Patient":
            return entry["resource"]["id"]
    raise ValueError("no Patient resource in bundle")


def display_name(bundle: dict) -> str:
    for entry in bundle["entry"]:
        r = entry["resource"]
        if r["resourceType"] == "Patient":
            name = (r.get("name") or [{}])[0]
            given = " ".join(n.rstrip("0123456789") for n in name.get("given", []))
            family = (name.get("family") or "").rstrip("0123456789")
            return f"{given} {family}".strip()
    return "Unknown Patient"


def add_procedure(bundle: dict, patient_id: str, display: str, note: str) -> None:
    resource_id = f"synthetic-augment-{display.lower().replace(' ', '-')}"
    bundle["entry"].append(
        {
            "fullUrl": f"urn:uuid:{resource_id}",
            "resource": {
                "resourceType": "Procedure",
                "id": resource_id,
                "status": "completed",
                "subject": {"reference": f"Patient/{patient_id}"},
                "code": {"text": display},
                "note": [{"text": note}],
            },
            "request": {"method": "PUT", "url": f"Procedure/{resource_id}"},
        }
    )


def add_diagnostic_report(bundle: dict, patient_id: str, display: str, conclusion: str) -> None:
    resource_id = f"synthetic-augment-{display.lower().replace(' ', '-')}"
    bundle["entry"].append(
        {
            "fullUrl": f"urn:uuid:{resource_id}",
            "resource": {
                "resourceType": "DiagnosticReport",
                "id": resource_id,
                "status": "final",
                "subject": {"reference": f"Patient/{patient_id}"},
                "code": {"text": display},
                "conclusion": conclusion,
            },
            "request": {"method": "PUT", "url": f"DiagnosticReport/{resource_id}"},
        }
    )


def find_conditional_refs(node) -> set[tuple[str, str]]:
    """Recursively finds every Reference.reference value shaped like
    "Organization?identifier=system|value" and returns (resourceType, value) pairs."""
    found = set()
    if isinstance(node, dict):
        ref = node.get("reference")
        if isinstance(ref, str):
            m = CONDITIONAL_REF_RE.match(ref)
            if m:
                found.add((m.group(1), m.group(2)))
        for value in node.values():
            found |= find_conditional_refs(value)
    elif isinstance(node, list):
        for item in node:
            found |= find_conditional_refs(item)
    return found


def resource_matches_identifier(resource: dict, value: str) -> bool:
    for identifier in resource.get("identifier", []) or []:
        if identifier.get("value") == value:
            return True
    return False


def build_reference_bundle(needed: set[tuple[str, str]]) -> dict:
    """Pulls only the Organization/Location/Practitioner resources our 4 demo
    patients actually reference (by identifier) out of Synthea's population-wide
    hospitalInformation*.json / practitionerInformation*.json files."""
    entries = []
    seen_ids = set()
    for pattern in ("hospitalInformation*.json", "practitionerInformation*.json"):
        for path in RAW_FHIR_DIR.glob(pattern):
            source_bundle = load(path)
            for entry in source_bundle.get("entry", []):
                resource = entry.get("resource", {})
                resource_type = resource.get("resourceType")
                for wanted_type, wanted_value in needed:
                    if resource_type == wanted_type and resource_matches_identifier(resource, wanted_value):
                        if resource["id"] not in seen_ids:
                            entries.append(entry)
                            seen_ids.add(resource["id"])
    return {"resourceType": "Bundle", "type": "batch", "entry": entries}


def load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path: Path, bundle: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f)


def main():
    for name in DISCARD_FILES:
        path = PATIENTS_DIR / name
        if path.exists():
            path.unlink()
            print(f"Removed unused candidate {name}")

    scenarios = []

    # 1. Lumbar MRI -- APPROVE (augmented with a documented PT course)
    bundle = load(PATIENTS_DIR / LUMBAR_APPROVE_FILE)
    patient_id = find_patient_id(bundle)
    add_procedure(
        bundle, patient_id, "Physical therapy",
        "Completed 6-week course of physical therapy for chronic low back pain; "
        "symptoms persist despite conservative management.",
    )
    save(PATIENTS_DIR / LUMBAR_APPROVE_FILE, bundle)
    scenarios.append({
        "patient_id": patient_id,
        "name": display_name(bundle),
        "scenario_label": "Lumbar MRI -- conservative therapy documented (expect APPROVE)",
        "suggested_procedure_code": "72148",
        "suggested_procedure_display": "MRI Lumbar Spine without contrast",
        "suggested_diagnosis_code": "M54.5",
        "suggested_diagnosis_display": "Low back pain",
    })

    # 2. Lumbar MRI -- PEND (Synthea data used as-is, no PT documented)
    bundle = load(PATIENTS_DIR / LUMBAR_PEND_FILE)
    patient_id = find_patient_id(bundle)
    save(PATIENTS_DIR / LUMBAR_PEND_FILE, bundle)
    scenarios.append({
        "patient_id": patient_id,
        "name": display_name(bundle),
        "scenario_label": "Lumbar MRI -- no conservative therapy on file (expect PEND)",
        "suggested_procedure_code": "72148",
        "suggested_procedure_display": "MRI Lumbar Spine without contrast",
        "suggested_diagnosis_code": "M54.5",
        "suggested_diagnosis_display": "Low back pain",
    })

    # 3. Knee arthroscopy -- APPROVE (augmented with an MRI-confirmed meniscal tear)
    bundle = load(PATIENTS_DIR / KNEE_APPROVE_FILE)
    patient_id = find_patient_id(bundle)
    add_diagnostic_report(
        bundle, patient_id, "MRI knee without contrast",
        "MRI demonstrates a complex tear of the medial meniscus with associated joint effusion.",
    )
    save(PATIENTS_DIR / KNEE_APPROVE_FILE, bundle)
    scenarios.append({
        "patient_id": patient_id,
        "name": display_name(bundle),
        "scenario_label": "Knee arthroscopy -- MRI-confirmed meniscal tear (expect APPROVE)",
        "suggested_procedure_code": "29881",
        "suggested_procedure_display": "Knee arthroscopy with meniscectomy",
        "suggested_diagnosis_code": "S83.2",
        "suggested_diagnosis_display": "Meniscus tear",
    })

    # 4. Knee arthroscopy -- DENY (Synthea data used as-is, no imaging/locking documented)
    bundle = load(PATIENTS_DIR / KNEE_DENY_FILE)
    patient_id = find_patient_id(bundle)
    save(PATIENTS_DIR / KNEE_DENY_FILE, bundle)
    scenarios.append({
        "patient_id": patient_id,
        "name": display_name(bundle),
        "scenario_label": "Knee arthroscopy -- no imaging confirmation on file (expect DENY)",
        "suggested_procedure_code": "29881",
        "suggested_procedure_display": "Knee arthroscopy with meniscectomy",
        "suggested_diagnosis_code": "S83.2",
        "suggested_diagnosis_display": "Meniscus tear",
    })

    with open(PATIENTS_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)

    SCENARIOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCENARIOS_PATH, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)

    # The final 4 patient bundles reference Organization/Location/Practitioner
    # resources only by identifier (Synthea's "bulk export" convention). Pull
    # just the ones actually needed out of the population-wide info files so
    # those references resolve when seeded, without committing the whole thing.
    needed_refs = set()
    for name in (LUMBAR_APPROVE_FILE, LUMBAR_PEND_FILE, KNEE_APPROVE_FILE, KNEE_DENY_FILE):
        needed_refs |= find_conditional_refs(load(PATIENTS_DIR / name))

    if needed_refs and RAW_FHIR_DIR.exists():
        reference_bundle = build_reference_bundle(needed_refs)
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        save(REFERENCE_DIR / "hospital_and_practitioner.json", reference_bundle)
        print(f"\nWrote {len(reference_bundle['entry'])} reference Organization/Location/"
              f"Practitioner resources to {REFERENCE_DIR / 'hospital_and_practitioner.json'}")

    print(f"\nFinal demo patients written to {PATIENTS_DIR} and {SCENARIOS_PATH}")
    for s in scenarios:
        print(f"  {s['patient_id']}  {s['name']:<20}  {s['scenario_label']}")


if __name__ == "__main__":
    main()
