"""Loads the curated synthetic patient bundles from data/patients/*.json into
a running HAPI FHIR server as FHIR transaction Bundles.
"""

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PATIENTS_DIR = ROOT / "data" / "patients"
REFERENCE_BUNDLE_PATH = ROOT / "data" / "reference" / "hospital_and_practitioner.json"
FHIR_BASE_URL = "http://localhost:8080/fhir"


def to_transaction_bundle(bundle: dict) -> dict:
    """Synthea's exporter sets some entries' request to a conditional match
    URL (e.g. "Location?identifier=...") for dedup against a real EHR. Against
    a fresh, empty HAPI instance we don't need that -- we just PUT every
    resource by its own id, which is simpler and avoids match-URL parsing
    quirks. We keep each entry's original fullUrl (urn:uuid:...) so internal
    cross-references between resources in this same transaction still resolve."""
    entries = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource")
        if not resource:
            continue
        resource_type = resource["resourceType"]
        resource_id = resource.get("id")
        transaction_entry = {
            "resource": resource,
            "request": {
                "method": "PUT",
                "url": f"{resource_type}/{resource_id}" if resource_id else resource_type,
            },
        }
        if entry.get("fullUrl"):
            transaction_entry["fullUrl"] = entry["fullUrl"]
        entries.append(transaction_entry)
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def main():
    if not PATIENTS_DIR.exists():
        raise SystemExit(f"No curated patients found at {PATIENTS_DIR}. Run curate_patients.py first.")

    paths = sorted(PATIENTS_DIR.glob("*.json"))
    paths = [p for p in paths if p.name != "manifest.json"]
    if not paths:
        raise SystemExit(f"No patient bundles in {PATIENTS_DIR}.")

    with httpx.Client(timeout=30) as client:
        if REFERENCE_BUNDLE_PATH.exists():
            with open(REFERENCE_BUNDLE_PATH, "r", encoding="utf-8") as f:
                reference_bundle = json.load(f)
            resp = client.post(
                FHIR_BASE_URL, json=reference_bundle,
                headers={"Content-Type": "application/fhir+json"},
            )
            if resp.status_code >= 300:
                print(f"FAILED reference bundle: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
            else:
                print(f"Seeded reference bundle ({len(reference_bundle['entry'])} Organization/Location/Practitioner resources)")

        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                bundle = json.load(f)
            transaction = to_transaction_bundle(bundle)
            resp = client.post(
                FHIR_BASE_URL,
                json=transaction,
                headers={"Content-Type": "application/fhir+json"},
            )
            if resp.status_code >= 300:
                print(f"FAILED {path.name}: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
            else:
                print(f"Seeded {path.name} ({len(transaction['entry'])} resources)")


if __name__ == "__main__":
    main()
