import os
import re
from collections import defaultdict
from backend.rag.embeddings import search as vector_search

STOP_WORDS = {
    "i", "me", "my", "the", "a", "an", "and", "or", "but", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "is", "it", "this", "that",
    "was", "are", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "shall",
    "need", "want", "please", "can", "you", "we", "they", "he", "she",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def _bm25_score(query_tokens: list[str], doc_text: str, avg_dl: float = 50.0) -> float:
    k1, b = 1.5, 0.75
    doc_tokens = _tokenize(doc_text)
    dl = len(doc_tokens)
    tf_map: dict[str, int] = defaultdict(int)
    for t in doc_tokens:
        tf_map[t] += 1

    score = 0.0
    for token in set(query_tokens):
        tf = tf_map.get(token, 0)
        if tf == 0:
            continue
        idf = 1.0  # simplified IDF (single-collection BM25)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / avg_dl)
        score += idf * (numerator / denominator)
    return score


def _rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    query_tokens = _tokenize(query)
    for doc in candidates:
        bm25 = _bm25_score(query_tokens, doc["text"])
        semantic = doc.get("score", 0.0)
        doc["hybrid_score"] = 0.6 * semantic + 0.4 * (bm25 / 10.0)
    candidates.sort(key=lambda d: d["hybrid_score"], reverse=True)
    return candidates[:top_k]


def retrieve(query: str, top_k: int = 5, category: str | None = None) -> str:
    raw_results = vector_search(query, top_k=min(top_k * 2, 20), category=category)
    if not raw_results:
        return ""
    reranked = _rerank(query, raw_results, top_k=top_k)
    context_parts = [f"[{i+1}] {doc['text']}" for i, doc in enumerate(reranked)]
    return "\n\n".join(context_parts)


def retrieve_for_specialty(specialty: str) -> str:
    query = f"appointment booking {specialty} doctor specialist conditions symptoms"
    return retrieve(query, top_k=5)


def retrieve_policies(query: str = "appointment booking policy") -> str:
    return retrieve(query, top_k=3, category="policy")
