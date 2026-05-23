# Phase 0 Implementation — Changelog

This file documents the additions made to the existing medical-ai-system to
turn it into the broader four-domain Local AI Platform described in
`../Local_AI_Platform_Guide.docx` and `../Phase0_Quick_Start.docx`.

Nothing from your existing codebase was removed. All additions are
backward-compatible — the appointment workflow, intent parser, sessions,
RAG, file upload, and React frontend keep working as before.

---

## What was added

### 1. OpenAI-compatible API endpoint  (`backend/routers/openai_compat.py`)

Exposes a standard OpenAI shape on top of your existing chat platform:

- `GET  /v1/models` — lists exposed model names.
- `POST /v1/chat/completions` — same wire shape as OpenAI, supports streaming.

Why this matters: any tool that speaks OpenAI (OpenWebUI, LibreChat, Cursor,
LangChain's `ChatOpenAI`, raw curl, custom Python clients) can now use this
backend as a model — and behind the scenes each request is routed through the
same intent classifier + workflow dispatch as `/api/chat`.

**Exposed model names:**

| Model name           | Behavior                                              |
| -------------------- | ----------------------------------------------------- |
| `local-ai-auto`      | Auto-route via the existing intent router (default).  |
| `local-ai-general`   | Force `chat_workflow`.                                |
| `local-ai-medical`   | Force `medical_qa_workflow`.                          |
| `local-ai-hr`        | Force `hr_workflow`.                                  |
| `local-ai-university`| Force the new `university_workflow`.                  |

**Auth:** set `OPENAI_COMPAT_API_KEY` in `.env`. If unset, the endpoint is
open (dev only). Clients send `Authorization: Bearer <key>`.

**Quick test:**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "model": "local-ai-auto",
        "messages": [{"role":"user","content":"What is the company sick leave policy?"}]
      }'
```

Streaming works with `"stream": true` (SSE).

### 2. University workflow  (`backend/workflows/university_workflow.py`)

Mirrors the existing `hr_workflow.py` pattern:

- Searches a dedicated Qdrant collection `university_knowledge` for grounding.
- Falls back to the base model with a university-specific system prompt when
  no documents are ingested.
- Exposes `ingest_university_document(text, filename)` for ingestion.

Wired into:

- `backend/router.py` — added `university` to both the LLM router prompt and
  the keyword route list (course, syllabus, registrar, GPA, scholarship,
  financial aid, faculty, etc.).
- `backend/main.py` — `_run_workflow` dispatches `university` queries to it.
- `backend/main.py` — new endpoint `POST /api/university/policy` to upload
  handbooks, catalogs, syllabi, academic calendars.

### 3. OCR fallback in PDF parser  (`backend/file_processing/pdf_parser.py`)

Same function signature — `extract_text(file_path)` — but now:

1. Tries PyMuPDF native extraction first (fast, perfect for born-digital PDFs).
2. For any page with fewer than 40 chars of native text, renders the page
   image and runs Tesseract OCR.
3. If `pytesseract` or the Tesseract binary is missing, prints a one-line
   warning and returns whatever native extraction produced.

Env vars:

- `TESSERACT_CMD` — full path to `tesseract.exe` (Windows convenience).
- `TESSERACT_LANG` — defaults to `eng`. Use `eng+urd` for Urdu+English etc.

### 4. OpenWebUI in `docker-compose.yml`

New service `openwebui` on port **3001**, pointed at the backend's `/v1`
endpoint. Visit http://localhost:3001 after `docker compose up`. First login
asks you to create an admin account inside OpenWebUI; that's separate from
the React frontend admin.

You can keep using the React UI on :3000 — both surfaces talk to the same
backend.

### 5. Eval harness  (`eval/test_cases.json` + `eval/run_eval.py`)

A small reproducible test suite covering all five workflows (general,
hr_tasks, medical_qa, medical_appointment, university). Each case has:

- `query` — the user message.
- `expected_workflow` — what the router should pick.
- `expect_substrings` (optional) — any one must appear in the answer.

Run it against a live backend:

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
python eval\run_eval.py                       # hits /api/chat
python eval\run_eval.py --use-openai-compat   # hits /v1/chat/completions
```

Output is a per-case table plus a summary with routing accuracy, substring
accuracy, and average latency. Exit code 1 if routing accuracy falls below
`EVAL_ROUTING_THRESHOLD` (default 0.8) — convenient for CI.

### 6. Setup script  (`setup.ps1`)

Added a new step 6 that installs Tesseract via winget
(`UB-Mannheim.TesseractOCR`) and refreshes PATH. The Tesseract binary is what
the new OCR fallback needs at runtime — the Python `pytesseract` package is
already pulled in via the updated `backend/requirements.txt`.

### 7. Python dependencies  (`backend/requirements.txt`)

Added two lines:

```
pytesseract>=0.3.10
pillow>=10.0.0
```

---

## How to use what's new

### Add a university workflow corpus

```powershell
# Upload a university handbook, catalog, calendar, or syllabus
curl.exe -X POST http://localhost:8000/api/university/policy `
  -F "file=@C:\path\to\handbook.pdf"
```

Then ask university questions and they get grounded:

```powershell
curl.exe -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{ \"text\": \"When is the last day to drop a course?\" }'
```

### Use OpenWebUI

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
docker compose up -d openwebui   # backend + ollama must already be up
```

Open http://localhost:3001, create the admin user, and the five
`local-ai-*` models will appear in the model dropdown. `local-ai-auto` is
the default — it routes each message through the intent classifier the same
way your existing chat does.

### Run the eval

```powershell
# With the backend running on :8000
python eval\run_eval.py
```

Track the routing accuracy number over time. Whenever you change a prompt
or pull a different model, re-run this — it's the cheapest early-warning
signal you have against regressions.

### Use the OpenAI-compatible endpoint from Python

```python
# Drop-in for openai >= 1.0 clients
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dev",   # any value works unless OPENAI_COMPAT_API_KEY is set
)

resp = client.chat.completions.create(
    model="local-ai-auto",
    messages=[{"role": "user", "content": "Summarize our parental leave policy."}],
)
print(resp.choices[0].message.content)
# The actual workflow chosen by the router is on resp.x_workflow (non-OpenAI extra)
```

### Stream responses

```python
stream = client.chat.completions.create(
    model="local-ai-auto",
    messages=[{"role": "user", "content": "Hi"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

---

## What still needs your hands

These are local-machine actions only you can do:

1. **Install Docker Desktop** (if not already) — `setup.ps1` step 3.
2. **Install Tesseract** — `setup.ps1` step 6, or manually from
   <https://github.com/UB-Mannheim/tesseract/wiki>.
3. **`pip install -r backend/requirements.txt`** inside the existing venv to
   pick up `pytesseract` and `pillow`.
4. **Pull models** (already done if you've run setup.ps1):
   `ollama pull gemma3:4b phi4-mini nomic-embed-text`.
5. **Restart the backend** so the new routes (`/v1/...`, `/api/university/...`)
   register.
6. **Run the eval** to capture a baseline:
   `python eval\run_eval.py > eval\baseline.txt`.

---

## Suggested next steps (after this lands)

In priority order:

1. **Ingest real domain corpora.** The HR and university workflows are only as
   good as the documents you give them. Start with 5-20 docs per workflow.
2. **Re-run the eval** and keep a baseline file in `eval/baseline.txt`.
3. **Per-workflow eval sets.** Expand `test_cases.json` to ~30 questions
   per workflow, including hard cases (acronyms, multi-part questions,
   negative tests).
4. **Wire OpenWebUI auth to your auth service.** Optional — only useful if
   you want a single sign-on across React UI and OpenWebUI.
5. **Switch to vLLM once you have an NVIDIA GPU.** The model gateway pattern
   in `routers/openai_compat.py` is already in place; you'd just point
   `OLLAMA_HOST` at the vLLM endpoint (it's OpenAI-compatible).
6. **Reranker.** When retrieval accuracy plateaus, add `bge-reranker-v2-m3`
   via sentence-transformers between Qdrant search and prompt assembly.
   Biggest accuracy lever in the RAG layer.
7. **Per-tenant Qdrant namespaces** if you ever go multi-tenant. Right now
   collections are per-domain (medical_knowledge, hr_knowledge,
   university_knowledge), not per-tenant.

---

## File map of the change

```
backend/
  main.py                                  # imports + dispatch + new endpoint
  router.py                                # added 'university' route + keywords
  requirements.txt                         # +pytesseract, +pillow
  routers/
    openai_compat.py                       # NEW
  workflows/
    university_workflow.py                 # NEW
  file_processing/
    pdf_parser.py                          # rewritten with OCR fallback
docker-compose.yml                         # +openwebui service on :3001
setup.ps1                                  # +step 6: install Tesseract
eval/
  test_cases.json                          # NEW
  run_eval.py                              # NEW
PHASE0_CHANGES.md                          # this file
```
