"""
OpenAI-compatible API endpoint.

Exposes /v1/models and /v1/chat/completions so any OpenAI-compatible client
(OpenWebUI, LibreChat, langchain ChatOpenAI, raw curl, custom apps) can use
this backend as a model. The endpoint routes each request through the same
intent router + workflow dispatch used by /api/chat — so the OpenAI client
gets the full multi-workflow platform (HR, medical_qa, university, etc.)
behind a single OpenAI-shaped model name.

Streaming is supported via Server-Sent Events; non-streaming returns the
classic OpenAI response shape.

Auth: a single shared API key from env (OPENAI_COMPAT_API_KEY). If unset,
the endpoint is open (dev only).
"""

import os
import json
import time
import uuid
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.router import route_query
from backend.intent_parser import parse_intent
from backend.workflows import (
    chat_workflow,
    medical_qa_workflow,
    hr_workflow,
    document_workflow,
)
from backend.workflows.appointment_workflow import run_workflow as run_appointment_workflow

# University workflow is added in this same change-set. Import is wrapped so
# the module still loads if a downgrade removes it.
try:
    from backend.workflows import university_workflow
except Exception:
    university_workflow = None


router = APIRouter(prefix="/v1", tags=["openai-compat"])

API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "")  # empty = no auth (dev)

# Stable identifiers exposed to OpenAI clients.
MODEL_AUTO = "local-ai-auto"        # auto-routed across all workflows
MODEL_GENERAL = "local-ai-general"  # forced to chat_workflow
MODEL_MEDICAL = "local-ai-medical"  # forced to medical_qa
MODEL_HR = "local-ai-hr"            # forced to hr_tasks
MODEL_UNIVERSITY = "local-ai-university"  # forced to university workflow

EXPOSED_MODELS = [MODEL_AUTO, MODEL_GENERAL, MODEL_MEDICAL, MODEL_HR, MODEL_UNIVERSITY]


# ---------------------------------------------------------------------------
# Schemas (subset of the OpenAI chat-completions schema)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None  # accepted but currently ignored
    max_tokens: Optional[int] = None     # accepted but currently ignored
    user: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_auth(authorization: Optional[str]) -> None:
    if not API_KEY:
        return  # dev mode, no auth
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _pick_workflow(model: str, user_text: str) -> str:
    """Map exposed model name + last user message to an internal workflow."""
    forced = {
        MODEL_GENERAL: "general",
        MODEL_MEDICAL: "medical_qa",
        MODEL_HR: "hr_tasks",
        MODEL_UNIVERSITY: "university",
    }
    if model in forced:
        return forced[model]
    # MODEL_AUTO or unknown — let the router decide
    return route_query(user_text, has_active_document=False)


def _history_from_messages(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    """Split the OpenAI messages list into (last_user_text, prior_history)."""
    if not messages:
        return "", []
    # Find last user message
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        return "", [{"role": m.role, "content": m.content} for m in messages]
    last_user_text = messages[last_user_idx].content
    history = [{"role": m.role, "content": m.content} for m in messages[:last_user_idx]]
    # Drop system messages we don't own — let each workflow inject its own.
    history = [h for h in history if h["role"] in ("user", "assistant")]
    return last_user_text, history


def _run_for_workflow(workflow: str, user_text: str, history: list[dict]) -> dict:
    if workflow == "medical_qa":
        return medical_qa_workflow.run(user_text, history)
    if workflow == "hr_tasks":
        return hr_workflow.run(user_text, history)
    if workflow == "document_chat":
        # Document chat without an active doc_id falls back to general
        return chat_workflow.run(user_text, history)
    if workflow == "medical_appointment":
        intent = parse_intent(user_text)
        state = run_appointment_workflow(intent, "")
        slots = state.get("available_slots", [])
        booking = state.get("booking", {})
        notice = state.get("no_specialist_notice", "")
        if state.get("status") == "awaiting_input" and slots:
            slot_lines = "\n".join(
                f"  {i+1}. {s.get('doctor_name','?')} ({s.get('specialty','?')}) — "
                f"{s.get('date','?')} at {s.get('time','?')}"
                for i, s in enumerate(slots[:5])
            )
            text = (
                (notice + "\n\n" if notice else "")
                + f"I found {len(slots)} available slot{'s' if len(slots)!=1 else ''}:\n"
                + slot_lines
                + "\n\n(Pick a number to book, or visit the web UI to confirm.)"
            )
            return {"response": text, "workflow": "medical_appointment", "sources": []}
        return {
            "response": state.get("ui_output", "No appointment could be processed."),
            "workflow": "medical_appointment",
            "sources": [],
        }
    if workflow == "university" and university_workflow is not None:
        return university_workflow.run(user_text, history)
    # Default
    return chat_workflow.run(user_text, history)


def _completion_payload(model: str, content: str, workflow: str, sources: list) -> dict:
    """Build the non-streaming OpenAI-shaped response object."""
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    return {
        "id": cid,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        # Non-standard fields (OpenAI clients ignore unknown fields).
        "x_workflow": workflow,
        "x_sources": sources,
    }


def _sse(line: dict) -> str:
    return "data: " + json.dumps(line) + "\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(authorization: Optional[str] = Header(default=None)):
    _check_auth(authorization)
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": now, "owned_by": "local-ai-platform"}
            for m in EXPOSED_MODELS
        ],
    }


@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionsRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    _check_auth(authorization)

    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is empty")

    user_text, history = _history_from_messages(req.messages)
    if not user_text.strip():
        raise HTTPException(status_code=400, detail="No user message found")

    workflow = _pick_workflow(req.model, user_text)

    # Run the workflow off the event loop (each backend workflow is sync).
    result = await asyncio.to_thread(_run_for_workflow, workflow, user_text, history)
    answer = result.get("response", "")
    sources = result.get("sources", []) or []

    if req.stream:
        # Emit the answer as a single token chunk + final stop. This is faithful
        # to the OpenAI shape; we don't currently stream Ollama tokens through,
        # though it would be a drop-in change later.
        async def gen():
            cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            created = int(time.time())
            head = {
                "id": cid, "object": "chat.completion.chunk", "created": created,
                "model": req.model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
            yield _sse(head)
            body = {
                "id": cid, "object": "chat.completion.chunk", "created": created,
                "model": req.model,
                "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}],
            }
            yield _sse(body)
            tail = {
                "id": cid, "object": "chat.completion.chunk", "created": created,
                "model": req.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "x_workflow": workflow, "x_sources": sources,
            }
            yield _sse(tail)
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return _completion_payload(req.model, answer, workflow, sources)
