const patientSelect = document.getElementById("patient-select");
const scenarioDesc = document.getElementById("scenario-desc");
const procedureDisplay = document.getElementById("procedure-display");
const procedureCode = document.getElementById("procedure-code");
const diagnosisCode = document.getElementById("diagnosis-code");
const diagnosisDisplay = document.getElementById("diagnosis-display");
const submitBtn = document.getElementById("submit-btn");

const progressPanel = document.getElementById("progress-panel");
const stepList = document.getElementById("step-list");
const decisionPanel = document.getElementById("decision-panel");
const decisionBadge = document.getElementById("decision-badge");
const rationaleText = document.getElementById("rationale-text");
const evidenceList = document.getElementById("evidence-list");
const auditList = document.getElementById("audit-list");

let patients = [];
let pollTimer = null;

async function loadPatients() {
  const res = await fetch("/api/patients");
  patients = await res.json();
  patientSelect.innerHTML = patients
    .map((p) => `<option value="${p.patient_id}">${p.name} — ${p.scenario_label}</option>`)
    .join("");
  onPatientChange();
}

function onPatientChange() {
  const patient = patients.find((p) => p.patient_id === patientSelect.value);
  if (!patient) return;
  scenarioDesc.textContent = patient.scenario_label;
  procedureDisplay.value = `${patient.suggested_procedure_display} (${patient.suggested_procedure_code})`;
  procedureCode.value = patient.suggested_procedure_code;
  diagnosisCode.value = patient.suggested_diagnosis_code || "";
  diagnosisDisplay.value = patient.suggested_diagnosis_display || "";
}

function renderSteps(steps) {
  stepList.innerHTML = steps
    .map(
      (s) => `<li><strong>${s.step.replaceAll("_", " ")}</strong><br />${s.summary}${
        s.detail ? `<div class="detail">${s.detail}</div>` : ""
      }</li>`
    )
    .join("");
}

function renderDecision(record) {
  decisionPanel.hidden = false;
  decisionBadge.textContent = record.decision;
  decisionBadge.className = `badge ${record.decision}`;
  rationaleText.textContent = record.rationale;
  evidenceList.innerHTML = (record.evidence_citations || [])
    .map((c) => `<li>${c}</li>`)
    .join("") || "<li>(no evidence citations)</li>";
  auditList.innerHTML = record.audit_steps
    .map(
      (s) => `<li><strong>${s.step.replaceAll("_", " ")}</strong> — ${s.timestamp}<br />${s.summary}</li>`
    )
    .join("");
}

async function poll(requestId) {
  const res = await fetch(`/api/prior-auth/${requestId}`);
  const record = await res.json();
  renderSteps(record.audit_steps);

  if (record.status === "COMPLETE" || record.status === "ERROR") {
    clearInterval(pollTimer);
    submitBtn.disabled = false;
    if (record.status === "COMPLETE") {
      renderDecision(record);
    } else {
      decisionPanel.hidden = false;
      decisionBadge.textContent = "ERROR";
      decisionBadge.className = "badge DENY";
      rationaleText.textContent = record.error || "Something went wrong.";
    }
  }
}

async function submitRequest() {
  submitBtn.disabled = true;
  progressPanel.hidden = false;
  decisionPanel.hidden = true;
  stepList.innerHTML = "";

  const payload = {
    patient_id: patientSelect.value,
    procedure_code: procedureCode.value,
    procedure_display: procedureDisplay.value.split(" (")[0],
    diagnosis_code: diagnosisCode.value || null,
    diagnosis_display: diagnosisDisplay.value || null,
  };

  const res = await fetch("/api/prior-auth/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const { request_id } = await res.json();

  pollTimer = setInterval(() => poll(request_id), 800);
}

patientSelect.addEventListener("change", onPatientChange);
submitBtn.addEventListener("click", submitRequest);
loadPatients();
