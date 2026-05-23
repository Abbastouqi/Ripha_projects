"""
Persistent local store for admission applications.

Why this exists
---------------
The Riphah portal automation produces credentials (portal email + auto-derived
password), a reference number, and a dashboard URL. Previously these only lived
in the in-memory `_session_workflows` dict and in the chat bubble shown by the
`AdmissionProgress.jsx` component. If the user closed the app, refreshed the
browser, or simply asked the bot later "what was my password?", that data was
gone.

This module persists every completed (or partially-completed) admission
attempt to a JSON file so that:

  • the bot can answer "show my applications" / "what was my password?"
  • a REST endpoint can list past applications
  • a future session can re-use the same credentials instead of re-registering

Storage
-------
File: backend/cache/admissions.json
Schema:
    {
        "applications": [
            {
                "application_id":   "RIU-A1B2C3D4",
                "session_id":       "<chat session id>",
                "full_name":        "...",
                "email":            "...",
                "cnic":             "...",
                "phone":            "...",
                "program":          "...",
                "campus":           "...",
                "portal_email":     "...",
                "portal_password":  "...",
                "reference":        "<portal-issued reference if any>",
                "dashboard_url":    "https://admissions.riphah.edu.pk/...",
                "status":           "submitted" | "needs_verification" | "failed",
                "needs_verification": bool,
                "verification_type":  "email" | "otp" | null,
                "created_at":       "ISO-8601",
                "updated_at":       "ISO-8601"
            },
            ...
        ]
    }

No external dependencies — just a JSON file guarded by a lock.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Optional

_CACHE_DIR  = os.path.join(os.path.dirname(__file__), "..", "cache")
_STORE_FILE = os.path.join(_CACHE_DIR, "admissions.json")
_LOCK       = threading.Lock()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if not os.path.exists(_STORE_FILE):
        return {"applications": []}
    try:
        with open(_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "applications" not in data:
            return {"applications": []}
        return data
    except Exception:
        return {"applications": []}


def _save(data: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, _STORE_FILE)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _matches(rec: dict, *, session_id: str | None, email: str | None, cnic: str | None) -> bool:
    if session_id and rec.get("session_id") == session_id:
        return True
    if email and rec.get("portal_email", "").lower() == email.lower():
        return True
    if cnic and rec.get("cnic", "").replace("-", "") == cnic.replace("-", ""):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_application(record: dict) -> dict:
    """
    Insert or update an application record.

    Uniqueness key (in order of precedence):
      1. application_id  — preferred, stable, generated at workflow start
      2. session_id      — chat session
      3. email + cnic    — fall-back identity

    Returns the saved record (with timestamps set).
    """
    if not record:
        return {}

    with _LOCK:
        store = _load()
        apps  = store.get("applications", [])

        app_id     = record.get("application_id", "")
        session_id = record.get("session_id", "")
        email      = (record.get("portal_email") or record.get("email") or "").lower()
        cnic       = record.get("cnic", "")

        existing_idx = None
        for i, rec in enumerate(apps):
            if app_id and rec.get("application_id") == app_id:
                existing_idx = i
                break
            if session_id and rec.get("session_id") == session_id:
                existing_idx = i
                break
            if email and rec.get("portal_email", "").lower() == email and cnic and rec.get("cnic", "").replace("-", "") == cnic.replace("-", ""):
                existing_idx = i
                break

        now = _now_iso()
        if existing_idx is None:
            record["created_at"] = now
            record["updated_at"] = now
            apps.append(record)
        else:
            merged = dict(apps[existing_idx])
            merged.update({k: v for k, v in record.items() if v not in (None, "")})
            merged["updated_at"] = now
            merged.setdefault("created_at", apps[existing_idx].get("created_at", now))
            apps[existing_idx] = merged
            record = merged

        store["applications"] = apps
        _save(store)
        return record


def get_by_session(session_id: str) -> Optional[dict]:
    """Return the most recent application for a chat session, or None."""
    if not session_id:
        return None
    with _LOCK:
        for rec in reversed(_load().get("applications", [])):
            if rec.get("session_id") == session_id:
                return rec
    return None


def get_by_application_id(application_id: str) -> Optional[dict]:
    if not application_id:
        return None
    with _LOCK:
        for rec in _load().get("applications", []):
            if rec.get("application_id") == application_id:
                return rec
    return None


def find_application(
    *,
    session_id: str | None = None,
    email: str | None = None,
    cnic: str | None = None,
) -> Optional[dict]:
    """Find the most recent matching application by any combination of identifiers."""
    if not any([session_id, email, cnic]):
        return None
    with _LOCK:
        for rec in reversed(_load().get("applications", [])):
            if _matches(rec, session_id=session_id, email=email, cnic=cnic):
                return rec
    return None


def list_all(limit: int = 50) -> list[dict]:
    """Return all applications, newest first."""
    with _LOCK:
        apps = list(_load().get("applications", []))
    apps.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return apps[:limit]


def delete_application(application_id: str) -> bool:
    with _LOCK:
        store = _load()
        before = len(store.get("applications", []))
        store["applications"] = [
            r for r in store.get("applications", [])
            if r.get("application_id") != application_id
        ]
        _save(store)
        return len(store["applications"]) != before
