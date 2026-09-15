"""SQLite-backed store for prior-auth requests, decisions, and their audit trail."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                procedure_code TEXT NOT NULL,
                procedure_display TEXT NOT NULL,
                diagnosis_code TEXT,
                diagnosis_display TEXT,
                status TEXT NOT NULL,
                decision TEXT,
                rationale TEXT,
                evidence_citations TEXT,
                matched_criteria TEXT,
                rule_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                step TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )


def create_request(patient_id: str, procedure_code: str, procedure_display: str,
                    diagnosis_code: str | None, diagnosis_display: str | None) -> str:
    request_id = str(uuid.uuid4())
    now = _now()
    with _lock, _conn() as conn:
        conn.execute(
            """INSERT INTO requests
               (id, patient_id, procedure_code, procedure_display, diagnosis_code,
                diagnosis_display, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
            (request_id, patient_id, procedure_code, procedure_display,
             diagnosis_code, diagnosis_display, now, now),
        )
    return request_id


def append_audit_step(request_id: str, step: str, summary: str, detail: str | None = None) -> None:
    now = _now()
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO audit_steps (request_id, step, summary, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
            (request_id, step, summary, detail, now),
        )
        conn.execute("UPDATE requests SET status = 'RUNNING', updated_at = ? WHERE id = ?", (now, request_id))


def set_result(request_id: str, decision: str, rationale: str, evidence_citations: list[str],
               matched_criteria: list[str], rule_id: str | None) -> None:
    now = _now()
    with _lock, _conn() as conn:
        conn.execute(
            """UPDATE requests SET status = 'COMPLETE', decision = ?, rationale = ?,
               evidence_citations = ?, matched_criteria = ?, rule_id = ?, updated_at = ?
               WHERE id = ?""",
            (decision, rationale, json.dumps(evidence_citations), json.dumps(matched_criteria),
             rule_id, now, request_id),
        )


def set_error(request_id: str, error: str) -> None:
    now = _now()
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE requests SET status = 'ERROR', error = ?, updated_at = ? WHERE id = ?",
            (error, now, request_id),
        )


def get_request(request_id: str) -> dict | None:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            return None
        request = dict(row)
        steps = conn.execute(
            "SELECT step, summary, detail, timestamp FROM audit_steps WHERE request_id = ? ORDER BY id ASC",
            (request_id,),
        ).fetchall()
        request["audit_steps"] = [dict(s) for s in steps]
        request["evidence_citations"] = json.loads(request["evidence_citations"]) if request["evidence_citations"] else []
        request["matched_criteria"] = json.loads(request["matched_criteria"]) if request["matched_criteria"] else []
        return request
