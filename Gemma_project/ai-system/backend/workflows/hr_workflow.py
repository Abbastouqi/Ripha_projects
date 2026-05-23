from backend.models.ollama_client import generate, WORKFLOW_MODEL
from backend.rag.embeddings import get_client

COLLECTION_NAME = "hr_knowledge"

SYSTEM_PROMPT = (
    "You are an HR AI assistant. Help employees with leave requests, payroll queries, "
    "company policies, benefits, attendance, and other HR-related matters. "
    "Be professional, empathetic, and accurate. Reference specific policies when available. "
    "If you don't have the specific policy, provide general best-practice guidance."
)


def _search_hr_knowledge(query: str, top_k: int = 5) -> list[str]:
    try:
        from backend.models.ollama_client import embed
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
        return [r.payload.get("text", "") for r in results if r.score > 0.4]
    except Exception:
        return []


def _build_context(history: list[dict]) -> str:
    lines = []
    for msg in history[-4:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def run(user_text: str, history: list[dict] | None = None) -> dict:
    history = history or []
    chunks = _search_hr_knowledge(user_text)
    sources = chunks[:3]
    conv_context = _build_context(history)

    if chunks:
        hr_context = "\n\n".join(chunks)
        prompt = (
            f"HR Policy context:\n{hr_context}\n\n"
            f"{conv_context}\nEmployee: {user_text}\nHR Assistant:"
        ).strip()
    else:
        prompt = (
            f"{conv_context}\nEmployee: {user_text}\nHR Assistant:"
        ).strip()

    response = generate(WORKFLOW_MODEL, prompt, SYSTEM_PROMPT)
    return {
        "response": response.strip(),
        "workflow": "hr_tasks",
        "sources": sources,
    }
