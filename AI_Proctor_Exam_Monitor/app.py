# ═══════════════════════════════════════════════════════════════════════════
#  ProctorAI — Exam Monitoring System
#  Backend:  Flask (Python)
#  Database: MySQL  ·  host: localhost  ·  port: 3307  ·  db: examproctordb
#            Connector: flask-mysqldb (MySQLdb / libmysqlclient)
#  AI stack: MediaPipe FaceMesh (head/gaze), Haar Cascade (multi-person),
#            YOLOv8n (object detection), face_recognition/ORB (identity)
# ═══════════════════════════════════════════════════════════════════════════

import math
import string
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, flash
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os
load_dotenv()
from flask_mysqldb import MySQL
import json
import numpy as np
import warnings
import threading
import utils
import grader
import random
import time
import cv2
import keyboard
import pdfplumber
import io
try:
    from docx import Document as DocxDocument
    DOCX_OK = True
except ImportError:
    DOCX_OK = False

# ── shared state ────────────────────────────────────────────────────────────
studentInfo  = None   # legacy dict kept for non-session exam flows
profileName  = None   # path to the saved face snapshot
_db_initialized = False

warnings.filterwarnings("ignore")
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'xyz'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ── MySQL config  (database: examproctordb, port 3307) ──────────────────────
app.config['MYSQL_HOST']     = 'localhost'
app.config['MYSQL_USER']     = 'root'
app.config['MYSQL_PASSWORD'] = 'admin'
app.config['MYSQL_DB']       = 'examproctordb'
app.config['MYSQL_PORT']     = 3307
mysql = MySQL(app)

executor = ThreadPoolExecutor(max_workers=8)
_started = False


def _violation_push(name: str, detail: str):
    """Push a violation event to all connected exam clients via Socket.IO."""
    socketio.emit('violation', {'name': name, 'detail': detail})


utils.set_violation_callback(_violation_push)


# ─────────────────────────── helpers ────────────────────────────

def generate_exam_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def init_db():
    global _db_initialized
    if _db_initialized:
        return
    try:
        cur = mysql.connection.cursor()
        # Add TEACHER to the role enum (ignore if already exists)
        try:
            cur.execute(
                "ALTER TABLE students MODIFY COLUMN Role ENUM('STUDENT','ADMIN','TEACHER') DEFAULT 'STUDENT'"
            )
            mysql.connection.commit()
        except Exception:
            pass

        cur.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                title       VARCHAR(255) NOT NULL,
                exam_code   VARCHAR(10)  UNIQUE NOT NULL,
                course_code VARCHAR(50)  DEFAULT '',
                duration    INT          DEFAULT 60,
                questions   JSON,
                created_by  INT,
                assigned_to JSON,
                created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                exam_id        INT,
                student_id     INT,
                score          INT          DEFAULT 0,
                total          INT          DEFAULT 0,
                trust_score    INT          DEFAULT 100,
                result_json_id INT          DEFAULT 0,
                submitted_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add result_json_id column if upgrading from older schema
        try:
            cur.execute("ALTER TABLE submissions ADD COLUMN result_json_id INT DEFAULT 0")
            mysql.connection.commit()
        except Exception:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subjective_answers (
                id               INT AUTO_INCREMENT PRIMARY KEY,
                submission_id    INT NOT NULL,
                question_index   INT NOT NULL,
                question_text    TEXT,
                student_answer   TEXT,
                ai_score         FLOAT DEFAULT 0,
                ai_feedback      TEXT,
                ideal_answer     TEXT,
                solution         TEXT,
                correct_points   JSON,
                mistakes         JSON,
                max_marks        INT DEFAULT 5,
                graded           TINYINT DEFAULT 0,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add analysis columns to existing table if upgrading
        for col, defn in [("solution", "TEXT"), ("correct_points", "JSON"),
                          ("mistakes", "JSON"), ("matching_keywords", "JSON"),
                          ("missing_keywords", "JSON"), ("semantic_score", "FLOAT DEFAULT 0")]:
            try:
                cur.execute(f"ALTER TABLE subjective_answers ADD COLUMN {col} {defn}")
                mysql.connection.commit()
            except Exception:
                pass
        mysql.connection.commit()
        cur.close()
        _db_initialized = True
    except Exception as e:
        print(f"[DB init] {e}")


# ─────────────────────────── MJPEG feed ─────────────────────────
# Reads from the shared latest_frame — no new VideoCapture here.

def capture_by_frames():
    detector = cv2.CascadeClassifier('Haarcascades/haarcascade_frontalface_default.xml')
    while True:
        with utils.frame_lock:
            frame = utils.latest_frame.copy() if utils.latest_frame is not None else None
        if frame is None:
            frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, 'Camera starting...', (90, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (80, 80, 80), 2)
        else:
            faces = detector.detectMultiScale(frame, 1.2, 6)
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.05)  # ~20 fps cap


# ─────────────────────── before_request ─────────────────────────
# Start camera + detection threads once at first request.

@app.before_request
def before_request():
    global _started
    init_db()
    if not _started:
        _started = True
        utils.deleteTrashVideos()   # remove any leftover mp4 files from previous runs
        utils.start_camera_reader()
        executor.submit(utils.cheat_Detection1)
        executor.submit(utils.cheat_Detection2)
        executor.submit(utils.fr.run_recognition)
        executor.submit(utils.a.record)


# ═══════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def main():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    global studentInfo
    username = request.form['username']
    password = request.form['password']
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM students WHERE Email=%s AND Password=%s", (username, password))
        data = cur.fetchone()
        cur.close()
    except Exception as e:
        print(f"[login] DB error: {e}")
        flash('Database error, please try again.', category='error')
        return redirect(url_for('main'))
    if data is None:
        flash('Your Email or Password is incorrect, try again.', category='error')
        return redirect(url_for('main'))
    id, name, email, _, role = data
    studentInfo = {"Id": id, "Name": name, "Email": email}
    session['user_id'] = id
    session['user_name'] = name
    session['user_role'] = role
    if role == 'STUDENT':
        utils.Student_Name = name
        return redirect(url_for('studentDashboard'))
    elif role == 'TEACHER':
        return redirect(url_for('teacherDashboard'))
    else:  # ADMIN
        return redirect(url_for('adminDashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return render_template('login.html')


# ─── Registration ────────────────────────────────────────────────

@app.route('/register')
def register():
    return render_template('register.html')


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'STUDENT').upper()
    if role not in ('STUDENT', 'TEACHER'):
        return jsonify({"error": "Invalid role"}), 400
    if not name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT ID FROM students WHERE Email=%s", (email,))
        if cur.fetchone():
            cur.close()
            return jsonify({"error": "Email already registered"}), 400
        cur.execute(
            "INSERT INTO students (Name, Email, Password, Role) VALUES (%s, %s, %s, %s)",
            (name, email, password, role)
        )
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
    except Exception as e:
        print(f"[api_register] DB error: {e}")
        return jsonify({"error": "Database error, please try again"}), 500
    session['user_id'] = new_id
    session['user_name'] = name
    session['user_role'] = role
    return jsonify({"success": True, "role": role})


# ═══════════════════════════════════════════════════════════════
#  STUDENT FLOW
# ═══════════════════════════════════════════════════════════════

@app.route('/student/dashboard')
def studentDashboard():
    if session.get('user_role') not in ('STUDENT',):
        return redirect(url_for('main'))
    return render_template('student-dashboard.html', student_name=session.get('user_name', ''))


@app.route('/api/student/exams')
def apiStudentExams():
    # Returns all exams available (or assigned) to the current student
    student_id = session.get('user_id')
    if not student_id:
        return jsonify([])
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, title, exam_code, course_code, duration, questions, assigned_to, created_at FROM exams"
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            exam_id, title, code, course, duration, qjson, assigned_json, created_at = row
            questions = json.loads(qjson) if qjson else []
            assigned = json.loads(assigned_json) if assigned_json else []
            # available to all if assigned list is empty
            if assigned and student_id not in assigned and str(student_id) not in [str(a) for a in assigned]:
                continue
            cur.execute("SELECT id FROM submissions WHERE exam_id=%s AND student_id=%s", (exam_id, student_id))
            submitted = cur.fetchone() is not None
            result.append({
                "id": exam_id,
                "title": title,
                "exam_code": code,
                "course_code": course,
                "duration": duration,
                "question_count": len(questions),
                "submitted": submitted,
                "created_at": str(created_at)
            })
        cur.close()
    except Exception as e:
        print(f"[apiStudentExams] DB error: {e}")
        result = []
    return jsonify(result)


@app.route('/student/take-exam/<exam_code>')
def studentTakeExam(exam_code):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title, duration FROM exams WHERE exam_code=%s", (exam_code,))
    row = cur.fetchone()
    cur.close()
    if not row:
        flash('Exam not found.', 'error')
        return redirect(url_for('studentDashboard'))
    session['current_exam_id'] = row[0]
    session['current_exam_title'] = row[1]
    session['current_exam_duration'] = row[2]
    utils.Student_Name = session.get('user_name', '')
    global studentInfo
    studentInfo = {"Id": session['user_id'], "Name": session['user_name'], "Email": ""}
    return redirect(url_for('rules'))


# ─── Exam questions API (no correct answers exposed) ─────────────

@app.route('/api/exam/questions')
def apiExamQuestions():
    exam_id = session.get('current_exam_id')
    if not exam_id:
        return jsonify({"error": "No active exam"}), 400
    cur = mysql.connection.cursor()
    cur.execute("SELECT questions, duration, title FROM exams WHERE id=%s", (exam_id,))
    row = cur.fetchone()
    cur.close()
    if not row:
        return jsonify({"error": "Exam not found"}), 404
    qjson, duration, title = row
    questions = json.loads(qjson) if qjson else []
    safe_qs = []
    for q in questions:
        entry = {"title": q.get("title", ""), "type": q.get("type", "mcq")}
        if entry["type"] == "subjective":
            entry["marks"] = q.get("marks", 5)
        else:
            entry["choices"] = q.get("choices", [])
        safe_qs.append(entry)
    return jsonify({"questions": safe_qs, "duration": duration * 60, "title": title, "total": len(safe_qs)})


# ─── Existing student routes (unchanged) ────────────────────────

@app.route('/rules')
def rules():
    return render_template('ExamRules.html')


@app.route('/faceInput')
def faceInput():
    return render_template('ExamFaceInput.html')


@app.route('/video_capture')
def video_capture():
    return Response(capture_by_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_snapshot')
def video_snapshot():
    """Single JPEG frame — used by ExamFaceInput for JS-driven refresh."""
    detector = cv2.CascadeClassifier('Haarcascades/haarcascade_frontalface_default.xml')
    with utils.frame_lock:
        frame = utils.latest_frame.copy() if utils.latest_frame is not None else None
    if frame is None:
        frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, 'Camera starting...', (90, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (80, 80, 80), 2)
    else:
        faces = detector.detectMultiScale(frame, 1.2, 6)
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
    _, buffer = cv2.imencode('.jpg', frame)
    resp = Response(buffer.tobytes(), mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/saveFaceInput')
def saveFaceInput():
    global profileName
    with utils.frame_lock:
        frame = utils.latest_frame.copy() if utils.latest_frame is not None else None
    if frame is None:
        return "Camera error: no frame available.", 500
    student_name = session.get('user_name') or (studentInfo['Name'] if studentInfo else 'Student')
    profileName = f"{student_name}_{utils.get_resultId():03}Profile.jpg"
    cv2.imwrite(profileName, frame)
    utils.move_file_to_output_folder(profileName, 'Profiles')
    return redirect(url_for('confirmFaceInput'))


@app.route('/confirmFaceInput')
def confirmFaceInput():
    profile = profileName
    utils.fr.encode_faces()
    return render_template('ExamConfirmFaceInput.html', profile=profile)


@app.route('/systemCheck')
def systemCheck():
    return render_template('ExamSystemCheck.html')


@app.route('/systemCheck', methods=["POST"])
def systemCheckRoute():
    if request.method == 'POST':
        examData = request.json
        output = 'exam'
        if 'Not available' in examData['input'].split(';'):
            output = 'systemCheckError'
    return jsonify({"output": output})


@app.route('/systemCheckError')
def systemCheckError():
    return render_template('ExamSystemCheckError.html')


# ─── Main exam page – passes dynamic questions via Jinja2 ────────

@app.route('/exam')
def exam():
    keyboard.hook(utils.shortcut_handler)

    exam_id = session.get('current_exam_id')
    questions_json = '[]'
    exam_duration = 300   # seconds
    exam_title = "Exam Test"

    if exam_id:
        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT questions, duration, title FROM exams WHERE id=%s", (exam_id,))
            row = cur.fetchone()
            cur.close()
            if row:
                qjson, duration, title = row
                qs = json.loads(qjson) if qjson else []
                safe_qs = []
                for q in qs:
                    entry = {"title": q.get("title", ""), "type": q.get("type", "mcq")}
                    if entry["type"] == "subjective":
                        entry["marks"] = q.get("marks", 5)
                    else:
                        entry["choices"] = q.get("choices", [])
                    safe_qs.append(entry)
                questions_json = json.dumps(safe_qs)
                exam_duration = duration * 60
                exam_title = title
        except Exception as e:
            print(f"[exam] could not load questions: {e}")

    return render_template('Exam.html',
                           questions_json=questions_json,
                           exam_duration=exam_duration,
                           exam_title=exam_title)


@app.route('/exam', methods=["POST"])
def examAction():
    link = ''
    if request.method == 'POST':
        examData = request.json
        if examData['input'] != '':
            utils.Globalflag = False
            # Log any keyboard shortcuts caught
            if utils.shorcuts:
                utils.write_json({
                    "Name": 'Prohibited Shortcuts (' + ','.join(list(dict.fromkeys(utils.shorcuts))) + ') detected.',
                    "Time": str(len(utils.shorcuts)) + " Counts",
                    "Duration": '',
                    "Mark": 0,
                    "Link": '',
                    "RId": utils.get_resultId()
                })
                utils.shorcuts = []

            trustScore   = utils.get_TrustScore(utils.get_resultId())
            totalMark    = math.floor(float(examData['input']) * 6.6667)
            student_name = session.get('user_name') or (studentInfo['Name'] if studentInfo else 'Student')
            student_id_val = session.get('user_id') or (studentInfo['Id'] if studentInfo else 0)
            rid          = utils.get_resultId()

            # Record to result.json for admin/teacher reports
            utils.write_json({
                "Id": rid,
                "Name": student_name,
                "TotalMark": totalMark,
                "TrustScore": max(100 - trustScore, 0),
                "Status": "Submitted",
                "Date": time.strftime("%Y-%m-%d", time.localtime(time.time())),
                "StId": student_id_val,
                "Link": profileName
            }, "result.json")

            # Save to submissions table
            exam_id = session.get('current_exam_id')
            if exam_id and student_id_val:
                try:
                    cur = mysql.connection.cursor()
                    cur.execute("SELECT id FROM submissions WHERE exam_id=%s AND student_id=%s",
                                (exam_id, student_id_val))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO submissions (exam_id, student_id, score, total, trust_score, result_json_id) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (exam_id, student_id_val, int(examData['input']), 15,
                             max(100 - trustScore, 0), rid)
                        )
                        mysql.connection.commit()
                    cur.close()
                except Exception as e:
                    print(f"[examAction] submission save error: {e}")

            # Student sees only "Submitted" — teacher/admin see the actual score and violations
            link = 'examSubmitted'
            resultStatus = student_name
        else:
            utils.Globalflag = True
            utils._audio_violation_logged = False   # reset for new exam session
            resultStatus = ''
    return jsonify({"output": resultStatus, "link": link})


@app.route('/examSubmitted/<student_name>')
def examSubmitted(student_name):
    return render_template('ExamSubmitted.html', student_name=student_name)


@app.route('/showResultPass/<result_status>')
def showResultPass(result_status):
    return render_template('ExamResultPass.html', result_status=result_status)


@app.route('/showResultFail/<result_status>')
def showResultFail(result_status):
    return render_template('ExamResultFail.html', result_status=result_status)


# ═══════════════════════════════════════════════════════════════
#  TEACHER ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/teacher/dashboard')
def teacherDashboard():
    # Teachers only
    if session.get('user_role') != 'TEACHER':
        return redirect(url_for('main'))
    teacher_id = session.get('user_id')
    exam_count = submission_count = student_count = 0
    recent = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM exams WHERE created_by=%s", (teacher_id,))
        exam_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM submissions s JOIN exams e ON s.exam_id=e.id WHERE e.created_by=%s",
            (teacher_id,)
        )
        submission_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM students WHERE Role='STUDENT'")
        student_count = cur.fetchone()[0]
        cur.execute("""
            SELECT st.Name, e.title, s.score, s.total, s.trust_score, s.submitted_at
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN students st ON s.student_id = st.ID
            WHERE e.created_by = %s
            ORDER BY s.submitted_at DESC
            LIMIT 8
        """, (teacher_id,))
        recent = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"[teacherDashboard] DB error: {e}")
    return render_template('teacher-dashboard.html',
                           teacher_name=session.get('user_name', ''),
                           exam_count=exam_count,
                           submission_count=submission_count,
                           student_count=student_count,
                           recent=recent)


@app.route('/teacher/exams')
def teacherExams():
    # Teachers only — lists all exams created by this teacher
    if session.get('user_role') != 'TEACHER':
        return redirect(url_for('main'))
    teacher_id = session.get('user_id')
    exams = []
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, title, exam_code, course_code, duration, questions, created_at "
            "FROM exams WHERE created_by=%s ORDER BY created_at DESC",
            (teacher_id,)
        )
        rows = cur.fetchall()
        cur.close()
        for row in rows:
            eid, title, code, course, duration, qjson, created_at = row
            q = json.loads(qjson) if qjson else []
            exams.append({
                "id": eid, "title": title, "exam_code": code,
                "course_code": course, "duration": duration,
                "question_count": len(q), "created_at": str(created_at)
            })
    except Exception as e:
        print(f"[teacherExams] DB error: {e}")
    return render_template('teacher-exams.html',
                           teacher_name=session.get('user_name', ''),
                           exams=exams)


@app.route('/api/teacher/exams', methods=['POST'])
def apiCreateExam():
    # Creates a new exam; generates a unique 6-char exam code
    if session.get('user_role') != 'TEACHER':
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    title = data.get('title', '').strip()
    course_code = data.get('course_code', '').strip()
    duration = int(data.get('duration', 60))
    questions = data.get('questions', [])
    if not title or not questions:
        return jsonify({"error": "Title and at least one question are required"}), 400
    try:
        exam_code = generate_exam_code()
        teacher_id = session.get('user_id')
        cur = mysql.connection.cursor()
        while True:
            cur.execute("SELECT id FROM exams WHERE exam_code=%s", (exam_code,))
            if not cur.fetchone():
                break
            exam_code = generate_exam_code()
        cur.execute(
            "INSERT INTO exams (title, exam_code, course_code, duration, questions, created_by, assigned_to) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (title, exam_code, course_code, duration, json.dumps(questions), teacher_id, json.dumps([]))
        )
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
    except Exception as e:
        print(f"[apiCreateExam] DB error: {e}")
        return jsonify({"error": "Database error creating exam"}), 500
    return jsonify({"success": True, "exam_code": exam_code, "id": new_id})


@app.route('/api/teacher/exam/<int:exam_id>/submissions')
def apiExamSubmissions(exam_id):
    if session.get('user_role') != 'TEACHER':
        return jsonify({"error": "Unauthorized"}), 403
    try:
        cur = mysql.connection.cursor()
        # Check if exam has subjective questions
        cur.execute("SELECT questions FROM exams WHERE id=%s", (exam_id,))
        eq = cur.fetchone()
        exam_qs = json.loads(eq[0]) if eq and eq[0] else []
        is_subjective = any(q.get('type') == 'subjective' for q in exam_qs)

        cur.execute("""
            SELECT s.id, st.Name, st.Email, s.score, s.total, s.trust_score, s.submitted_at, s.result_json_id
            FROM submissions s
            JOIN students st ON s.student_id = st.ID
            WHERE s.exam_id = %s
            ORDER BY s.submitted_at DESC
        """, (exam_id,))
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"[apiExamSubmissions] DB error: {e}")
        return jsonify([])
    result = []
    for row in rows:
        sid, name, email, score, total, trust, sub_at, rid = row
        pct = math.floor(score / total * 100) if total else 0
        result.append({
            "submission_id": sid,
            "student_name": name, "email": email,
            "score": score, "total": total, "percentage": pct,
            "trust_score": trust, "submitted_at": str(sub_at),
            "result_json_id": rid or 0,
            "is_subjective": is_subjective,
        })
    return jsonify(result)


@app.route('/api/violations/<int:rid>')
def apiViolations(rid):
    if session.get('user_role') not in ('TEACHER', 'ADMIN'):
        return jsonify({"error": "Unauthorized"}), 403
    if rid == 0:
        return jsonify([])
    try:
        details = utils.getResultDetails(rid)
        return jsonify(details.get('Violation', []))
    except Exception:
        return jsonify([])


@app.route('/api/teacher/exam/<int:exam_id>/delete', methods=['POST'])
def apiDeleteExam(exam_id):
    # Only the teacher who owns the exam can delete it
    if session.get('user_role') != 'TEACHER':
        return jsonify({"error": "Unauthorized"}), 403
    teacher_id = session.get('user_id')
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM exams WHERE id=%s AND created_by=%s", (exam_id, teacher_id))
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print(f"[apiDeleteExam] DB error: {e}")
        return jsonify({"error": "Database error"}), 500
    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════
#  MONITORING STATUS (camera sidebar polling)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/monitoring/status')
def monitoringStatus():
    return jsonify(utils.monitoring_status)


# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/admin/dashboard')
def adminDashboard():
    # Admins only — overview stats + recent submissions and users
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    student_count = teacher_count = exam_count = submission_count = 0
    recent = []
    recent_users = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM students WHERE Role='STUDENT'")
        student_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM students WHERE Role='TEACHER'")
        teacher_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM exams")
        exam_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM submissions")
        submission_count = cur.fetchone()[0]
        # Latest 10 submissions across all exams
        cur.execute("""
            SELECT st.Name, COALESCE(t.Name, 'Unknown'), e.title,
                   s.score, s.total, s.trust_score, s.submitted_at
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN students st ON s.student_id = st.ID
            LEFT JOIN students t ON e.created_by = t.ID
            ORDER BY s.submitted_at DESC
            LIMIT 10
        """)
        recent = cur.fetchall()
        # Latest 12 registered users
        cur.execute("SELECT ID, Name, Email, Role FROM students ORDER BY ID DESC LIMIT 12")
        recent_users = cur.fetchall()
        # All teachers (always shown in dedicated section)
        cur.execute("SELECT ID, Name, Email FROM students WHERE Role='TEACHER' ORDER BY ID")
        all_teachers = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"[adminDashboard] DB error: {e}")
        all_teachers = []
    return render_template('admin-dashboard.html',
                           student_count=student_count,
                           teacher_count=teacher_count,
                           exam_count=exam_count,
                           submission_count=submission_count,
                           recent=recent,
                           recent_users=recent_users,
                           all_teachers=all_teachers)


@app.route('/adminResults')
def adminResults():
    # Admins only — all exam results from result.json
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    try:
        results = utils.getResults()
    except Exception as e:
        print(f"[adminResults] error: {e}")
        results = []
    return render_template('Results.html', results=results)


@app.route('/adminResultDetails/<resultId>')
def adminResultDetails(resultId):
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    try:
        result_Details = utils.getResultDetails(resultId)
    except Exception as e:
        print(f"[adminResultDetails] error: {e}")
        result_Details = {}
    return render_template('ResultDetails.html', resultDetials=result_Details)


@app.route('/adminResultDetailsVideo/<videoInfo>')
def adminResultDetailsVideo(videoInfo):
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    return render_template('ResultDetailsVideo.html', videoInfo=videoInfo)


@app.route('/adminStudents')
def adminStudents():
    # Admins only — shows all students and teachers
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    students = []
    teachers = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT ID, Name, Email, Role FROM students WHERE Role='STUDENT' ORDER BY ID")
        students = cur.fetchall()
        cur.execute("SELECT ID, Name, Email, Role FROM students WHERE Role='TEACHER' ORDER BY ID")
        teachers = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"[adminStudents] DB error: {e}")
    return render_template('Students.html', students=students, teachers=teachers)


@app.route('/insertStudent', methods=['POST'])
def insertStudent():
    # Admin adds a new student or teacher account
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    try:
        name = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role', 'STUDENT').upper()
        if role not in ('STUDENT', 'TEACHER'):
            role = 'STUDENT'
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO students (Name, Email, Password, Role) VALUES (%s, %s, %s, %s)",
            (name, email, password, role)
        )
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print(f"[insertStudent] DB error: {e}")
        flash("Error adding user. Email may already be in use.", "error")
    return redirect(url_for('adminStudents'))


@app.route('/deleteStudent/<string:stdId>', methods=['GET'])
def deleteStudent(stdId):
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM students WHERE ID=%s", (stdId,))
        mysql.connection.commit()
        cur.close()
        flash("Record Has Been Deleted Successfully")
    except Exception as e:
        print(f"[deleteStudent] DB error: {e}")
        flash("Error deleting record.", "error")
    return redirect(url_for('adminStudents'))


@app.route('/updateStudent', methods=['POST', 'GET'])
def updateStudent():
    # Admin edits name/email and optionally password of any user
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main'))
    if request.method == 'POST':
        try:
            id_data = request.form['id']
            name = request.form['name']
            email = request.form['email']
            password = request.form.get('password', '').strip()
            cur = mysql.connection.cursor()
            if password:
                cur.execute(
                    "UPDATE students SET Name=%s, Email=%s, Password=%s WHERE ID=%s",
                    (name, email, password, id_data)
                )
            else:
                cur.execute(
                    "UPDATE students SET Name=%s, Email=%s WHERE ID=%s",
                    (name, email, id_data)
                )
            mysql.connection.commit()
            cur.close()
        except Exception as e:
            print(f"[updateStudent] DB error: {e}")
            flash("Error updating user.", "error")
    return redirect(url_for('adminStudents'))


# ═══════════════════════════════════════════════════════════════
#  SUBJECTIVE EXAM — TEACHER: Upload Paper
# ═══════════════════════════════════════════════════════════════

def _extract_text_from_file(file) -> str:
    """Extract plain text from uploaded PDF or DOCX file."""
    filename = file.filename.lower()
    data = file.read()

    if filename.endswith('.pdf'):
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return '\n'.join(text_parts)

    elif filename.endswith('.docx') and DOCX_OK:
        doc = DocxDocument(io.BytesIO(data))
        return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())

    return ''


@app.route('/api/teacher/upload-paper', methods=['POST'])
def apiUploadPaper():
    if session.get('user_role') != 'TEACHER':
        return jsonify({"error": "Unauthorized"}), 403

    uploaded = request.files.get('paper')
    print(f"[upload-paper] files={list(request.files.keys())} uploaded={uploaded}")
    if not uploaded or uploaded.filename == '':
        return jsonify({"error": "No file received. Make sure you selected a file before clicking Extract."}), 400

    fname = uploaded.filename.lower()
    print(f"[upload-paper] filename={fname}")
    if not (fname.endswith('.pdf') or fname.endswith('.docx')):
        return jsonify({"error": f"Unsupported file type '{fname}'. Please upload a PDF or Word (.docx) file."}), 400

    try:
        text = _extract_text_from_file(uploaded)
        print(f"[upload-paper] extracted {len(text)} chars")
    except Exception as e:
        print(f"[upload-paper] extraction error: {e}")
        return jsonify({"error": f"Could not read file: {e}"}), 500

    if not text.strip():
        return jsonify({"error": "No text found in the file. If it's a scanned PDF, please use a text-based PDF or copy-paste questions into a Word document."}), 400

    try:
        questions = grader.extract_questions_from_text(text)
        print(f"[upload-paper] AI returned {len(questions)} questions")
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print(f"[upload-paper] AI error: {e}")
        return jsonify({"error": f"AI extraction failed: {e}"}), 500

    if not questions:
        return jsonify({"error": "AI could not identify any questions in the document. Make sure the file contains clear question text."}), 400

    return jsonify({"questions": questions, "raw_text_preview": text[:500]})


# ═══════════════════════════════════════════════════════════════
#  SUBJECTIVE EXAM — STUDENT: Submit Answers
# ═══════════════════════════════════════════════════════════════

@app.route('/api/exam/subjective/submit', methods=['POST'])
def apiSubjectiveSubmit():
    student_id = session.get('user_id')
    exam_id    = session.get('current_exam_id')
    if not student_id or not exam_id:
        return jsonify({"error": "No active exam session"}), 400

    data    = request.get_json()
    answers = data.get('answers', {})   # {question_index: answer_text}

    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT questions FROM exams WHERE id=%s", (exam_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Exam not found"}), 404

        questions = json.loads(row[0]) if row[0] else []
        student_name = session.get('user_name', '')
        rid = utils.get_resultId()

        # Create submission record
        cur.execute(
            "INSERT INTO submissions (exam_id, student_id, score, total, trust_score, result_json_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (exam_id, student_id, 0, sum(q.get('marks', 5) for q in questions if q.get('type') == 'subjective'),
             100, rid)
        )
        submission_id = cur.lastrowid

        # Save each answer (ungraded — grading runs async)
        for idx, q in enumerate(questions):
            if q.get('type') != 'subjective':
                continue
            ans = answers.get(str(idx), '').strip()
            cur.execute(
                "INSERT INTO subjective_answers "
                "(submission_id, question_index, question_text, student_answer, max_marks) "
                "VALUES (%s, %s, %s, %s, %s)",
                (submission_id, idx, q.get('title', ''), ans, int(q.get('marks', 5)))
            )

        mysql.connection.commit()
        cur.close()

        # Record to result.json
        utils.write_json({
            "Id": rid, "Name": student_name,
            "TotalMark": 0, "TrustScore": 100,
            "Status": "Pending Grading",
            "Date": time.strftime("%Y-%m-%d"),
            "StId": student_id, "Link": ""
        }, "result.json")

        # Trigger async grading
        executor.submit(_grade_submission_async, submission_id, questions, answers)

    except Exception as e:
        print(f"[apiSubjectiveSubmit] error: {e}")
        return jsonify({"error": "Submission failed"}), 500

    return jsonify({"success": True, "submission_id": submission_id,
                    "report_url": f"/exam/report/{submission_id}"})


@app.route('/api/exam/mixed/submit', methods=['POST'])
def apiMixedSubmit():
    """Submit a mixed exam: score MCQ immediately, grade subjective async."""
    student_id = session.get('user_id')
    exam_id    = session.get('current_exam_id')
    if not student_id or not exam_id:
        return jsonify({"error": "No active exam session"}), 400

    data        = request.get_json()
    mcq_answers = data.get('mcq_answers', {})   # {q_index: choice_index (int or None)}
    subj_answers = data.get('subj_answers', {}) # {q_index: answer_text}

    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT questions FROM exams WHERE id=%s", (exam_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Exam not found"}), 404

        questions    = json.loads(row[0]) if row[0] else []
        student_name = session.get('user_name', '')
        rid          = utils.get_resultId()

        # Score MCQ questions
        mcq_correct = 0
        mcq_total   = 0
        for i, q in enumerate(questions):
            if q.get('type') != 'mcq':
                continue
            mcq_total += 1
            chosen_idx = mcq_answers.get(str(i))
            if chosen_idx is not None:
                try:
                    chosen_answer = q['choices'][int(chosen_idx)]
                    if chosen_answer == q.get('answer', ''):
                        mcq_correct += 1
                except (IndexError, TypeError, ValueError):
                    pass

        subj_total = sum(int(q.get('marks', 5)) for q in questions if q.get('type') == 'subjective')
        total_marks = mcq_total + subj_total

        # Create submission record with MCQ score as initial score
        cur.execute(
            "INSERT INTO submissions (exam_id, student_id, score, total, trust_score, result_json_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (exam_id, student_id, mcq_correct, total_marks, 100, rid)
        )
        submission_id = cur.lastrowid

        # Save subjective answers (ungraded)
        for idx, q in enumerate(questions):
            if q.get('type') != 'subjective':
                continue
            ans = subj_answers.get(str(idx), '').strip()
            cur.execute(
                "INSERT INTO subjective_answers "
                "(submission_id, question_index, question_text, student_answer, max_marks) "
                "VALUES (%s, %s, %s, %s, %s)",
                (submission_id, idx, q.get('title', ''), ans, int(q.get('marks', 5)))
            )

        mysql.connection.commit()
        cur.close()

        utils.write_json({
            "Id": rid, "Name": student_name,
            "TotalMark": mcq_correct, "TrustScore": 100,
            "Status": "Pending Grading",
            "Date": time.strftime("%Y-%m-%d"),
            "StId": student_id, "Link": ""
        }, "result.json")

        # Async grade subjective section
        executor.submit(_grade_submission_async, submission_id, questions, subj_answers)

    except Exception as e:
        print(f"[apiMixedSubmit] error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Submission failed"}), 500

    return jsonify({"success": True, "submission_id": submission_id,
                    "mcq_score": mcq_correct, "mcq_total": mcq_total,
                    "report_url": f"/exam/report/{submission_id}"})


def _grade_submission_async(submission_id: int, questions: list, answers: dict):
    """Background thread: grade all subjective answers and update DB."""
    import MySQLdb, time
    db = None
    with app.app_context():
        try:
            t0 = time.time()
            n  = len([q for q in questions if q.get('type') == 'subjective'])
            print(f"[grader] START submission {submission_id} — {n} question(s)")

            results = grader.grade_submission(questions, answers)

            print(f"[grader] AI grading done in {time.time()-t0:.1f}s — writing to DB")

            db = MySQLdb.connect(
                host='localhost', user='root', password='admin',
                db='examproctordb', port=3307, charset='utf8mb4'
            )
            cur = db.cursor()
            total_score = 0.0
            for r in results:
                print(f"[grader]   Q{r['question_index']} score={r['score']} "
                      f"sem={r.get('semantic_score',0)}% "
                      f"matched_kw={len(r.get('matching_keywords',[]))}")
                cur.execute(
                    "UPDATE subjective_answers "
                    "SET ai_score=%s, ai_feedback=%s, ideal_answer=%s, "
                    "solution=%s, correct_points=%s, mistakes=%s, "
                    "matching_keywords=%s, missing_keywords=%s, semantic_score=%s, graded=1 "
                    "WHERE submission_id=%s AND question_index=%s",
                    (r['score'], r['feedback'], r['ideal_answer'],
                     r.get('solution', ''),
                     json.dumps(r.get('correct_points', [])),
                     json.dumps(r.get('mistakes', [])),
                     json.dumps(r.get('matching_keywords', [])),
                     json.dumps(r.get('missing_keywords', [])),
                     r.get('semantic_score', 0),
                     submission_id, r['question_index'])
                )
                total_score += r['score']

            cur.execute("UPDATE submissions SET score=%s WHERE id=%s",
                        (round(total_score), submission_id))
            db.commit()
            cur.close()
            print(f"[grader] DONE submission {submission_id} in {time.time()-t0:.1f}s  total={total_score}")
        except Exception as e:
            import traceback
            print(f"[grader] async grading error: {e}")
            traceback.print_exc()
        finally:
            if db:
                db.close()


# ═══════════════════════════════════════════════════════════════
#  SUBJECTIVE EXAM — TEACHER: View Graded Results
# ═══════════════════════════════════════════════════════════════

@app.route('/api/teacher/exam/<int:exam_id>/subjective-results')
def apiSubjectiveResults(exam_id):
    if session.get('user_role') != 'TEACHER':
        return jsonify({"error": "Unauthorized"}), 403
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT s.id, st.Name, s.submitted_at,
                   sa.question_index, sa.question_text, sa.student_answer,
                   sa.ai_score, sa.ai_feedback, sa.ideal_answer, sa.max_marks, sa.graded
            FROM submissions s
            JOIN students st ON s.student_id = st.ID
            JOIN subjective_answers sa ON sa.submission_id = s.id
            WHERE s.exam_id = %s
            ORDER BY s.submitted_at DESC, sa.question_index
        """, (exam_id,))
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"[apiSubjectiveResults] error: {e}")
        return jsonify([])

    # Group by submission
    subs = {}
    for row in rows:
        sid, name, sub_at, qidx, qtxt, ans, score, feedback, ideal, marks, graded = row
        if sid not in subs:
            subs[sid] = {"submission_id": sid, "student_name": name,
                         "submitted_at": str(sub_at), "answers": []}
        subs[sid]["answers"].append({
            "question_index": qidx, "question": qtxt, "student_answer": ans,
            "ai_score": score, "ai_feedback": feedback,
            "ideal_answer": ideal, "max_marks": marks, "graded": bool(graded)
        })

    return jsonify(list(subs.values()))


# ═══════════════════════════════════════════════════════════════
#  STUDENT ANALYSIS REPORT
# ═══════════════════════════════════════════════════════════════

@app.route('/exam/report/<int:submission_id>')
def examReport(submission_id):
    if not session.get('user_id'):
        return redirect(url_for('main'))
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT question_index, question_text, student_answer, "
            "ideal_answer, solution, correct_points, mistakes, "
            "matching_keywords, missing_keywords, semantic_score, graded, max_marks "
            "FROM subjective_answers WHERE submission_id=%s ORDER BY question_index",
            (submission_id,)
        )
        rows = cur.fetchall()
        cur.execute("""SELECT e.title, s.score, s.total,
                              (SELECT COUNT(*) FROM subjective_answers WHERE submission_id=%s) as subj_count
                       FROM submissions s JOIN exams e ON s.exam_id=e.id WHERE s.id=%s""",
                    (submission_id, submission_id))
        exam_row = cur.fetchone()
        cur.close()
    except Exception as e:
        print(f"[examReport] DB error: {e}")
        rows = []
        exam_row = None

    answers = []
    total_score = 0.0
    total_marks = 0
    for row in rows:
        qidx, qtxt, stud_ans, ideal, solution, cp_json, mis_json, mk_json, missing_json, sem_score, graded, max_marks = row
        # fetch ai_score too for totals
        answers.append({
            "index":            qidx + 1,
            "question":         qtxt or "",
            "student_answer":   stud_ans or "",
            "solution":         solution or ideal or "",
            "correct_points":   json.loads(cp_json)      if cp_json      else [],
            "mistakes":         json.loads(mis_json)     if mis_json     else [],
            "matching_keywords":json.loads(mk_json)      if mk_json      else [],
            "missing_keywords": json.loads(missing_json) if missing_json else [],
            "semantic_score":   float(sem_score or 0),
            "graded":           bool(graded),
            "max_marks":        int(max_marks or 0),
        })
        total_marks += int(max_marks or 0)

    # fetch scores separately for total
    try:
        cur2 = mysql.connection.cursor()
        cur2.execute("SELECT SUM(ai_score) FROM subjective_answers WHERE submission_id=%s", (submission_id,))
        s = cur2.fetchone()[0]
        total_score = round(float(s or 0), 1)
        cur2.close()
    except Exception:
        total_score = 0.0

    exam_title   = exam_row[0] if exam_row else "Exam"
    student_name = session.get('user_name', 'Student')
    # For mixed exams: submission score includes MCQ portion already saved
    mcq_score  = int(exam_row[1] or 0) - int(round(total_score)) if exam_row and exam_row[3] else 0
    mcq_score  = max(0, mcq_score)
    is_mixed   = bool(exam_row and exam_row[3] and mcq_score > 0)
    return render_template('ExamReport.html',
                           answers=answers,
                           exam_title=exam_title,
                           student_name=student_name,
                           submission_id=submission_id,
                           total_score=total_score,
                           total_marks=total_marks,
                           mcq_score=mcq_score,
                           is_mixed=is_mixed)


@app.route('/api/exam/report/<int:submission_id>/status')
def examReportStatus(submission_id):
    """Poll endpoint — returns grading progress."""
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*), SUM(graded) FROM subjective_answers WHERE submission_id=%s",
                    (submission_id,))
        total, done = cur.fetchone()
        cur.close()
        return jsonify({"total": total or 0, "graded": int(done or 0),
                        "ready": (total and total == done)})
    except Exception:
        return jsonify({"total": 0, "graded": 0, "ready": False})


if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
