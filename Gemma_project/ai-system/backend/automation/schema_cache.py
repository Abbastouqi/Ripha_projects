"""
Persistent cache for Riphah admission portal schemas.

Stores the exact CSS selectors that worked during a previous fill so that
subsequent runs skip the LLM-mapping step and go straight to filling.

Storage: backend/cache/portal_schemas.json
TTL: CACHE_TTL_DAYS (default 7). After expiry the portal is re-scanned.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

CACHE_TTL_DAYS = 7
_CACHE_DIR  = os.path.join(os.path.dirname(__file__), "..", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "portal_schemas.json")
_LOCK = threading.Lock()


def _url_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _load() -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def get_schema(portal_url: str) -> Optional[dict]:
    """
    Return the cached schema for a portal URL if it exists and is fresh.
    Returns None if expired or not found.
    """
    with _LOCK:
        all_schemas = _load()
        entry = all_schemas.get(_url_key(portal_url))
        if not entry:
            return None
        try:
            age = datetime.now() - datetime.fromisoformat(entry.get("saved_at", ""))
            if age > timedelta(days=CACHE_TTL_DAYS):
                return None
        except Exception:
            return None
        return entry


def save_schema(
    portal_url: str,
    field_selectors: dict,
    navigation_steps: list | None = None,
    discovered_fields: list | None = None,
) -> None:
    """
    Persist a portal schema.

    field_selectors: {data_key -> css_selector} — the selectors that actually worked
    navigation_steps: list of {"action": "click", "selector": "..."} dicts
    discovered_fields: raw field list from portal scan
    """
    with _LOCK:
        all_schemas = _load()
        all_schemas[_url_key(portal_url)] = {
            "portal_url":       portal_url,
            "field_selectors":  field_selectors,
            "navigation_steps": navigation_steps or [],
            "discovered_fields": discovered_fields or [],
            "saved_at":         datetime.now().isoformat(),
            "fill_count":       all_schemas.get(_url_key(portal_url), {}).get("fill_count", 0) + 1,
        }
        _save(all_schemas)
    print(f"[SchemaCache] Saved schema for {portal_url} — "
          f"{len(field_selectors)} selectors cached")


def update_selectors(portal_url: str, new_selectors: dict) -> None:
    """Merge newly discovered selectors into the existing cache entry."""
    with _LOCK:
        all_schemas = _load()
        key = _url_key(portal_url)
        entry = all_schemas.get(key, {"portal_url": portal_url, "navigation_steps": [], "discovered_fields": []})
        existing = entry.get("field_selectors", {})
        existing.update(new_selectors)
        entry["field_selectors"] = existing
        entry["saved_at"] = datetime.now().isoformat()
        all_schemas[key] = entry
        _save(all_schemas)


def clear_schema(portal_url: str) -> None:
    with _LOCK:
        data = _load()
        data.pop(_url_key(portal_url), None)
        _save(data)


def get_cache_summary() -> list[dict]:
    with _LOCK:
        data = _load()
        return [
            {
                "url":        v.get("portal_url"),
                "selectors":  len(v.get("field_selectors", {})),
                "fill_count": v.get("fill_count", 0),
                "saved_at":   v.get("saved_at"),
            }
            for v in data.values()
        ]


# ---------------------------------------------------------------------------
# Workflow schema cache  (login/registration selectors, 3-day TTL)
# ---------------------------------------------------------------------------

WORKFLOW_TTL_DAYS = 3
_WORKFLOW_FILE    = os.path.join(_CACHE_DIR, "portal_workflow.json")


def _load_workflow() -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if not os.path.exists(_WORKFLOW_FILE):
        return {}
    try:
        with open(_WORKFLOW_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_workflow(data: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_WORKFLOW_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def get_workflow(portal_url: str) -> Optional[dict]:
    """Return the cached portal workflow schema if it exists and is fresh (≤3 days)."""
    with _LOCK:
        all_data = _load_workflow()
        entry    = all_data.get(_url_key(portal_url))
        if not entry:
            return None
        try:
            age = datetime.now() - datetime.fromisoformat(entry.get("explored_at", ""))
            if age > timedelta(days=WORKFLOW_TTL_DAYS):
                return None
        except Exception:
            return None
        return entry


def save_workflow(portal_url: str, schema: dict) -> None:
    """Persist a portal workflow schema (login/registration/verification selectors)."""
    with _LOCK:
        all_data = _load_workflow()
        all_data[_url_key(portal_url)] = schema
        _save_workflow(all_data)
    print(f"[WorkflowCache] Saved workflow schema for {portal_url}")
