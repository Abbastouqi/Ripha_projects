"""
Lightweight IoU-based face tracker.
Assigns stable track IDs across frames so we don't re-query FAISS
for a face we already identified.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class Track:
    track_id: int
    bbox: np.ndarray           # [x1, y1, x2, y2]
    embedding: Optional[np.ndarray] = None
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    confidence: float = 0.0
    frames_alive: int = 1
    frames_since_update: int = 0
    last_logged_at: float = 0.0   # epoch seconds


class FaceTracker:
    def __init__(self, max_age: int = 20, iou_threshold: float = 0.30):
        self.max_age = max_age
        self.iou_threshold = iou_threshold
        self.tracks: list[Track] = []
        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, faces: list) -> list[Track]:
        """
        faces: list of InsightFace Face objects from FaceEngine.process()
        Returns all currently active tracks (updated + unmatched old ones).
        """
        detections = [(f.bbox.astype(int), f.normed_embedding, f.det_score) for f in faces]

        matched_track_ids: set[int] = set()

        for bbox, embedding, score in detections:
            best_iou, best_track = 0.0, None
            for track in self.tracks:
                iou = self._iou(bbox, track.bbox)
                if iou > best_iou:
                    best_iou, best_track = iou, track

            if best_iou >= self.iou_threshold and best_track is not None:
                best_track.bbox = bbox
                best_track.frames_since_update = 0
                best_track.frames_alive += 1
                matched_track_ids.add(best_track.track_id)
                # Update embedding for unidentified tracks each frame
                if best_track.person_id is None:
                    best_track.embedding = embedding
            else:
                # New face — create a new track with this embedding
                track = Track(
                    track_id=self._next_id,
                    bbox=bbox,
                    embedding=embedding,
                    confidence=score,
                )
                self._next_id += 1
                self.tracks.append(track)
                matched_track_ids.add(track.track_id)

        # Age out unmatched tracks
        for track in self.tracks:
            if track.track_id not in matched_track_ids:
                track.frames_since_update += 1

        self.tracks = [t for t in self.tracks if t.frames_since_update < self.max_age]
        return self.tracks

    def needs_match(self, track: Track) -> bool:
        """True when this track still needs a FAISS lookup."""
        return track.person_id is None and track.embedding is not None

    # ------------------------------------------------------------------
    @staticmethod
    def _iou(a: np.ndarray, b: np.ndarray) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix = max(0, min(ax2, bx2) - max(ax1, bx1))
        iy = max(0, min(ay2, by2) - max(ay1, by1))
        inter = ix * iy
        union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / union if union > 0 else 0.0
