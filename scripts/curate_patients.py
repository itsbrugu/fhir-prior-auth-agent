"""Selects a handful of Synthea-generated synthetic patients whose records
naturally support our two demo prior-auth scenarios, then trims each
patient's FHIR bundle down to clinically-relevant resource types before
committing them to data/patients/.

Run after scripts/generate_synthetic_data.sh (or the equivalent docker run)
has populated data/raw_synthea/fhir/*.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw_synthea" / "fhir"
OUT_DIR = ROOT / "data" / "patients"

KEEP_RESOURCE_TYPES = {
    "Patient",
    "Condition",
    "Observation",
    "Procedure",
    "MedicationRequest",
    "Medication",
    "DiagnosticReport",
    "Encounter",
    # Kept (even though not clinically interesting) because clinical
    # resources above reference them -- dropping these breaks the
    # transaction bundle's internal urn:uuid references.
    "Practitioner",
    "PractitionerRole",
    "Organization",
    "Location",
}

# Substrings we look for in a patient's Condition text to decide which
# demo scenario they naturally fit.
BACK_PAIN_TERMS = ["low back pain", "back pain", "backache"]
KNEE_TERMS = ["knee", "meniscus", "meniscal"]

MAX_PATIENTS_PER_SCENARIO = 4


def load_bundle(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def bundle_condition_texts(bundle: dict) -> list[str]:
    texts = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Condition":
            continue
        code = resource.get("code", {})
        texts.append((code.get("text") or "").lower())
        for coding in code.get("coding", []) or []:
            texts.append((coding.get("display") or "").lower())
    return texts

def trim_bundle(bundle: dict) -> dict:
    kept_entries = [
        entry for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") in KEEP_RESOURCE_TYPES
    ]
    bundle["entry"] = kept_entries
    return bundle


def patient_id_from_bundle(bundle: dict) -> str | None:
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            return resource.get("id")
    return None


def main():
    if not RAW_DIR.exists():
        raise SystemExit(f"No raw Synthea output found at {RAW_DIR}. Run generate_synthetic_data.sh first.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    back_pain_matches = []
    knee_matches = []

    for path in sorted(RAW_DIR.glob("*.json")):
        if path.name.startswith(("hospitalInformation", "practitionerInformation")):
            continue
        bundle = load_bundle(path)
        texts = " | ".join(bundle_condition_texts(bundle))
        if any(term in texts for term in BACK_PAIN_TERMS) and len(back_pain_matches) < MAX_PATIENTS_PER_SCENARIO:
            back_pain_matches.append((path, bundle))
        elif any(term in texts for term in KNEE_TERMS) and len(knee_matches) < MAX_PATIENTS_PER_SCENARIO:
            knee_matches.append((path, bundle))

    print(f"Back-pain scenario matches: {len(back_pain_matches)}")
    print(f"Knee scenario matches: {len(knee_matches)}")

    selected = back_pain_matches + knee_matches
    manifest = []
    for path, bundle in selected:
        trimmed = trim_bundle(bundle)
        patient_id = patient_id_from_bundle(trimmed)
        if not patient_id:
            continue
        out_path = OUT_DIR / f"{patient_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(trimmed, f)
        manifest.append({"patient_id": patient_id, "source_file": path.name})
        print(f"Wrote {out_path.name} ({len(trimmed['entry'])} resources)")

    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nCurated {len(manifest)} patients into {OUT_DIR}")
    print("Next: inspect data/patients/manifest.json and hand-pick patient IDs for")
    print("backend/rules/scenarios.json, then run scripts/seed_fhir_server.py")


if __name__ == "__main__":
    main()
