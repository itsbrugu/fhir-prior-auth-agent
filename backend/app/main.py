import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app import store
from app.agent.graph import run_prior_auth
from app.models import PatientSummary, PriorAuthRequestIn, PriorAuthRequestOut, PriorAuthStatus

app = FastAPI(title="FHIR Prior-Authorization Agent")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
SCENARIOS_PATH = Path(__file__).resolve().parent.parent / "rules" / "scenarios.json"


@app.on_event("startup")
def on_startup():
    store.init_db()


@app.get("/api/patients", response_model=list[PatientSummary])
def list_patients():
    if not SCENARIOS_PATH.exists():
        return []
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/prior-auth/submit", response_model=PriorAuthRequestOut, status_code=202)
def submit_prior_auth(req: PriorAuthRequestIn, background_tasks: BackgroundTasks):
    request_id = store.create_request(
        req.patient_id, req.procedure_code, req.procedure_display,
        req.diagnosis_code, req.diagnosis_display,
    )
    background_tasks.add_task(
        run_prior_auth, request_id, req.patient_id, req.procedure_code,
        req.procedure_display, req.diagnosis_code, req.diagnosis_display,
    )
    return PriorAuthRequestOut(request_id=request_id, status="PENDING")


@app.get("/api/prior-auth/{request_id}", response_model=PriorAuthStatus)
def get_prior_auth(request_id: str):
    record = store.get_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return record


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
