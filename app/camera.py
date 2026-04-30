"""
Camera capture loop — runs in a background daemon thread.

Pipeline per processed frame:
  1. Capture frame
  2. Skip (frame_count % FRAME_SKIP != 0) → push raw frame for streaming
  3. FaceEngine.process() → detected faces with embeddings
  4. FaceTracker.update() → stable track IDs
  5. For unidentified tracks → FaceMatcher.search() → person or unknown
  6. Confirmed person → AttendanceService.log_attendance() (async, non-blocking)
  7. Unknown face → AttendanceService.log_unknown() (async, non-blocking)
  8. Annotate frame and push to streaming queue
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .face_engine import FaceEngine
from .tracker import FaceTracker
from .matcher import FaceMatcher
from .attendance import AttendanceService
from .config import CAMERA_ID, FRAME_SKIP


class CameraProcessor:
    def __init__(
        self,
        engine: FaceEngine,
        tracker: FaceTracker,
        matcher: FaceMatcher,
        attendance: AttendanceService,
        camera_id: int = CAMERA_ID,
        frame_skip: int = FRAME_SKIP,
    ):
        self.engine = engine
        self.tracker = tracker
        self.matcher = matcher
        self.attendance = attendance
        self.camera_id = camera_id
        self.frame_skip = frame_skip

        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=3)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._frame_count = 0
        self._unknown_cooldown: dict[int, float] = {}  # track_id → last logged time

    # ------------------------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._running = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def latest_frame(self) -> Optional[np.ndarray]:
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    def _run(self) -> None:
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        if not cap.isOpened():
            print(f"[camera] ERROR: Cannot open camera {self.camera_id}")
            return

        print(f"[camera] Started on device {self.camera_id}, skip={self.frame_skip}")

        while self._running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            self._frame_count += 1

            if self._frame_count % self.frame_skip != 0:
                self._push_frame(frame)
                continue

            annotated = self._process(frame)
            self._push_frame(annotated)

        cap.release()
        print("[camera] Stopped.")

    # ------------------------------------------------------------------
    def _process(self, frame: np.ndarray) -> np.ndarray:
        try:
            faces = self.engine.process(frame)
        except Exception as exc:
            print(f"[camera] Engine error: {exc}")
            return frame

        tracks = self.tracker.update(faces)
        annotated = frame.copy()

        for track in tracks:
            if self.tracker.needs_match(track):
                person_id, name, score = self.matcher.search(track.embedding)
                track.person_id = person_id
                track.person_name = name
                track.confidence = score

                if person_id and self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self.attendance.on_face_seen(person_id, name, score),
                        self._loop,
                    )
                elif self._loop:
                    # Log unknown face at most once per 60s per track
                    now = time.time()
                    if now - self._unknown_cooldown.get(track.track_id, 0) > 60:
                        self._unknown_cooldown[track.track_id] = now
                        x1, y1, x2, y2 = track.bbox
                        crop = frame[max(0, y1):y2, max(0, x1):x2]
                        if crop.size > 0:
                            asyncio.run_coroutine_threadsafe(
                                self.attendance.log_unknown(crop),
                                self._loop,
                            )

            # Annotate
            x1, y1, x2, y2 = track.bbox
            color = (0, 220, 0) if track.person_id else (0, 0, 220)
            label = f"{track.person_name or 'Unknown'} {track.confidence:.2f}"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                annotated, label, (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2,
            )

        return annotated

    def _push_frame(self, frame: np.ndarray) -> None:
        """Drop oldest frame if consumer is slow."""
        if self._frame_queue.full():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            pass
