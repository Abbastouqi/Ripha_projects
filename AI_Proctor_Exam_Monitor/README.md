# 🎓 Riphah Exam Monitoring System — ProctorAI
### Developed by Abbas

> An AI-powered online exam proctoring platform that monitors students in real-time using computer vision, object detection, and audio analysis to ensure exam integrity.

---

## 📋 Table of Contents
- [Overview](#overview)
- [Technology Stack](#technology-stack)
- [AI Models Used](#ai-models-used)
- [Database Design](#database-design)
- [Project Structure](#project-structure)
- [Full System Flow](#full-system-flow)
- [User Roles & Features](#user-roles--features)
- [ProctorAI Monitoring Engine](#proctorai-monitoring-engine)
- [Violation Detection System](#violation-detection-system)
- [API Endpoints](#api-endpoints)
- [How to Run](#how-to-run)
- [Default Credentials](#default-credentials)

---

## Overview

The **Riphah Exam Monitoring System (ProctorAI)** is a full-stack web application that enables:
- **Teachers** to create and manage online exams with multiple-choice questions
- **Students** to take proctored exams with real-time AI monitoring
- **Admins** to manage all users, view results, and review violation records

The system uses a live webcam feed to continuously monitor students during exams, detecting cheating behaviors such as looking away, multiple people in frame, banned objects (phones, laptops), window switching, and suspicious keyboard shortcuts.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.14, Flask 3.x |
| **Database** | MySQL 9.7 (port 3307) |
| **DB Connector** | Flask-MySQLdb (MySQLdb / libmysqlclient) |
| **Computer Vision** | OpenCV 4.13 |
| **Object Detection** | YOLOv8n (Ultralytics) |
| **Face Detection** | OpenCV Haar Cascade |
| **Face Matching** | OpenCV ORB (Oriented FAST and Rotated BRIEF) |
| **Head Pose** | MediaPipe FaceMesh + OpenCV solvePnP |
| **Audio Detection** | sounddevice (replaces pyaudio) |
| **Screen Monitoring** | PyGetWindow, PyAutoGUI |
| **Keyboard Monitoring** | keyboard library |
| **Frontend** | HTML5, CSS3, Bootstrap 4/5, Jinja2 |
| **Camera Streaming** | MJPEG over HTTP (multipart/x-mixed-replace) |
| **Concurrency** | Python threading, ThreadPoolExecutor |
| **Data Storage** | MySQL (users/exams/submissions) + JSON files (violations/results) |

---

## AI Models Used

### 1. YOLOv8n — Object Detection
- **Model file:** `yolov8n.pt`
- **Purpose:** Detects banned objects during the exam
- **Banned objects:** cell phone, laptop, remote, book, mouse, keyboard, TV, backpack, handbag
- **Confidence threshold:** 0.35
- **Loaded:** asynchronously in background thread at startup

### 2. OpenCV Haar Cascade — Face Detection
- **Model file:** `haarcascades/haarcascade_frontalface_default.xml`
- **Purpose:** Detects faces in the webcam frame for:
  - Multi-person detection (more than 1 face = violation)
  - Face presence check (no face = violation)
  - Face region extraction for identity matching

### 3. OpenCV ORB — Face Identity Matching
- **Algorithm:** ORB (Oriented FAST and Rotated BRIEF) feature descriptor
- **Purpose:** Matches the student's live face against their registered profile photo
- **How it works:** Extracts keypoints from face ROI, matches against stored descriptors using Brute-Force Hamming distance matcher
- **Match threshold:** ≥ 8 good matches (distance < 50) = verified identity
- **Replaces:** dlib + face_recognition (not available on Python 3.14)

### 4. MediaPipe FaceMesh + OpenCV solvePnP — Head Pose Estimation
- **Purpose:** Detects head direction (Forward / Looking Left / Right / Up / Down)
- **How it works:**
  - MediaPipe FaceMesh extracts 468 3D facial landmarks
  - 6 key landmarks used for pose estimation (nose tip, chin, eye corners, mouth corners)
  - OpenCV `solvePnP` computes rotation vector from 2D→3D point correspondences
  - `RQDecomp3x3` converts rotation matrix to Euler angles
  - Thresholds: y < -10° = Left, y > 15° = Right, x < -8° = Down, x > 15° = Up

### 5. sounddevice — Audio/Voice Detection
- **Purpose:** Detects noise/speech during the exam
- **How it works:** Continuous audio stream via `RawInputStream`, RMS energy calculated per frame, triggers recording when RMS > threshold (10)
- **Output:** Saves `.wav` files to `static/OutputAudios/`
- **Replaces:** pyaudio (not available on Python 3.14)

---

## Database Design

**Database name:** `examproctordb`  
**Host:** localhost | **Port:** 3307 | **User:** root

### Table: `students`
| Column | Type | Description |
|--------|------|-------------|
| ID | INT AUTO_INCREMENT PK | Unique user ID |
| Name | VARCHAR(100) | Full name |
| Email | VARCHAR(100) UNIQUE | Login email |
| Password | VARCHAR(100) | Plain text password |
| Role | ENUM('STUDENT','ADMIN','TEACHER') | User role |

### Table: `exams`
| Column | Type | Description |
|--------|------|-------------|
| id | INT AUTO_INCREMENT PK | Exam ID |
| title | VARCHAR(255) | Exam title |
| exam_code | VARCHAR(10) UNIQUE | 6-char code students use to join |
| course_code | VARCHAR(50) | Course identifier |
| duration | INT | Duration in minutes |
| questions | JSON | Array of question objects |
| created_by | INT | Teacher's student ID (FK) |
| assigned_to | JSON | Array of student IDs (empty = all) |
| created_at | TIMESTAMP | Creation time |

### Table: `submissions`
| Column | Type | Description |
|--------|------|-------------|
| id | INT AUTO_INCREMENT PK | Submission ID |
| exam_id | INT | FK to exams |
| student_id | INT | FK to students |
| score | INT | Raw correct answers count |
| total | INT | Total questions |
| trust_score | INT | 100 - violation marks |
| result_json_id | INT | Links to result.json entry |
| submitted_at | TIMESTAMP | Submission time |

### JSON Files (flat file storage)
- **`violation.json`** — All violation events with timestamps, durations, marks
- **`result.json`** — Exam result summaries with trust scores

---

## Project Structure

```
AI-Proctor-Exam-Monitor/
│
├── app.py                    # Flask application — all routes
├── utils.py                  # AI detection engine + helpers
├── requirements.txt          # Python dependencies
├── result.json               # Exam results (flat file)
├── violation.json            # Violation records (flat file)
├── yolov8n.pt                # YOLOv8 nano model weights
│
├── Haarcascades/
│   └── haarcascade_frontalface_default.xml
│
├── utils/
│   └── coco.txt              # COCO class names for YOLO
│
├── templates/
│   ├── login.html            # Login page
│   ├── register.html         # Registration page
│   ├── student-dashboard.html
│   ├── teacher-dashboard.html
│   ├── teacher-exams.html
│   ├── admin-dashboard.html
│   ├── Students.html         # Admin user management
│   ├── Results.html          # Admin exam results
│   ├── ResultDetails.html    # Violation detail view
│   ├── ResultDetailsVideo.html
│   ├── ExamRules.html        # Exam rules page
│   ├── ExamFaceInput.html    # Face capture page
│   ├── ExamConfirmFaceInput.html
│   ├── ExamSystemCheck.html  # Webcam/mic check
│   ├── ExamSystemCheckError.html
│   ├── Exam.html             # Main exam + AI monitor panel
│   ├── ExamSubmitted.html    # Submission confirmation
│   ├── ExamResultPass.html
│   └── ExamResultFail.html
│
└── static/
    ├── css/                  # Stylesheets
    ├── js/                   # JavaScript files
    ├── img/                  # Images
    ├── Profiles/             # Student face snapshots
    ├── OutputVideos/         # Violation video clips
    └── OutputAudios/         # Violation audio clips
```

---

## Full System Flow

### Student Flow
```
Login
  │
  ▼
Student Dashboard  ──→  Browse available exams
  │
  ▼  (click "Take Exam")
Exam Rules Page
  │
  ▼
Face Input Page  ──→  Live webcam feed shown
  │                   Haar Cascade draws green rectangle around face
  ▼  (click "Save Image")
Face Confirmation  ──→  Profile photo saved to static/Profiles/
  │                     ORB descriptors computed for identity matching
  ▼
System Check  ──→  Browser checks webcam + microphone availability
  │
  ▼
Exam Page
  │  ├── Questions loaded from database (answers hidden)
  │  ├── Countdown timer starts
  │  ├── AI Monitor Panel shows live camera feed
  │  ├── Background threads start monitoring:
  │  │     • Face identity (ORB matching)
  │  │     • Head pose (FaceMesh + solvePnP)
  │  │     • Multi-person (Haar Cascade)
  │  │     • Object detection (YOLOv8)
  │  │     • Window switching (PyGetWindow)
  │  │     • Keyboard shortcuts (keyboard library)
  │  │     • Audio/noise (sounddevice)
  │  └── Violations logged to violation.json in real-time
  │
  ▼  (submit or timer expires)
Exam Submitted Page  ──→  "Your exam has been submitted"
                          Score + violations saved to DB
```

### Teacher Flow
```
Login
  │
  ▼
Teacher Dashboard  ──→  Stats: exams created, submissions, students
  │
  ▼
My Exams Page
  │  ├── Create new exam (title, course, duration, questions)
  │  ├── Each exam gets a unique 6-char exam code
  │  ├── View submissions per exam
  │  └── Delete exam
  │
  ▼  (view submissions)
Submission List  ──→  Student name, score, trust score, timestamp
                      Click to view violation details
```

### Admin Flow
```
Login
  │
  ▼
Admin Dashboard  ──→  System-wide stats
  │
  ├── User Management  ──→  Add / Edit / Delete Students & Teachers
  │                         Tab view: Students | Teachers
  │
  └── Exam Results  ──→  All submitted exams from result.json
                         Click "Details" → violation breakdown
                         Click video/audio links → playback
```

---

## User Roles & Features

| Feature | Student | Teacher | Admin |
|---------|---------|---------|-------|
| Take proctored exam | ✅ | ❌ | ❌ |
| View available exams | ✅ | ❌ | ❌ |
| Create/manage exams | ❌ | ✅ | ❌ |
| View exam submissions | ❌ | ✅ | ✅ |
| View violation details | ❌ | ✅ | ✅ |
| Manage users (CRUD) | ❌ | ❌ | ✅ |
| View all results | ❌ | ❌ | ✅ |
| System-wide dashboard | ❌ | ❌ | ✅ |

---

## ProctorAI Monitoring Engine

The monitoring engine runs **5 parallel background threads** during an exam:

| Thread | Function | Detection Method |
|--------|----------|-----------------|
| `cheat_Detection1` | Head pose monitoring | OpenCV face position heuristic |
| `cheat_Detection2` | Multi-person + screen | Haar Cascade + PyGetWindow |
| `fr.run_recognition` | Identity verification | ORB feature matching |
| `a.record` | Voice/noise detection | sounddevice RMS analysis |
| `_load_yolo` (startup) | Object detection | YOLOv8n predict |

### Shared Camera Architecture
A single **camera reader thread** (`start_camera_reader`) captures frames at ~30fps and stores them in `latest_frame` (protected by `frame_lock`). All detection threads and the MJPEG stream read from this shared frame — no multiple VideoCapture instances.

### Real-time Monitor Panel
During the exam, a floating panel (bottom-right) shows:
- 🔴/🟢 **Face** — detected or not
- 🔴/🟡/🟢 **Gaze** — Forward / Looking Left/Right/Up/Down
- 🔴/🟢 **Persons** — count of faces detected
- 🔴/🟢 **Objects** — banned object name if detected
- **Violations counter** — total violations logged
- **Alert message** — last triggered alert

---

## Violation Detection System

| Violation Type | Trigger | Mark Formula |
|---------------|---------|-------------|
| Face not visible | No face detected for > 3 seconds | 2 × duration (seconds) |
| Identity mismatch | ORB match score < 8 for > 3 seconds | 2 × duration |
| Head movement | Not looking forward for > 3 seconds | 1 × duration |
| Multiple persons | More than 1 face for > 3 seconds | 1.5 × duration |
| Window switch | Active window ≠ exam browser | 2 × duration |
| Banned object | Phone/laptop/book detected for > 3 seconds | 1.5 × duration |
| Keyboard shortcut | Ctrl+C/V, Alt+Tab, F1-F3, Win key, etc. | Logged (0 marks) |
| Voice/noise | RMS audio energy > threshold | 1 × duration |

**Trust Score** = 100 − (sum of all violation marks)  
A trust score of 0 means maximum violations detected.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Login page |
| POST | `/login` | Authenticate user |
| GET | `/logout` | Clear session |
| GET | `/register` | Registration page |
| POST | `/api/register` | Register new user |
| GET | `/student/dashboard` | Student home |
| GET | `/api/student/exams` | List available exams |
| GET | `/student/take-exam/<code>` | Start exam flow |
| GET | `/rules` | Exam rules |
| GET | `/faceInput` | Face capture page |
| GET | `/video_capture` | MJPEG camera stream |
| GET | `/saveFaceInput` | Save face snapshot |
| GET | `/confirmFaceInput` | Confirm face photo |
| GET/POST | `/systemCheck` | System compatibility check |
| GET | `/exam` | Exam page |
| POST | `/exam` | Submit exam answers |
| GET | `/examSubmitted/<name>` | Submission confirmation |
| GET | `/teacher/dashboard` | Teacher home |
| GET | `/teacher/exams` | Teacher exam list |
| POST | `/api/teacher/exams` | Create new exam |
| GET | `/api/teacher/exam/<id>/submissions` | View submissions |
| POST | `/api/teacher/exam/<id>/delete` | Delete exam |
| GET | `/api/monitoring/status` | Real-time AI status (JSON) |
| GET | `/api/violations/<rid>` | Violation records for result |
| GET | `/admin/dashboard` | Admin overview |
| GET | `/adminStudents` | User management |
| GET | `/adminResults` | All exam results |
| GET | `/adminResultDetails/<id>` | Result + violations |
| POST | `/insertStudent` | Add user |
| GET | `/deleteStudent/<id>` | Delete user |
| POST | `/updateStudent` | Update user |

---

## How to Run

### Prerequisites
- Python 3.14+
- MySQL 9.7 running on port 3307
- Webcam connected

### Step 1 — Install dependencies
```bash
pip install flask flask-mysqldb numpy opencv-python mediapipe ultralytics keyboard pyautogui pygetwindow sounddevice pyperclip
```

### Step 2 — Setup MySQL database
Open MySQL Command Line Client and run:
```sql
CREATE DATABASE IF NOT EXISTS examproctordb;
USE examproctordb;

CREATE TABLE IF NOT EXISTS students (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Email VARCHAR(100) NOT NULL UNIQUE,
    Password VARCHAR(100) NOT NULL,
    Role ENUM('STUDENT','ADMIN','TEACHER') DEFAULT 'STUDENT'
);

INSERT INTO students (Name, Email, Password, Role)
VALUES ('Admin', 'admin@riphah.edu.pk', 'admin', 'ADMIN');

INSERT INTO students (Name, Email, Password, Role)
VALUES ('Abbas', 'abbas@riphah.edu.pk', 'abbas123', 'STUDENT');
```

### Step 3 — Run the application
```bash
# Kill any old Python processes first
taskkill /F /IM python.exe /T

# Navigate to project folder
cd E:\exam_monitoring_system\AI-Proctor-Exam-Monitor

# Start the app
python app.py
```

### Step 4 — Open browser
Wait ~15 seconds for YOLO to load, then open:
```
http://127.0.0.1:5000
```

---

## Default Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@riphah.edu.pk | admin |
| Student | abbas@riphah.edu.pk | abbas123 |

> To add a Teacher account: login as Admin → User Management → Add User → select Role: Teacher

---

## Notes

- **Face recognition** uses OpenCV ORB instead of dlib (dlib has no Python 3.14 wheel)
- **Audio detection** uses sounddevice instead of pyaudio (same reason)
- **Video recording** of violations is disabled by default (requires FFmpeg); violations are logged to JSON
- The `exam_window_title` in `utils.py` is set to `"Exam — Mozilla Firefox"` — update this if using a different browser
- Database credentials are in `app.py` — change `MYSQL_PASSWORD` to match your MySQL root password

---

*Riphah Exam Monitoring System — ProctorAI | Developed by Abbas*
