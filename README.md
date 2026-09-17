# FHIR Prior-Authorization AI Agent

An agentic AI demo that automates a healthcare-payer prior-authorization
determination against a **self-hosted, open-source FHIR server**, seeded
with **100% synthetic patients** -- no real PHI anywhere in this repo.

It exists to demonstrate, in running code, the skills behind a healthcare
AI-transformation architect role: LLM agents, RAG, HL7/FHIR, and
governance/explainability for a regulated payer workflow (prior
authorization / utilization management).

> Redox (a commercial FHIR integration platform) isn't open source, so this
> project uses genuinely open-source equivalents instead: **HAPI FHIR**
> (self-hosted FHIR R4 server) + **Synthea** (MITRE's synthetic patient
> generator) + **LangGraph** + **Claude**.

## What it does

1. Pick one of 4 synthetic patients, each pre-loaded with a realistic (but
   entirely fabricated) FHIR medical record.
2. Submit a prior-authorization request for a specific procedure.
3. Watch a LangGraph agent work through it live: fetch the patient's FHIR
   record -> check a deterministic coverage-policy rule -> retrieve
   supporting clinical evidence via RAG -> ask Claude to write a
   provider-facing rationale -> record a full audit trail.
4. Get an APPROVE / DENY / PEND determination with cited evidence and a
   step-by-step audit log.

Two scenarios are pre-loaded so the demo shows both outcomes, not just a
rubber stamp:

| Patient | Procedure | Expected result |
|---|---|---|
| Boyd O'Hara | MRI Lumbar Spine (72148) | **APPROVE** -- documented physical therapy on file |
| Alene Stiedemann | MRI Lumbar Spine (72148) | **PEND** -- no conservative therapy documented |
| Erminia Erdman | Knee arthroscopy (29881) | **APPROVE** -- MRI-confirmed meniscal tear |
| Deadra Walker | Knee arthroscopy (29881) | **DENY** -- no imaging confirmation on file |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system
diagram and a table mapping each part of this repo to the underlying
AI-architecture concepts, and [`docs/COMPLIANCE_NOTE.md`](docs/COMPLIANCE_NOTE.md)
for exactly where the synthetic data came from and how it was curated.

## Architecture at a glance

```
docker-compose.yml
├── hapi-fhir   open-source FHIR R4 server (hapiproject/hapi)
└── backend     FastAPI + LangGraph agent (Claude + Chroma RAG)
        └── serves the static frontend too, no separate build step
```

Prior-auth decisions are made by a small, unit-tested, YAML-driven rules
engine (`backend/rules/prior_auth_rules.yaml`) -- **not** by the LLM. Claude's
job is to explain that decision clearly, citing real evidence, never to
override it. Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quickstart

Prerequisites: Docker Desktop, Python 3.9+ (for the one-time seed script),
and an [Anthropic API key](https://console.anthropic.com/).

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

docker compose up -d hapi-fhir
```

Wait ~30-60s for HAPI FHIR to finish booting, then check it's up:

```bash
curl http://localhost:8080/fhir/metadata
```

Seed it with the 4 synthetic demo patients (one-time; only needs the
`httpx` package on your host):

```bash
pip install httpx
python scripts/seed_fhir_server.py
```

Start the backend (serves the UI too) and open it:

```bash
docker compose up -d backend
```

Open **http://localhost:8000** and submit a request.

> **Note:** HAPI FHIR runs with its default in-memory H2 database in this
> compose file (fine for a demo, zero setup). Data doesn't survive a
> container restart -- if `docker compose restart hapi-fhir` (or a Docker
> Desktop restart) wipes it, just re-run `python scripts/seed_fhir_server.py`.

## Regenerating the synthetic data yourself

`data/patients/` and `data/reference/` are already committed, so the
quickstart above doesn't require this. If you want to generate a fresh
population and re-curate:

```bash
scripts/generate_synthetic_data.sh 150   # runs Synthea via Docker/JRE
python scripts/curate_patients.py         # selects candidates matching our 2 scenarios
python scripts/finalize_demo_patients.py  # picks the final 4, augments 2, writes scenarios.json
```

## Running the tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/
```

## License

MIT -- see [LICENSE](LICENSE). Depends on HAPI FHIR (Apache-2.0), Synthea
(Apache-2.0), LangGraph, Chroma, and the Anthropic API.
