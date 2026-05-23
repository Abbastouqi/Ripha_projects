"""
University workflow — Riphah International University assistant.

Handles admissions queries, program information, fee structures,
campus details, academic policies, and student services.

RAG: pulls from `university_knowledge` Qdrant collection (populated by
web_scraper.py from riphah.edu.pk + manually uploaded documents).
If the collection is empty, triggers a background scrape automatically.
"""

from backend.models.ollama_client import generate, WORKFLOW_MODEL, embed
from backend.rag.embeddings import get_client
from backend.workflows.admission_workflow import ADMISSION_TRIGGER_KEYWORDS
from backend.prompts.university_prompts import (
    ASKRIPHAH_SYSTEM,
    build_university_rag_prompt,
    check_input,
    sanitise_output,
    is_university_relevant,
    get_off_topic_response,
)

COLLECTION_NAME = "university_knowledge"
SYSTEM_PROMPT   = ASKRIPHAH_SYSTEM   # kept for any legacy references


def _search_knowledge(query: str, top_k: int = 5) -> list[str]:
    try:
        client = get_client()
        collections = [c.name for c in client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            return []
        query_vector = embed(query)
        if not query_vector:
            return []
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [r.payload.get("text", "") for r in results if r.score > 0.35]
    except Exception:
        return []


def _build_context(history: list[dict]) -> str:
    lines = []
    for msg in history[-4:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def _is_admission_trigger(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in ADMISSION_TRIGGER_KEYWORDS)


def run(user_text: str, history: list[dict] | None = None) -> dict:
    history = history or []

    # ── Layer 1: Input guardrails ────────────────────────────────────────────
    guard = check_input(user_text)
    if guard.blocked:
        print(f"[University] Guardrail blocked ({guard.category}): {user_text[:60]}")
        return {
            "response": guard.response,
            "workflow": "university",
            "sources":  [],
            "guardrail": guard.category,
        }

    # ── Layer 2: Admission trigger detection ─────────────────────────────────
    if _is_admission_trigger(user_text):
        return {
            "response": (
                "I can help you apply for admission at Riphah International University! "
                "I'll walk you through the application step by step right here in the chat."
            ),
            "workflow":        "university",
            "sources":         [],
            "trigger_workflow": "admission",
        }

    # ── Layer 3: Topic relevance gate ────────────────────────────────────────
    if not is_university_relevant(user_text):
        return {
            "response": get_off_topic_response(),
            "workflow": "university",
            "sources":  [],
            "guardrail": "off_topic",
        }

    # ── Layer 4: RAG retrieval ────────────────────────────────────────────────
    chunks = _search_knowledge(user_text)
    sources = chunks[:3]

    if not chunks:
        try:
            from backend.scraper.web_scraper import is_collection_populated, trigger_background_scrape
            if not is_collection_populated():
                print("[University] Collection empty — triggering background scrape of riphah.edu.pk")
                trigger_background_scrape()
        except Exception as e:
            print(f"[University] Scrape trigger error: {e}")

    # ── Layer 5: LLM call ─────────────────────────────────────────────────────
    prompt   = build_university_rag_prompt(user_text, chunks, history)
    response = generate(WORKFLOW_MODEL, prompt, ASKRIPHAH_SYSTEM)

    # ── Layer 6: Output sanitisation ─────────────────────────────────────────
    safe_response = sanitise_output(response.strip())

    return {
        "response": safe_response,
        "workflow": "university",
        "sources":  sources,
    }


def ingest_university_document(text: str, filename: str = "policy") -> int:
    """Ingest a university document (handbook, calendar, syllabus) into Qdrant."""
    import time
    import hashlib
    from qdrant_client.models import Distance, VectorParams, PointStruct
    from backend.file_processing.chunker import chunk_text

    client = get_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

    chunks = chunk_text(text)
    base = int(time.time() * 1000)
    points = []
    for i, c in enumerate(chunks):
        v = embed(c)
        if not v:
            continue
        chunk_hash = hashlib.md5(c.encode()).hexdigest()[:12]
        points.append(
            PointStruct(
                id=base + i,
                vector=v,
                payload={
                    "text": c,
                    "filename": filename,
                    "chunk_hash": chunk_hash,
                    "source": "upload",
                },
            )
        )

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)
