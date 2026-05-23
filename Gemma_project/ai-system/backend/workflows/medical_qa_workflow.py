from backend.models.ollama_client import generate, WORKFLOW_MODEL
from backend.rag.embeddings import search

SYSTEM_PROMPT = (
    "You are a medical AI assistant. Answer medical questions based on the provided context "
    "when available. Be accurate and clear. Always recommend the user consult a qualified "
    "healthcare professional for personal medical decisions."
)


def _build_context(history: list[dict]) -> str:
    lines = []
    for msg in history[-4:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def run(user_text: str, history: list[dict] | None = None) -> dict:
    history = history or []
    sources: list[str] = []

    try:
        rag_results = search(user_text, top_k=5)
        context_chunks = [r["text"] for r in rag_results if r.get("score", 0) > 0.4]
        sources = context_chunks[:3]
    except Exception:
        context_chunks = []

    rag_context = "\n\n".join(context_chunks) if context_chunks else ""
    conv_context = _build_context(history)

    if rag_context:
        prompt = (
            f"Medical knowledge context:\n{rag_context}\n\n"
            f"{conv_context}\nUser: {user_text}\nAssistant:"
        ).strip()
    else:
        prompt = (
            f"{conv_context}\nUser: {user_text}\nAssistant:"
        ).strip()

    response = generate(WORKFLOW_MODEL, prompt, SYSTEM_PROMPT)
    return {
        "response": response.strip(),
        "workflow": "medical_qa",
        "sources": sources,
    }
