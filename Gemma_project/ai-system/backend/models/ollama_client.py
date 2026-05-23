import os
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
WORKFLOW_MODEL = os.getenv("OLLAMA_WORKFLOW_MODEL", "mistral:7b")
INTENT_MODEL = os.getenv("OLLAMA_INTENT_MODEL", "phi4-mini")
AGENT_MODEL = os.getenv("OLLAMA_AGENT_MODEL", "phi4-mini")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
SMALL_FALLBACK_MODEL = os.getenv("OLLAMA_SMALL_FALLBACK_MODEL", "gemma3:4b")

TIMEOUT = 300.0


def health_check() -> dict:
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        models = [m["name"] for m in data.get("models", [])]
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# gemma3:4b is the small fast fallback; prefer it before heavier models
FALLBACK_ORDER = ["gemma3", "phi4", "phi3", "mistral", "llama3", "qwen"]


def _loaded_models() -> list[str]:
    result = health_check()
    if result["status"] == "ok":
        return result.get("models", [])
    return []


def _resolve_model(preferred: str) -> str:
    """Return preferred model if available, else best installed fallback."""
    loaded = _loaded_models()
    preferred_base = preferred.split(":")[0]
    for m in loaded:
        if m.startswith(preferred_base):
            return m
    for fallback in FALLBACK_ORDER:
        for m in loaded:
            if m.startswith(fallback):
                print(f"[ollama] '{preferred}' not ready, falling back to '{m}'")
                return m
    return preferred


def generate(model: str, prompt: str, system_prompt: str = "") -> str:
    resolved = _resolve_model(model)
    payload = {
        "model": resolved,
        "prompt": prompt,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt
    try:
        r = httpx.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("response", "")
    except Exception as primary_err:
        # Primary model failed — retry once with the small gemma3:4b fallback
        if resolved != SMALL_FALLBACK_MODEL:
            print(f"[ollama] '{resolved}' failed ({primary_err}), retrying with '{SMALL_FALLBACK_MODEL}'")
            payload["model"] = SMALL_FALLBACK_MODEL
            r2 = httpx.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
            r2.raise_for_status()
            return r2.json().get("response", "")
        raise


def generate_json(model: str, prompt: str, system_prompt: str = "", retries: int = 3) -> dict:
    strict_system = (
        system_prompt
        + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
        "No markdown, no code fences, no explanation text. Start your response with { and end with }."
    )
    for attempt in range(retries):
        try:
            raw = generate(model, prompt, strict_system)
            raw = raw.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            # Find first { and last }
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                raw = raw[start : end + 1]
            return json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            if attempt == retries - 1:
                raise ValueError(f"Failed to get valid JSON after {retries} attempts: {e}")
            time.sleep(1)
    return {}


def embed(text: str) -> list[float]:
    r = httpx.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json().get("embedding", [])


def pull_model(model_name: str) -> None:
    print(f"Pulling model: {model_name} (this may take a while on first run)...")
    with httpx.stream(
        "POST",
        f"{OLLAMA_HOST}/api/pull",
        json={"name": model_name},
        timeout=600.0,
    ) as r:
        for line in r.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    status = data.get("status", "")
                    if "pulling" in status or "success" in status:
                        print(f"  {status}")
                except Exception:
                    pass


def ensure_models() -> None:
    loaded = _loaded_models()
    needed = [WORKFLOW_MODEL, INTENT_MODEL, EMBED_MODEL]
    # Deduplicate
    needed = list(dict.fromkeys(needed))
    for model in needed:
        base = model.split(":")[0]
        already = any(m.startswith(base) for m in loaded)
        if not already:
            pull_model(model)
        else:
            print(f"Model already loaded: {model}")
