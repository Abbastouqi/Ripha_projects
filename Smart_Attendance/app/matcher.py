"""
In-memory FAISS index for sub-millisecond cosine similarity search.
Enrollment embeddings are loaded from Supabase pgvector on startup
and added live when new people are enrolled.
"""
from __future__ import annotations

import numpy as np
import faiss
from typing import Optional

from .config import EMBEDDING_DIM, SIMILARITY_THRESHOLD


class FaceMatcher:
    def __init__(self, threshold: float = SIMILARITY_THRESHOLD):
        self.threshold = threshold
        # IndexFlatIP = exact inner product; equal to cosine for L2-normalized vectors
        self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._person_ids: list[str] = []
        self._person_names: list[str] = []

    # ------------------------------------------------------------------
    def load(self, rows: list[dict]) -> None:
        """
        Bulk-load from Supabase rows.
        Each row must have: person_id (str), name (str), embedding (list|str).
        """
        if not rows:
            return
        persons, embeddings = [], []
        for row in rows:
            emb = _parse_vector(row["embedding"])
            if emb is None or len(emb) != EMBEDDING_DIM:
                continue
            persons.append((row["person_id"], row["name"]))
            embeddings.append(emb)

        if not embeddings:
            return

        mat = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(mat)
        self.index.add(mat)
        for pid, name in persons:
            self._person_ids.append(pid)
            self._person_names.append(name)

    def add(self, person_id: str, name: str, embedding: np.ndarray) -> None:
        """Add a single enrollment embedding (called after enroll endpoint)."""
        vec = embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(vec)
        self.index.add(vec)
        self._person_ids.append(person_id)
        self._person_names.append(name)

    # ------------------------------------------------------------------
    def search(
        self, embedding: np.ndarray
    ) -> tuple[Optional[str], Optional[str], float]:
        """
        Returns (person_id, name, similarity) if above threshold,
        else (None, None, best_score).
        """
        if self.index.ntotal == 0:
            return None, None, 0.0

        query = embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, k=1)

        score = float(scores[0][0])
        idx = int(indices[0][0])

        if score >= self.threshold and idx >= 0:
            return self._person_ids[idx], self._person_names[idx], score
        return None, None, score

    @property
    def enrolled_count(self) -> int:
        return self.index.ntotal


# ------------------------------------------------------------------
def _parse_vector(raw) -> Optional[np.ndarray]:
    """pgvector comes back as a Python list or string '[0.1,0.2,...]'."""
    try:
        if isinstance(raw, str):
            raw = raw.strip("[]").split(",")
        return np.array(raw, dtype=np.float32)
    except Exception:
        return None
