from backend.models.ollama_client import generate, WORKFLOW_MODEL

SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Answer questions clearly and concisely. "
    "Be friendly, accurate, and helpful. If you don't know something, say so."
)


def _build_context(history: list[dict]) -> str:
    lines = []
    for msg in history[-6:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def run(user_text: str, history: list[dict] | None = None) -> dict:
    history = history or []
    context = _build_context(history)
    prompt = f"{context}\nUser: {user_text}\nAssistant:" if context else f"User: {user_text}\nAssistant:"
    response = generate(WORKFLOW_MODEL, prompt, SYSTEM_PROMPT)
    return {
        "response": response.strip(),
        "workflow": "general",
        "sources": [],
    }
