# Medical AI Workflow Automation System

A fully local, offline-capable medical appointment booking system powered by LLMs running on your own machine. No cloud APIs. No subscriptions. Everything runs on localhost.

---

## What This System Does

A patient types a natural language request like:

> "I have chest pain and need to see a cardiologist urgently"

The system automatically:
1. Understands the intent (specialty = cardiology, urgency = urgent)
2. Looks up the patient in the database
3. Fetches available doctor slots
4. Presents options to the patient
5. Confirms the booking and writes it to PostgreSQL
6. Sends a simulated SMS/email notification
7. Updates the EHR summary

All steps run as a LangGraph workflow — a stateful AI pipeline where each node is an intelligent agent.

---

## Architecture Overview

```
Browser (React)
      |
      | HTTP + WebSocket
      v
FastAPI Backend (Python)
      |
      |-- Intent Parser --> Ollama (phi4-mini)
      |-- LangGraph Workflow
      |       |-- auth_agent     --> PostgreSQL
      |       |-- schedule_agent --> PostgreSQL
      |       |-- ehr_agent      --> PostgreSQL
      |       |-- notify_agent   --> PostgreSQL (logs)
      |       |-- ui_agent       --> formats output
      |
      |-- RAG Retriever --> Qdrant (vector search)
      |                --> Ollama (nomic-embed-text)
      |
      |-- Workflow LLM  --> Ollama (gemma3:4b)

Infrastructure (Docker)
  - PostgreSQL 16 + pgvector  (patient data, appointments)
  - Qdrant                    (medical knowledge vectors)

Local AI (Ollama)
  - gemma3:4b        (workflow generation)
  - phi4-mini        (intent parsing, agents)
  - nomic-embed-text (RAG embeddings)
```

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS | Patient-facing UI |
| Backend | FastAPI (Python 3.14) | REST API + WebSocket |
| Orchestration | LangGraph 1.2 | Stateful AI workflow DAG |
| LLM Inference | Ollama (CPU mode) | Local model serving |
| Models | gemma3:4b, phi4-mini | Workflow + intent AI |
| Embeddings | nomic-embed-text | RAG vector embeddings |
| Vector DB | Qdrant | Medical knowledge search |
| Relational DB | PostgreSQL 16 + pgvector | Patients, doctors, slots |
| Containers | Docker Desktop + WSL2 | DB infrastructure |
| Package Manager | pip (Python) + npm (Node) | Dependencies |

---

## Project Structure

```
medical-ai-system/
│
├── .env                          # All secrets and config (never commit)
├── docker-compose.yml            # PostgreSQL + Qdrant containers
├── setup.ps1                     # One-time install script
├── start.ps1                     # Start all services at once
├── test_e2e.ps1                  # End-to-end test script
│
├── backend/
│   ├── main.py                   # FastAPI app, all endpoints, WebSocket
│   ├── intent_parser.py          # NLP: text -> {specialty, urgency, symptoms}
│   ├── Dockerfile                # Backend container image
│   ├── requirements.txt          # Python dependencies
│   │
│   ├── agents/                   # LangGraph agent nodes
│   │   ├── auth_agent.py         # Patient lookup / guest session
│   │   ├── schedule_agent.py     # Find + confirm appointment slots
│   │   ├── ehr_agent.py          # Read patient appointment history
│   │   ├── notify_agent.py       # Simulate SMS/email notification
│   │   └── ui_agent.py           # Format output for frontend
│   │
│   ├── workflows/
│   │   └── appointment_workflow.py  # LangGraph DAG definition
│   │
│   ├── models/
│   │   └── ollama_client.py      # Ollama HTTP client (generate, embed, pull)
│   │
│   ├── rag/
│   │   ├── embeddings.py         # Qdrant ingest + vector search
│   │   └── retriever.py          # Hybrid BM25 + semantic retrieval
│   │
│   └── database/
│       ├── db.py                 # All PostgreSQL queries (psycopg3)
│       └── schema.sql            # Tables + sample data (auto-applied by Docker)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Main layout, sidebar, workflow state
│   │   └── components/
│   │       ├── ChatInput.jsx     # Patient name + request input
│   │       ├── WorkflowProgress.jsx  # Live 6-step progress timeline
│   │       ├── SlotPicker.jsx    # Appointment slot selection cards
│   │       └── ConfirmationCard.jsx  # Booking confirmation display
│   └── ...config files
│
└── data/
    └── medical/
        ├── icd10_sample.json     # 50 ICD-10 codes for RAG knowledge base
        └── policies.txt          # 10 hospital policy documents for RAG
```

---

## Prerequisites

Before you start, make sure these are installed on your machine:

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Windows 10/11 | Build 19041+ | `winver` |
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Git | Any | `git --version` |
| Docker Desktop | 4.x | `docker --version` |
| Ollama | 0.24+ | `ollama --version` |
| WSL2 (modern) | 2.x | `wsl --version` |

> **Important:** Docker Desktop requires WSL2. If you get a "WSL needs updating" error, run:
> ```powershell
> winget install --id Microsoft.WSL -e --source winget --accept-package-agreements --accept-source-agreements
> ```
> Then relaunch Docker Desktop and click "Try Again".

---

## Step-by-Step Setup (First Time Only)

### Step 1 — Clone or copy the project

```powershell
cd D:\Ripha_projects\Gemma_project
# Project is already at: medical-ai-system\
```

### Step 2 — Install Docker Desktop

If Docker is not installed:
```powershell
winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
```
After install: **restart your PC**, then launch Docker Desktop from the Start menu and wait for it to fully start (green icon in system tray).

### Step 3 — Install Ollama

```powershell
winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
```
Or download from https://ollama.com/download/windows

### Step 4 — Pull AI Models (one-time, ~6 GB total)

Open a terminal and run these one by one:
```powershell
ollama pull nomic-embed-text   # ~274 MB  — embeddings
ollama pull phi4-mini          # ~2.5 GB  — intent parsing + agents
ollama pull gemma3:4b          # ~3.3 GB  — workflow generation
```
> This only needs to be done once. Models are stored in `~\.ollama\models\`.

### Step 5 — Create Python virtual environment

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r backend\requirements.txt
```

### Step 6 — Install frontend dependencies

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system\frontend
npm install
```

### Step 7 — Verify .env file exists

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
Get-Content .env
```
The `.env` file should contain all database, Qdrant, Ollama, and backend config values.

---

## Running the System (Every Time)

Open **4 separate terminals** in VSCode (click `+` in the terminal panel to add tabs).

### Terminal 1 — Start Docker containers (PostgreSQL + Qdrant)

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
docker compose up -d postgres qdrant
docker ps
```

Expected output:
```
medical_postgres   Up X seconds (healthy)
medical_qdrant     Up X seconds (healthy)
```

### Terminal 2 — Start Ollama

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
```
Leave this running. You will see: `Listening on 127.0.0.1:11434`

### Terminal 3 — Start FastAPI Backend

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Leave this running. You will see: `Uvicorn running on http://0.0.0.0:8000`

### Terminal 4 — Start React Frontend

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system\frontend
npm run dev
```
Leave this running. You will see: `Local: http://localhost:3000/`

---

## One-Time: Ingest RAG Knowledge Base

After Docker is running for the first time, load the medical knowledge into Qdrant.
Run this in any terminal (only needed once, or after resetting Qdrant):

```powershell
cd D:\Ripha_projects\Gemma_project\medical-ai-system
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from backend.rag.embeddings import load_and_ingest_all; load_and_ingest_all('data/medical')"
```

Expected output:
```
Created Qdrant collection: medical_knowledge
Ingested 50 documents into Qdrant
```

---

## Accessing the System

| URL | Description |
|---|---|
| http://localhost:3000 | React frontend (patient UI) |
| http://localhost:8000 | Backend API root |
| http://localhost:8000/docs | Swagger / interactive API docs |
| http://localhost:8000/api/health | Backend + Ollama health check |
| http://localhost:6333/dashboard | Qdrant web dashboard |
| http://localhost:11434 | Ollama API |

---

## How the Workflow Works (End-to-End Flow)

```
Patient types request in browser
         |
         v
POST /api/patient/request
         |
         v
intent_parser.py  <-- phi4-mini LLM
  Extracts: specialty, urgency, symptoms
         |
         v
LangGraph workflow starts (appointment_workflow.py)
         |
    [Node 1] auth_agent
      - Looks up patient by name in PostgreSQL
      - If not found: creates guest session
         |
    [Node 2] schedule_agent.find_slots
      - Queries PostgreSQL for available slots
      - Filters by specialty (cardiology, neurology, etc.)
         |
    [Node 3] ui_agent
      - Formats slots for display
         |
    [Node 4] wait_for_input  <-- workflow pauses here
      - Status set to "awaiting_input"
      - Frontend shows SlotPicker component
         |
    Patient clicks a slot
         |
POST /api/workflow/{id}/confirm
         |
    [Node 5] schedule_agent.confirm
      - Updates appointment status to "confirmed" in PostgreSQL
      - Returns appointment ID
         |
    [Node 6] ehr_agent
      - Reads patient appointment history
      - Generates EHR summary
         |
    [Node 7] notify_agent
      - Simulates SMS + email notification
      - Logs notification to PostgreSQL
         |
    Workflow status = "completed"
         |
Frontend shows ConfirmationCard with booking details
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/patient/request` | Submit a patient request (starts workflow) |
| GET | `/api/workflow/{id}` | Get workflow status and results |
| POST | `/api/workflow/{id}/confirm` | Confirm a selected appointment slot |
| GET | `/api/doctors` | List all doctors with next available slot |
| GET | `/api/patient/{name}/history` | Get appointment history for a patient |
| GET | `/api/health` | System health check |
| WS | `/api/workflow/{id}/stream` | WebSocket for real-time workflow updates |

### Example: Submit a request

```powershell
$body = '{"text": "I have chest pain, need a cardiologist urgently", "patient_name": "Sarah Johnson"}'
Invoke-RestMethod "http://localhost:8000/api/patient/request" -Method Post -Body $body -ContentType "application/json"
```

### Example: Confirm a slot

```powershell
$body = '{"slot_id": 6, "doctor_name": "Dr. James Patel", "specialty": "neurology", "date": "Monday, May 18, 2026", "time": "09:00 AM"}'
Invoke-RestMethod "http://localhost:8000/api/workflow/WF-XXXXXXXX/confirm" -Method Post -Body $body -ContentType "application/json"
```

---

## Database: Sample Data

The database is auto-populated when the Docker container first starts (from `backend/database/schema.sql`).

**Patients (5 records):**
| ID | Name | Email |
|---|---|---|
| 1 | John Smith | john.smith@email.com |
| 2 | Sarah Johnson | sarah.j@email.com |
| 3 | Michael Brown | mbrown@email.com |
| 4 | Emily Davis | emily.d@email.com |
| 5 | Robert Wilson | rwilson@email.com |

**Doctors (4 records):**
| Name | Specialty |
|---|---|
| Dr. Sarah Chen | Cardiology |
| Dr. James Patel | Neurology |
| Dr. Maria Rodriguez | Orthopedics |
| Dr. Emily Brown | General |

**Appointments:** 20 pre-seeded available slots across the next 7 days.

---

## AI Models Explained

| Model | Size | Used For | Speed (CPU) |
|---|---|---|---|
| `phi4-mini` | 2.5 GB | Intent parsing, agent decisions | ~4–10 seconds |
| `gemma3:4b` | 3.3 GB | Workflow generation, complex reasoning | ~10–20 seconds |
| `nomic-embed-text` | 274 MB | Converting text to vectors for RAG | ~1 second |

> All models run on CPU. GPU is not required. A machine with 8+ GB RAM is recommended.

---

## RAG Knowledge Base

The system uses hybrid retrieval (BM25 keyword + semantic vector search) over two document sets:

- **`data/medical/icd10_sample.json`** — 50 ICD-10 diagnosis codes across 4 specialties (cardiology, neurology, orthopedics, general)
- **`data/medical/policies.txt`** — 10 hospital policies (booking rules, urgency classification, cancellation, HIPAA, insurance)

Retrieval is used by agents to ground decisions in medical knowledge rather than pure LLM hallucination.

---

## Configuration (.env)

```env
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=medical_ai
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=medical_secret_key

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_WORKFLOW_MODEL=gemma3:4b
OLLAMA_INTENT_MODEL=phi4-mini
OLLAMA_AGENT_MODEL=phi4-mini
OLLAMA_EMBED_MODEL=nomic-embed-text

# Backend
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3000
```

---

## Troubleshooting

### Docker Desktop won't start — "WSL needs updating"
```powershell
winget install --id Microsoft.WSL -e --source winget --accept-package-agreements --accept-source-agreements
```
Then relaunch Docker Desktop and click "Try Again".

### Port 8000 already in use
```powershell
$pid = (netstat -ano | Select-String ":8000.*LISTEN" | ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -First 1)
Stop-Process -Id $pid -Force
```

### Ollama not found in terminal
```powershell
$env:PATH += ";$env:LOCALAPPDATA\Programs\Ollama"
ollama serve
```

### Backend times out on first request
Normal on first run — phi4-mini is loading into memory (~10–20 seconds). Subsequent requests are faster.

### PostgreSQL connection refused
Make sure Docker containers are running:
```powershell
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
docker ps
# If not running:
docker compose up -d postgres qdrant
```

### Qdrant shows 401 Unauthorized in browser
This is expected. Qdrant is secured with an API key. The Python backend uses it correctly. To access the dashboard directly:
```
http://localhost:6333/dashboard
```

### Frontend shows blank page or old data
Hard refresh: `Ctrl + Shift + R`

---

## Stopping the System

```powershell
# Stop Docker containers (data is preserved in Docker volumes)
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
cd D:\Ripha_projects\Gemma_project\medical-ai-system
docker compose down

# Stop Backend: press Ctrl+C in Terminal 3
# Stop Frontend: press Ctrl+C in Terminal 4
# Stop Ollama: press Ctrl+C in Terminal 2
```

To stop containers AND delete all data (full reset):
```powershell
docker compose down -v
```

---

## What Was Built (Implementation Summary)

This system was built entirely from scratch in a single session:

1. **Folder structure** — 38 source files across backend, frontend, data, and infrastructure
2. **Docker Compose** — PostgreSQL 16 with pgvector + Qdrant with health checks
3. **Database schema** — 5 tables with sample patients, doctors, and 20 appointment slots
4. **RAG knowledge base** — 50 ICD-10 entries + 10 hospital policies ingested into Qdrant
5. **Ollama client** — HTTP wrapper for generate, generate_json (with retry), embed, pull
6. **Intent parser** — phi4-mini LLM with rule-based fallback for specialty/urgency extraction
7. **5 LangGraph agents** — auth, schedule, EHR, notify, UI — each a pure Python function
8. **LangGraph workflow** — Stateful DAG with conditional branching and human-in-the-loop pause
9. **FastAPI backend** — 7 REST endpoints + WebSocket streaming, async-safe with thread offloading
10. **React frontend** — Live workflow timeline, slot picker, confirmation card, health monitoring
11. **E2E test script** — Automated PowerShell test covering full booking flow

**Key engineering decisions:**
- Used `psycopg3` (`psycopg[binary]`) instead of psycopg2 — required for Python 3.14 compatibility
- All blocking DB/LLM calls wrapped in `asyncio.to_thread()` to avoid freezing the async FastAPI event loop
- Added 3-second `connect_timeout` to PostgreSQL config so the backend degrades gracefully when DB is unreachable
- All agents handle DB failures gracefully with demo-mode fallback (demo slots when DB is offline)
- LangGraph `resume_workflow()` directly calls agents in sequence instead of re-invoking the graph (avoids checkpoint complexity)
