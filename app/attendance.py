"""
Attendance + Presence tracking service.

State machine per person:
  OUT → (face detected, confidence > threshold) → CHECKIN  → IN
  IN  → (not seen for CHECKOUT_TIMEOUT_SEC)     → CHECKOUT → OUT

Events published to all WebSocket subscribers.
"""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Optional

import cv2
import numpy as np
from supabase import Client

from .config import COOLDOWN_SECONDS, CHECKOUT_TIMEOUT_SEC


class AttendanceService:
    def __init__(self, db: Client):
        self.db = db
        self._subscribers: list[asyncio.Queue] = []

        # In-memory presence state  {person_id: {"status","last_seen","checkin_at","name"}}
        self._presence: dict[str, dict] = {}

        # Load existing status from DB on startup
        self._load_current_status()

        # Start the checkout watchdog (runs every 30s)
        asyncio.get_event_loop().call_later(30, self._schedule_watchdog)

    # ── Public API ────────────────────────────────────────────────────────────

    async def on_face_seen(
        self,
        person_id: str,
        person_name: str,
        confidence: float,
        camera_id: str = "main",
    ) -> str:
        """
        Call this every time a known face is detected.
        Returns 'checkin', 'already_in', or 'cooldown'.
        """
        now = time.time()
        state = self._presence.get(person_id)

        if state is None:
            # First time we see this person this session
            state = {"status": "out", "last_seen": 0, "checkin_at": 0, "name": person_name}
            self._presence[person_id] = state

        state["last_seen"] = now
        state["name"] = person_name

        if state["status"] == "out":
            # CHECKIN
            state["status"] = "in"
            state["checkin_at"] = now
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._db_checkin, person_id, confidence, camera_id
            )
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[CHECK IN ] {ts} | {person_name:<20} | confidence: {confidence*100:.1f}% | saved to DB ✓")
            self._publish({
                "type": "checkin",
                "person_id": person_id,
                "person_name": person_name,
                "confidence": round(confidence, 4),
                "timestamp": time.strftime("%H:%M:%S"),
            })
            return "checkin"

        # Already IN — just update last_seen (no duplicate event)
        return "already_in"

    async def log_unknown(self, face_crop: np.ndarray) -> None:
        _, buf = cv2.imencode(".jpg", face_crop, [cv2.IMWRITE_JPEG_QUALITY, 70])
        b64 = base64.b64encode(buf).decode()
        loop = asyncio.get_event_loop()
        row_id = await loop.run_in_executor(None, self._insert_unknown, b64)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[UNKNOWN  ] {ts} | Unrecognised face detected — run enroll_unknown.py to enroll")
        self._publish({"type": "unknown_face", "face_id": row_id})

    def get_presence_snapshot(self) -> list[dict]:
        """Return list of people currently IN."""
        now = time.time()
        result = []
        for pid, s in self._presence.items():
            if s["status"] == "in":
                duration_min = int((now - s["checkin_at"]) / 60)
                result.append({
                    "person_id": pid,
                    "name": s["name"],
                    "checkin_at": time.strftime("%H:%M:%S", time.localtime(s["checkin_at"])),
                    "duration_min": duration_min,
                })
        return sorted(result, key=lambda x: x["checkin_at"])

    # ── Checkout watchdog ─────────────────────────────────────────────────────

    def _schedule_watchdog(self):
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(self._run_watchdog())
        loop.call_later(30, self._schedule_watchdog)

    async def _run_watchdog(self):
        now = time.time()
        for person_id, state in list(self._presence.items()):
            if state["status"] == "in":
                absent_for = now - state["last_seen"]
                if absent_for >= CHECKOUT_TIMEOUT_SEC:
                    state["status"] = "out"
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, self._db_checkout, person_id
                    )
                    ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n[CHECK OUT] {ts} | {state['name']:<20} | absent for {int(absent_for/60)} min | saved to DB ✓")
                    self._publish({
                        "type": "checkout",
                        "person_id": person_id,
                        "person_name": state["name"],
                        "absent_for_min": int(absent_for / 60),
                        "timestamp": time.strftime("%H:%M:%S"),
                    })

    # ── WebSocket pub/sub ─────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def _publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # ── DB operations (blocking — run in executor) ────────────────────────────

    def _load_current_status(self):
        try:
            rows = self.db.table("current_status").select(
                "person_id, status, checkin_at, last_seen, persons(name)"
            ).execute().data
            for r in rows:
                pid = r["person_id"]
                name = (r.get("persons") or {}).get("name", "Unknown")
                checkin_ts = r.get("checkin_at") or ""
                last_ts    = r.get("last_seen") or ""
                # Convert ISO string to epoch
                checkin_epoch = _iso_to_epoch(checkin_ts)
                last_epoch    = _iso_to_epoch(last_ts)
                self._presence[pid] = {
                    "status": r.get("status", "out"),
                    "last_seen": last_epoch,
                    "checkin_at": checkin_epoch,
                    "name": name,
                }
            print(f"[attendance] Loaded {len(rows)} presence states from DB")
        except Exception as exc:
            print(f"[attendance] Could not load current_status: {exc}")

    def _db_checkin(self, person_id: str, confidence: float, camera_id: str):
        try:
            # Log event
            self.db.table("presence_log").insert({
                "person_id": person_id,
                "event_type": "checkin",
                "confidence": confidence,
                "camera_id": camera_id,
            }).execute()
            # Upsert current status
            self.db.table("current_status").upsert({
                "person_id": person_id,
                "status": "in",
                "checkin_at": "now()",
                "last_seen": "now()",
                "updated_at": "now()",
            }).execute()
        except Exception as exc:
            print(f"[attendance] checkin DB error: {exc}")

    def _db_checkout(self, person_id: str):
        try:
            self.db.table("presence_log").insert({
                "person_id": person_id,
                "event_type": "checkout",
            }).execute()
            self.db.table("current_status").update({
                "status": "out",
                "updated_at": "now()",
            }).eq("person_id", person_id).execute()
        except Exception as exc:
            print(f"[attendance] checkout DB error: {exc}")

    def _insert_unknown(self, face_b64: str) -> Optional[str]:
        try:
            res = self.db.table("unknown_faces").insert({"face_image": face_b64}).execute()
            return res.data[0]["id"] if res.data else None
        except Exception as exc:
            print(f"[attendance] unknown face DB error: {exc}")
            return None


def _iso_to_epoch(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        from datetime import datetime, timezone
        ts = ts[:19].replace("T", " ")
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0
