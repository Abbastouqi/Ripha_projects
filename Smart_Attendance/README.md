# SmartAttendance

A production-grade face recognition attendance system. Camera frames are processed by InsightFace (ArcFace 512D embeddings), matched against a FAISS vector index, and check-in / check-out events are logged to Supabase in real time.

## Features

- **Automatic check-in / check-out** — person enters frame → check-in logged; absent 5 minutes → auto check-out
- **Live browser monitor** — MJPEG stream with face boxes, who-is-IN panel, real-time event feed
- **Desktop client** — Tkinter app with live feed, enroll form, attendance table, unknown faces tab
- **Bulk enrollment** — drop photos in `enroll_images/Name_ID/` and run one script
- **Interactive unknown-face enrollment** — terminal tool that beeps on unknown face, prompts you to enroll live from camera
- **Excel export** — `GET /export/attendance` downloads a formatted spreadsheet
- **WebSocket events** — real-time push for check-in / check-out / unknown face
- **Auto-restart supervisor** — handles Windows WinError 64 crash automatically
- CPU-only (no GPU required) — tested on Intel i7-8550U

## Architecture

```
Camera (OpenCV)
    │
    ▼  every Nth frame (FRAME_SKIP)
FaceEngine (InsightFace buffalo_sc / buffalo_l)
    │  detection + 512D ArcFace embedding
    ▼
FaceTracker (IoU-based, reuses embeddings for tracked faces)
    │
    ▼  only for new / unidentified tracks
FaceMatcher (FAISS IndexFlatIP — cosine similarity, <1ms)
    │
    ├─ Known person  →  AttendanceService.on_face_seen()
    │                       └─ State machine: OUT → CHECKIN → IN
    │                       └─ Writes to Supabase presence_log + current_status
    │                       └─ Publishes WebSocket event
    │
    └─ Unknown face  →  AttendanceService.log_unknown()
                            └─ Saves JPEG crop to Supabase unknown_faces
                            └─ Publishes WebSocket event

Checkout watchdog (every 30s):
    absent ≥ CHECKOUT_TIMEOUT_SEC → CHECKOUT event + DB update
```

## Tech Stack

| Component | Library |
|---|---|
| API server | FastAPI + Uvicorn |
| Face detection & embedding | InsightFace (buffalo_sc / buffalo_l) |
| Vector search | FAISS (IndexFlatIP, cosine similarity) |
| Database | Supabase (PostgreSQL + pgvector) |
| Real-time events | WebSocket (FastAPI native) |
| Desktop client | Tkinter + Pillow |
| Excel export | openpyxl |

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/Abbastouqi/Ripha_projects.git
cd Ripha_projects

# Windows — creates venv and installs all dependencies
setup.bat
```

### 2. Configure Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run `database/schema_v1.sql`
3. Then run `database/schema_v2.sql`
4. Copy `.env.example` to `.env` and fill in your `SUPABASE_URL` and `SUPABASE_KEY`

### 3. Enroll people

Create subfolders in `enroll_images/` named `FullName_EmployeeID`:

```
enroll_images/
    Touqeer_001/
        photo1.jpg
        photo2.jpg
        photo3.jpg
    Ahmed_002/
        img1.jpg
        img2.jpg
```

Then run:

```bash
venv\Scripts\python.exe scripts\enroll_from_folder.py
```

### 4. Start the server

```bash
.\start.bat
```

Server runs at `http://localhost:8000`

### 5. Open the monitor

Double-click `client/monitor.html` in Explorer, or open it in your browser.

---

## Project Structure

```
SmartAttendance/
├── app/                        FastAPI application
│   ├── main.py                 API endpoints + lifespan
│   ├── config.py               Settings from .env
│   ├── face_engine.py          InsightFace wrapper
│   ├── tracker.py              IoU-based face tracker
│   ├── matcher.py              FAISS cosine similarity search
│   ├── attendance.py           Check-in/out state machine + WebSocket pub/sub
│   └── camera.py               Background camera capture loop
│
├── scripts/
│   ├── enroll_from_folder.py   Bulk enrollment from enroll_images/
│   └── enroll_unknown.py       Interactive terminal enrollment for unknown faces
│
├── client/
│   ├── monitor.html            Browser-based live monitor (no install needed)
│   └── desktop_client.py       Tkinter desktop app
│
├── database/
│   ├── schema_v1.sql           Core tables (persons, embeddings, unknown_faces)
│   └── schema_v2.sql           Presence tracking (presence_log, current_status)
│
├── enroll_images/              Drop enrollment photos here (gitignored)
├── models/                     InsightFace models auto-downloaded here
├── run.py                      Supervisor — auto-restarts server on crash
├── start.bat                   Windows launcher (kills old process, starts server)
├── setup.bat                   One-time setup (creates venv, installs deps)
├── requirements.txt
└── .env.example                Environment variable template
```

---

## Configuration

All settings live in `.env`:

| Variable | Default | Description |
|---|---|---|
| `SUPABASE_URL` | — | Your Supabase project URL |
| `SUPABASE_KEY` | — | Service role key (not anon) |
| `SIMILARITY_THRESHOLD` | `0.60` | Minimum cosine similarity to accept a match |
| `CAMERA_ID` | `0` | OpenCV camera index (0 = built-in webcam) |
| `FRAME_SKIP` | `5` | Process every Nth frame |
| `CHECKOUT_TIMEOUT_SEC` | `300` | Seconds absent before auto check-out |
| `INSIGHTFACE_MODEL` | `buffalo_sc` | `buffalo_sc` (fast) or `buffalo_l` (accurate) |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server status + enrolled face count |
| `GET` | `/stream` | MJPEG live camera feed |
| `GET` | `/snapshot` | Single JPEG frame |
| `POST` | `/enroll` | Enroll new person (multipart: name, employee_id, images) |
| `GET` | `/presence` | Who is currently IN |
| `GET` | `/presence/log` | Check-in/out event history |
| `GET` | `/attendance` | Check-in records (optional `?date=YYYY-MM-DD`) |
| `GET` | `/export/attendance` | Download Excel spreadsheet |
| `GET` | `/unknown-faces` | Unreviewed unknown face records |
| `PATCH` | `/unknown-faces/{id}/review` | Mark unknown face reviewed |
| `POST` | `/reload-index` | Reload FAISS from Supabase after bulk enrollment |
| `WS` | `/ws/events` | Real-time check-in / check-out / unknown events |

---

## Clients

### Browser Monitor (`client/monitor.html`)
Open directly in any browser — no server needed for the page itself.
- Live MJPEG stream with server-drawn face bounding boxes and name labels
- "Currently IN" panel with duration
- Real-time event feed via WebSocket
- Automatically reconnects on server restart

### Desktop Client (`client/desktop_client.py`)
```bash
venv\Scripts\python.exe client\desktop_client.py
```
Requires `Pillow` (included in requirements.txt).

### Terminal Enrollment Tool (`scripts/enroll_unknown.py`)
Run in a second terminal while the server is running:
```bash
venv\Scripts\python.exe scripts\enroll_unknown.py
```
Beeps on unknown face detection, prompts Y/N to enroll, captures 5 live snapshots.

---

## Model Comparison

| Model | Size | Speed (i7-8550U) | Accuracy (LFW) |
|---|---|---|---|
| `buffalo_sc` (MobileFaceNet) | ~100 MB | ~15 fps | ~99.0% |
| `buffalo_l` (ResNet100 + ArcFace) | ~1 GB | ~5 fps | ~99.4% |

Switch model in `.env`: `INSIGHTFACE_MODEL=buffalo_l` and set `FRAME_SKIP=10`.

---

## Similarity Threshold Guide

ArcFace cosine similarity ranges:

| Score | Meaning |
|---|---|
| 0.75 – 0.99 | Very confident — same person |
| 0.60 – 0.75 | Confident — good match |
| 0.50 – 0.60 | Uncertain — possible match |
| Below 0.50 | Different person → shown as Unknown |

**Recommended:** `SIMILARITY_THRESHOLD=0.60`. Never go below `0.55` — causes false matches.

---

## License

MIT
