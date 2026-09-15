#!/usr/bin/env bash
# Generates a fresh batch of synthetic patients with Synthea (MITRE, Apache-2.0)
# via its official Docker image -- no local Java required.
#
# Output lands in data/raw_synthea/fhir/*.json. Run scripts/curate_patients.py
# afterwards to select and trim a demo-ready subset into data/patients/.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/data/raw_synthea"
POPULATION="${1:-150}"

mkdir -p "$OUT_DIR"

docker run --rm -v "$OUT_DIR:/output" synthetichealth/synthea:latest \
  -p "$POPULATION" \
  --exporter.fhir.export true \
  --exporter.baseDirectory /output

echo "Synthetic FHIR bundles written to $OUT_DIR/fhir"
