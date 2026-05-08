"""
utils.py — ProctorAI Detection Engine
======================================
Models (best available, graceful fallback):
  Face Detection:    MediaPipe BlazeFace  →  Haar Cascade
  Face Recognition:  OpenCV SFace ONNX   →  ORB matching
  Head Pose:         MediaPipe FaceMesh solvePnP
  Iris Gaze:         MediaPipe FaceMesh refine_landmarks (bundled)
  Drowsiness (EAR):  MediaPipe FaceMesh refine_landmarks (bundled)
  Object Detection:  YOLOv8n ONNX        →  YOLOv8n PyTorch
  Audio VAD:         Adaptive RMS via sounddevice
  Alerts:            Flask-SocketIO push  →  polling fallback
Database: MySQL · host: localhost · port: 3307 · db: examproctordb
"""

import sys, cv2, numpy as np, time, math, random, os, json, shutil
import keyboard, pyautogui, pygetwindow as gw, webbrowser, pyperclip
import threading, sounddevice as sd, struct, wave, datetime, subprocess
from concurrent.futures import ThreadPoolExecutor
import mediapipe as mp
from ultralytics import YOLO

# ─────────────────────────── ONNX Runtime (optional) ──────────────────────────
try:
    import onnxruntime as ort
    ort.set_default_logger_severity(3)
    _ORT_OK = True
except ImportError:
    _ORT_OK = False
    print("INFO: onnxruntime not found — ONNX models disabled.")

# ─────────────────────────── Model paths ──────────────────────────────────────
_MODELS = os.path.join(os.path.dirname(__file__), 'models')
_YUNET_PATH  = os.path.join(_MODELS, 'face_detection_yunet_2023mar.onnx')
_SFACE_PATH  = os.path.join(_MODELS, 'face_recognition_sface_2021dec_int8.onnx')
_YOLO_ONNX   = os.path.join(_MODELS, 'yolov8n.onnx')

# ─────────────────────────── Face Detection — YuNet ──────────────────────────
_yunet = None
if os.path.exists(_YUNET_PATH):
    try:
        _yunet = cv2.FaceDetectorYN.create(
            _YUNET_PATH, '', (320, 320),
            score_threshold=0.55, nms_threshold=0.3, top_k=5000
        )
        print("INFO: YuNet face detector loaded.")
    except Exception as e:
        print(f"WARNING: YuNet load failed ({e}) — using Haar fallback.")

# Haar fallback (always available)
_haar = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
print("INFO: Haar cascade ready as fallback.")

# ─────────────────────────── Face Recognition — SFace ────────────────────────
_sface = None
if os.path.exists(_SFACE_PATH):
    try:
        _sface = cv2.FaceRecognizerSF.create(_SFACE_PATH, '')
        print("INFO: SFace face recognizer loaded (replaces ORB).")
    except Exception as e:
        print(f"WARNING: SFace load failed ({e}) — using ORB fallback.")

# ─────────────────────────── Object Detection — ONNX / PyTorch ───────────────
_yolo_ort_session = None
if _ORT_OK and os.path.exists(_YOLO_ONNX):
    try:
        _yolo_ort_session = ort.InferenceSession(_YOLO_ONNX, providers=['CPUExecutionProvider'])
        print("INFO: YOLOv8n ONNX loaded (faster than PyTorch).")
    except Exception as e:
        print(f"WARNING: YOLO ONNX failed ({e}) — using PyTorch fallback.")

# PyTorch YOLO loaded in background — used if ONNX not available
_yolo_pt = None
def _load_yolo_pt():
    global _yolo_pt
    if _yolo_ort_session:
        return  # ONNX is already available, skip PyTorch
    try:
        _yolo_pt = YOLO("yolov8n.pt", "v8")
        print("INFO: YOLOv8n PyTorch loaded.")
    except Exception as e:
        print(f"WARNING: YOLOv8n PyTorch failed: {e}")
threading.Thread(target=_load_yolo_pt, daemon=True).start()

# ─────────────────────────── MediaPipe Tasks API ─────────────────────────────
_mp_face_det  = None   # FaceDetector (Tasks API)
_mp_landmarker = None  # FaceLandmarker (Tasks API, replaces FaceMesh)

_BLAZE_PATH = os.path.join(_MODELS, 'blaze_face_short_range.tflite')
_LAND_PATH  = os.path.join(_MODELS, 'face_landmarker.task')

try:
    from mediapipe.tasks import python as _mp_py
    from mediapipe.tasks.python import vision as _mp_vis

    if os.path.exists(_BLAZE_PATH):
        _mp_face_det = _mp_vis.FaceDetector.create_from_options(
            _mp_vis.FaceDetectorOptions(
                base_options=_mp_py.BaseOptions(model_asset_path=_BLAZE_PATH),
                running_mode=_mp_vis.RunningMode.IMAGE,
                min_detection_confidence=0.55,
            )
        )
        print("INFO: MediaPipe FaceDetector (Tasks API) loaded.")

    if os.path.exists(_LAND_PATH):
        _mp_landmarker = _mp_vis.FaceLandmarker.create_from_options(
            _mp_vis.FaceLandmarkerOptions(
                base_options=_mp_py.BaseOptions(model_asset_path=_LAND_PATH),
                running_mode=_mp_vis.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
            )
        )
        print("INFO: MediaPipe FaceLandmarker (Tasks API) loaded.")
except Exception as e:
    print(f"WARNING: MediaPipe Tasks init failed ({e}) — Haar/YuNet will be used.")

# ─────────────────────────── COCO classes banned during exam ─────────────────
BANNED_CLASSES = {
    'cell phone', 'remote', 'laptop', 'book', 'mouse', 'keyboard',
    'tv', 'backpack', 'handbag',
}
# YOLOv8 COCO class IDs for the above (for ONNX path)
_BANNED_IDS = {
    67: 'cell phone', 63: 'laptop', 73: 'book',
    65: 'remote',     62: 'tv',     74: 'device',
    24: 'backpack',   26: 'handbag', 64: 'mouse', 66: 'keyboard',
}

# ─────────────────────────── Global state ─────────────────────────────────────
Globalflag      = False
Student_Name    = ''
_audio_violation_logged = False   # fire audio violation only once per exam session
monitoring_status = {
    "face_detected":    False,
    "face_count":       0,
    "gaze_direction":   "Forward",
    "eye_state":        "Open",
    "object_detected":  False,
    "object_name":      "",
    "identity_ok":      True,
    "violations_count": 0,
    "active":           False,
    "last_alert":       "",
    "last_alert_time":  0,   # epoch seconds — UI clears after 8s
}

start_time        = [0, 0, 0, 0, 0]
end_time          = [0, 0, 0, 0, 0]
recorded_durations = []
prev_state = [
    'Verified Student appeared',
    "Forward",
    "Only one person is detected",
    "Stay in the Test",
    "No Electronic Device Detected",
]
flag = [False, False, False, False, False]

# Shared camera frame
latest_frame    = None
frame_lock      = threading.Lock()
_camera_started = False

# No video recording — violations logged to JSON only
video  = ['', '', '', '', '']
writer = [None, None, None, None, None]

# Shortcuts caught during exam
shorcuts = []
active_window_title = "Exam — Mozilla Firefox"
exam_window_title   = active_window_title
active_window       = None

# ─────────────────────────── Socket.IO callback ───────────────────────────────
_violation_callback = None  # set by app.py after SocketIO init

def set_violation_callback(fn):
    global _violation_callback
    _violation_callback = fn

def _push_violation(name, detail=""):
    """Emit a violation event via SocketIO and stamp last_alert_time."""
    monitoring_status["last_alert"]      = f"{name}"
    monitoring_status["last_alert_time"] = time.time()
    if _violation_callback:
        try:
            _violation_callback(name, detail)
        except Exception:
            pass

# ─────────────────────────── Audio constants ──────────────────────────────────
TRIGGER_RMS    = 10
RATE           = 16000
TIMEOUT_SECS   = 3
FRAME_SECS     = 0.25
CUSHION_SECS   = 1
SHORT_NORMALIZE = (1.0 / 32768.0)
CHANNELS       = 1
SHORT_WIDTH    = 2
CHUNK          = int(RATE * FRAME_SECS)
CUSHION_FRAMES = int(CUSHION_SECS / FRAME_SECS)
TIMEOUT_FRAMES = int(TIMEOUT_SECS / FRAME_SECS)
f_name_directory = os.path.join(os.getcwd(), 'static', 'OutputAudios')
os.makedirs(f_name_directory, exist_ok=True)
cap = None

# Adaptive noise floor for audio VAD
_noise_floor  = 0.0
_noise_alpha  = 0.01  # slow adaptation rate

# ─────────────────────────── COCO class list (for legacy path) ────────────────
try:
    with open("utils/coco.txt", "r") as _f:
        class_list = _f.read().split("\n")
except FileNotFoundError:
    class_list = []

# ═══════════════════════════════════════════════════════════════════════════════
#  CAMERA READER
# ═══════════════════════════════════════════════════════════════════════════════

def start_camera_reader():
    global cap, latest_frame, _camera_started
    if _camera_started:
        return
    _camera_started = True
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)

    def _loop():
        global latest_frame
        while True:
            if cap and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    with frame_lock:
                        latest_frame = frame.copy()
            time.sleep(0.033)  # ~30 fps

    threading.Thread(target=_loop, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════════════════
#  FACE DETECTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_faces_blazeface(bgr):
    """Returns number of faces using MediaPipe FaceDetector (Tasks API)."""
    if _mp_face_det is None:
        return None
    try:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = _mp_face_det.detect(mp_image)
        return len(res.detections) if res.detections else 0
    except Exception:
        return None

def _detect_faces_haar(bgr):
    """Haar cascade fallback."""
    gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    faces = _haar.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
    return len(faces)

def count_faces(bgr):
    """Best available face count."""
    n = _detect_faces_blazeface(bgr)
    return n if n is not None else _detect_faces_haar(bgr)

# ═══════════════════════════════════════════════════════════════════════════════
#  GAZE / HEAD POSE / DROWSINESS  (MediaPipe FaceMesh)
# ═══════════════════════════════════════════════════════════════════════════════

# Eye landmark indices for EAR (Eye Aspect Ratio)
_LEFT_EYE  = [33,  160, 158, 133, 153, 144]
_RIGHT_EYE = [362, 385, 387, 263, 373, 380]
_EAR_THRESH         = 0.21   # below this = eyes closed
_EAR_CLOSED_FRAMES  = 15     # ~1.5s at 10fps → drowsiness violation

_eye_closed_counter = 0

def _ear(lm, indices, w, h):
    """Eye Aspect Ratio — close to 0 = eyes shut."""
    pts = [(lm[i].x * w, lm[i].y * h) for i in indices]
    A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    return (A + B) / (2.0 * C + 1e-6)

def _iris_gaze(lm, w):
    """
    Iris-based gaze: where the eyes are actually pointing.
    Landmarks 468/473 = iris centers (requires refine_landmarks=True).
    Returns 'center', 'Looking Left (Eyes)', or 'Looking Right (Eyes)'.
    """
    try:
        def px(i): return lm[i].x * w
        lr  = (px(468) - px(33))  / (px(133) - px(33)  + 1e-6)
        rr  = (px(473) - px(362)) / (px(263) - px(362) + 1e-6)
        avg = (lr + rr) / 2.0
        if avg < 0.35:
            return 'Looking Left (Eyes)'
        if avg > 0.65:
            return 'Looking Right (Eyes)'
        return 'center'
    except (IndexError, ZeroDivisionError):
        return 'center'


def headMovmentDetection(image):
    """
    Full head analysis per frame:
      1. 3D head pose via solvePnP (where head points)
      2. Iris gaze (where eyes look — catches sideways glancing)
      3. EAR drowsiness (eyes closed too long)
    Returns the final direction string.
    """
    global _eye_closed_counter

    if _mp_landmarker is None:
        return "Forward"

    # Flip for selfie-mirror so solvePnP y-angle matches intuitive left/right
    flipped = cv2.flip(image, 1)
    rgb = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    results = _mp_landmarker.detect(mp_image)

    img_h, img_w = image.shape[:2]
    textHead = "Forward"

    if results.face_landmarks:
        lm = results.face_landmarks[0]

        # ── 3D head pose (solvePnP) ──
        face_2d, face_3d = [], []
        for idx, pt in enumerate(lm):
            if idx in (33, 263, 1, 61, 291, 199):
                x, y = int(pt.x * img_w), int(pt.y * img_h)
                face_2d.append([x, y])
                face_3d.append([x, y, pt.z])

        face_2d = np.array(face_2d, dtype=np.float64)
        face_3d = np.array(face_3d, dtype=np.float64)
        focal   = img_w
        cam_mat = np.array([[focal, 0, img_h/2],[0, focal, img_w/2],[0, 0, 1]])
        dist    = np.zeros((4, 1), dtype=np.float64)

        ok, rvec, _ = cv2.solvePnP(face_3d, face_2d, cam_mat, dist)
        rmat, _     = cv2.Rodrigues(rvec)
        angles, *_  = cv2.RQDecomp3x3(rmat)
        x_ang, y_ang = angles[0] * 360, angles[1] * 360

        if   y_ang < -10: textHead = "Looking Left"
        elif y_ang >  15: textHead = "Looking Right"
        elif x_ang <  -8: textHead = "Looking Down"
        elif x_ang >  15: textHead = "Looking Up"
        else:             textHead = "Forward"

        # ── Iris gaze (override if head is forward but eyes drift) ──
        if textHead == "Forward":
            iris = _iris_gaze(lm, img_w)
            if iris != 'center':
                textHead = iris

        # ── EAR drowsiness ──
        try:
            ear_val = (_ear(lm, _LEFT_EYE, img_w, img_h) +
                       _ear(lm, _RIGHT_EYE, img_w, img_h)) / 2.0
            if ear_val < _EAR_THRESH:
                _eye_closed_counter += 1
                monitoring_status["eye_state"] = "Closed"
                if _eye_closed_counter >= _EAR_CLOSED_FRAMES:
                    Head_record_duration("Eyes Closed (Drowsy)", image)
                    monitoring_status["last_alert"] = "Drowsiness detected — eyes closed"
                    _push_violation("Eyes Closed", "Student may be drowsy or looking down")
                    _eye_closed_counter = 0
                    return "Eyes Closed"
            else:
                _eye_closed_counter = 0
                monitoring_status["eye_state"] = "Open"
        except (IndexError, Exception):
            pass

    monitoring_status["gaze_direction"] = textHead
    if textHead not in ("Forward", "center"):
        monitoring_status["last_alert"] = f"Head: {textHead}"
    Head_record_duration(textHead, image)
    return textHead

# ═══════════════════════════════════════════════════════════════════════════════
#  JSON / FILE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def write_json(new_data, filename='violation.json'):
    with open(filename, 'r+') as f:
        data = json.load(f)
        data.append(new_data)
        f.seek(0)
        json.dump(data, f, indent=4)

def move_file_to_output_folder(file_name, folder_name='OutputVideos'):
    src = os.path.join(os.getcwd(), file_name)
    dst = os.path.join(os.getcwd(), 'static', folder_name, file_name)
    try:
        shutil.move(src, dst)
    except (FileNotFoundError, shutil.Error) as e:
        print(f"[move_file] {e}")

def reduceBitRate(input_file, output_file):
    ffmpeg = "E:/ffmpeg/ffmpeg-2025-06-08-git-5fea5e3e11-full_build/bin/ffmpeg.exe"
    subprocess.run([ffmpeg, "-i", input_file, "-b:v", "1000k",
                    "-c:v", "libx264", "-c:a", "aac",
                    "-strict", "experimental", "-b:a", "192k", output_file],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def deleteTrashVideos():
    for fn in os.listdir(os.getcwd()):
        if fn.lower().endswith('.mp4'):
            try:
                os.remove(os.path.join(os.getcwd(), fn))
            except OSError:
                pass

# ═══════════════════════════════════════════════════════════════════════════════
#  VIOLATION RECORDING  (unchanged API, adds SocketIO push)
# ═══════════════════════════════════════════════════════════════════════════════

def faceDetectionRecording(img, text):
    global start_time, end_time, recorded_durations, prev_state, flag
    monitoring_status["face_detected"] = (text == "Verified Student appeared")
    monitoring_status["identity_ok"]   = (text == "Verified Student appeared")
    if text != "Verified Student appeared":
        monitoring_status["last_alert"] = "Identity mismatch or face not visible"

    if text != 'Verified Student appeared' and prev_state[0] == 'Verified Student appeared':
        start_time[0] = time.time()
    elif text != 'Verified Student appeared' and text == prev_state[0] and (time.time() - start_time[0]) > 3:
        flag[0] = True
    elif text != 'Verified Student appeared' and text == prev_state[0] and (time.time() - start_time[0]) <= 3:
        flag[0] = False
    else:
        if prev_state[0] != "Verified Student appeared":
            end_time[0] = time.time()
            dur = math.ceil((end_time[0] - start_time[0]) / 3)
            v = {"Name": prev_state[0],
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[0])),
                 "Duration": f"{dur} seconds", "Mark": math.floor(2 * dur),
                 "Link": "", "RId": get_resultId()}
            if flag[0]:
                recorded_durations.append(v)
                write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = "Violation: " + v["Name"]
                _push_violation(v["Name"], f"Duration: {dur}s")
            flag[0] = False
    prev_state[0] = text


def Head_record_duration(text, _img):
    global start_time, end_time, recorded_durations, prev_state, flag
    if text != "Forward":
        if text != prev_state[1] and prev_state[1] == "Forward":
            start_time[1] = time.time()
        elif text != prev_state[1] and prev_state[1] != "Forward":
            end_time[1] = time.time()
            dur = math.ceil((end_time[1] - start_time[1]) / 7)
            v = {"Name": prev_state[1],
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[1])),
                 "Duration": f"{dur} seconds", "Mark": dur,
                 "Link": "", "RId": get_resultId()}
            if flag[1]:
                recorded_durations.append(v); write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = "Violation: " + v["Name"]
                _push_violation(v["Name"], f"Duration: {dur}s")
            start_time[1] = time.time(); flag[1] = False
        elif text == prev_state[1] and (time.time() - start_time[1]) > 3:
            flag[1] = True
        elif text == prev_state[1] and (time.time() - start_time[1]) <= 3:
            flag[1] = False
        prev_state[1] = text
    else:
        if prev_state[1] != "Forward":
            end_time[1] = time.time()
            dur = math.ceil((end_time[1] - start_time[1]) / 7)
            v = {"Name": prev_state[1],
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[1])),
                 "Duration": f"{dur} seconds", "Mark": dur,
                 "Link": "", "RId": get_resultId()}
            if flag[1]:
                recorded_durations.append(v); write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = "Violation: " + v["Name"]
                _push_violation(v["Name"], f"Duration: {dur}s")
            flag[1] = False
        prev_state[1] = text


def MTOP_record_duration(text, _img):
    global start_time, end_time, recorded_durations, prev_state, flag
    if text != 'Only one person is detected' and prev_state[2] == 'Only one person is detected':
        start_time[2] = time.time()
    elif text != 'Only one person is detected' and text == prev_state[2] and (time.time() - start_time[2]) > 3:
        flag[2] = True
    elif text != 'Only one person is detected' and text == prev_state[2] and (time.time() - start_time[2]) <= 3:
        flag[2] = False
    else:
        if prev_state[2] != "Only one person is detected":
            end_time[2] = time.time()
            dur = math.ceil((end_time[2] - start_time[2]) / 3)
            v = {"Name": prev_state[2],
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[2])),
                 "Duration": f"{dur} seconds", "Mark": math.floor(1.5 * dur),
                 "Link": "", "RId": get_resultId()}
            if flag[2]:
                recorded_durations.append(v); write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = "Violation: Multiple persons detected"
                _push_violation("Multiple Persons", f"Duration: {dur}s")
            flag[2] = False
    prev_state[2] = text


def SD_record_duration(text, _img):
    global start_time, end_time, prev_state, flag
    if text != "Stay in the Test" and prev_state[3] == "Stay in the Test":
        start_time[3] = time.time()
    elif text != "Stay in the Test" and text == prev_state[3] and (time.time() - start_time[3]) > 3:
        flag[3] = True
    elif text != "Stay in the Test" and text == prev_state[3] and (time.time() - start_time[3]) <= 3:
        flag[3] = False
    else:
        if prev_state[3] != "Stay in the Test":
            end_time[3] = time.time()
            dur = math.ceil((end_time[3] - start_time[3]) / 4)
            v = {"Name": prev_state[3],
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[3])),
                 "Duration": f"{dur} seconds", "Mark": 2 * dur,
                 "Link": "", "RId": get_resultId()}
            if flag[3]:
                recorded_durations.append(v); write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = "Violation: Tab/window switched"
                _push_violation("Window Switch", f"Switched to: {prev_state[3]}")
            flag[3] = False
    prev_state[3] = text


def EDD_record_duration(text, _img):
    global start_time, end_time, prev_state, flag
    if text == "Electronic Device Detected" and prev_state[4] == "No Electronic Device Detected":
        start_time[4] = time.time()
    elif text == "Electronic Device Detected" and text == prev_state[4] and (time.time() - start_time[4]) > 3:
        flag[4] = True
    elif text == "Electronic Device Detected" and text == prev_state[4] and (time.time() - start_time[4]) <= 3:
        flag[4] = False
    else:
        if prev_state[4] == "Electronic Device Detected":
            end_time[4] = time.time()
            dur  = math.ceil((end_time[4] - start_time[4]) / 10)
            name = "Electronic Device: " + monitoring_status.get("object_name", "unknown")
            v = {"Name": name,
                 "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time[4])),
                 "Duration": f"{dur} seconds", "Mark": math.floor(1.5 * dur),
                 "Link": "", "RId": get_resultId()}
            if flag[4]:
                write_json(v)
                monitoring_status["violations_count"] += 1
                monitoring_status["last_alert"] = f"Violation: {name}"
                _push_violation(name, f"Duration: {dur}s")
            flag[4] = False
    prev_state[4] = text

# ═══════════════════════════════════════════════════════════════════════════════
#  MULTI-PERSON DETECTION  (BlazeFace → Haar fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def MTOP_Detection(img):
    n = count_faces(img)
    monitoring_status["face_count"] = n
    textMTOP = "Only one person is detected" if n <= 1 else "More than one person is detected."
    if n > 1:
        monitoring_status["last_alert"] = "Multiple persons detected"
    MTOP_record_duration(textMTOP, img)

# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN / SHORTCUT DETECTION  (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

def capture_screen():
    frame = np.array(pyautogui.screenshot())
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

def shortcut_handler(event):
    if event.event_type != keyboard.KEY_DOWN:
        return
    shortcut = ''
    pairs = [
        ('ctrl','c','Ctrl+C'), ('ctrl','v','Ctrl+V'), ('ctrl','a','Ctrl+A'),
        ('ctrl','x','Ctrl+X'), ('ctrl','t','Ctrl+T'), ('ctrl','w','Ctrl+W'),
        ('ctrl','z','Ctrl+Z'),
    ]
    for mod, key, label in pairs:
        if keyboard.is_pressed(mod) and keyboard.is_pressed(key):
            shortcut = label; break
    if not shortcut:
        for key, label in [('f1','F1'),('f2','F2'),('f3','F3'),
                            ('print_screen','Prt Scn'),('win','Window')]:
            if keyboard.is_pressed(key):
                shortcut = label; break
    if not shortcut:
        if keyboard.is_pressed('alt') and keyboard.is_pressed('tab'):
            shortcut = 'Alt+Tab'
        elif keyboard.is_pressed('alt') and keyboard.is_pressed('esc'):
            shortcut = 'Alt+Esc'
        elif keyboard.is_pressed('ctrl') and keyboard.is_pressed('esc'):
            shortcut = 'Ctrl+Esc'
    if shortcut:
        shorcuts.append(shortcut)

def screenDetection():
    global active_window, active_window_title, exam_window_title
    new_win = gw.getActiveWindow()
    frame   = capture_screen()
    if new_win and new_win.title != exam_window_title:
        if new_win.title != active_window_title:
            active_window       = new_win
            active_window_title = new_win.title
        SD_record_duration("Move away from the Test", frame)
    else:
        SD_record_duration("Stay in the Test", frame)

# ═══════════════════════════════════════════════════════════════════════════════
#  OBJECT DETECTION  (ONNX → PyTorch fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_objects_onnx(bgr):
    """YOLOv8n ONNX inference — ~2× faster than PyTorch on CPU."""
    inp_name = _yolo_ort_session.get_inputs()[0].name
    img = cv2.resize(bgr, (416, 416)).astype(np.float32) / 255.0
    inp = img.transpose(2, 0, 1)[np.newaxis]
    preds = _yolo_ort_session.run(None, {inp_name: inp})[0][0]  # (84, N)
    found = set()
    for det in preds.T:
        x, y, w, h = det[:4]
        scores = det[4:]
        cls_id = int(np.argmax(scores))
        conf   = float(scores[cls_id])
        if conf >= 0.35 and cls_id in _BANNED_IDS:
            if cls_id == 67 and conf < 0.40:  # phone needs higher threshold
                continue
            found.add(_BANNED_IDS[cls_id])
    return list(found)


def _detect_objects_pytorch(bgr):
    """YOLOv8n PyTorch fallback."""
    if _yolo_pt is None:
        return []
    results = _yolo_pt.predict(source=[bgr], conf=0.35, save=False, verbose=False)
    found = []
    for r in results:
        for box in r.boxes.cpu().numpy():
            name = r.names[int(box.cls[0])]
            if name in BANNED_CLASSES:
                found.append(name)
    return list(set(found))


def electronicDevicesDetection(frame):
    try:
        objs = (_detect_objects_onnx(frame) if _yolo_ort_session
                else _detect_objects_pytorch(frame))
        if objs:
            name = objs[0]
            monitoring_status["object_detected"] = True
            monitoring_status["object_name"]     = name
            monitoring_status["last_alert"]      = f"Banned object: {name}"
            EDD_record_duration("Electronic Device Detected", frame)
        else:
            monitoring_status["object_detected"] = False
            monitoring_status["object_name"]     = ""
            EDD_record_duration("No Electronic Device Detected", frame)
    except Exception as e:
        print(f"[YOLO] {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#  FACE RECOGNITION  (SFace ONNX → ORB fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def face_confidence(face_distance, face_match_threshold=0.6):
    r = (1.0 - face_match_threshold)
    linear = (1.0 - face_distance) / (r * 2.0)
    if face_distance > face_match_threshold:
        return str(round(linear * 100, 2)) + '%'
    v = (linear + ((1.0 - linear) * math.pow((linear - 0.5) * 2, 0.2))) * 100
    return str(round(v, 2)) + '%'


class FaceRecognition:
    """
    Identity verification.
    Uses OpenCV SFace (ONNX, cosine similarity) when available,
    falls back to ORB feature matching.
    """
    known_face_encodings = []
    known_face_names     = []
    _use_sface           = (_sface is not None)

    def __init__(self):
        self.encode_faces()

    def encode_faces(self):
        self.known_face_encodings = []
        self.known_face_names     = []
        profiles_dir = 'static/Profiles'
        if not os.path.exists(profiles_dir):
            return

        if self._use_sface:
            self._encode_sface(profiles_dir)
        else:
            self._encode_orb(profiles_dir)
        print(f"[FaceRecognition] Loaded {len(self.known_face_names)} profiles "
              f"({'SFace' if self._use_sface else 'ORB'}).")

    def _encode_sface(self, profiles_dir):
        """SFace: store aligned face crops for feature extraction at match time."""
        for fn in os.listdir(profiles_dir):
            img = cv2.imread(os.path.join(profiles_dir, fn))
            if img is None:
                continue
            # Detect face region with Haar for alignment crop
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = _haar.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            if not len(faces):
                continue
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            # Build a YuNet-style bbox row: [x,y,w,h, ..., score]
            bbox = np.array([[x, y, w, h, 0,0,0,0,0,0,0,0,0,0, 1.0]], dtype=np.float32)
            try:
                aligned = _sface.alignCrop(img, bbox[0])
                feat    = _sface.feature(aligned)
                self.known_face_encodings.append(feat)
                self.known_face_names.append(fn)
            except Exception:
                pass

    def _encode_orb(self, profiles_dir):
        orb = cv2.ORB_create()
        for fn in os.listdir(profiles_dir):
            img = cv2.imread(os.path.join(profiles_dir, fn), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            _, des = orb.detectAndCompute(img, None)
            if des is not None:
                self.known_face_encodings.append(des)
                self.known_face_names.append(fn)

    def run_recognition(self):
        global Globalflag
        if self._use_sface:
            self._run_sface()
        else:
            self._run_orb()

    def _run_sface(self):
        global Globalflag
        while True:
            if not Globalflag:
                time.sleep(0.2); continue
            with frame_lock:
                frame = latest_frame.copy() if latest_frame is not None else None
            if frame is None:
                time.sleep(0.05); continue

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = _haar.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            text  = "Verified Student disappeared"

            if len(faces) > 0 and self.known_face_encodings:
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                bbox = np.array([x, y, w, h, 0,0,0,0,0,0,0,0,0,0, 1.0], dtype=np.float32)
                try:
                    aligned   = _sface.alignCrop(frame, bbox)
                    feat_live = _sface.feature(aligned)
                    best      = max(
                        _sface.match(feat_live, enc, cv2.FaceRecognizerSF_FR_COSINE)
                        for enc in self.known_face_encodings
                    )
                    if best > 0.363:  # ArcFace cosine threshold
                        text = "Verified Student appeared"
                except Exception:
                    pass
            elif len(faces) > 0 and not self.known_face_encodings:
                text = "Verified Student appeared"  # no profiles — allow

            monitoring_status["face_detected"] = (text == "Verified Student appeared")
            faceDetectionRecording(frame, text)
            time.sleep(0.1)

    def _run_orb(self):
        """ORB fallback recognition loop."""
        global Globalflag
        orb = cv2.ORB_create()
        bf  = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        while True:
            if not Globalflag:
                time.sleep(0.2); continue
            with frame_lock:
                frame = latest_frame.copy() if latest_frame is not None else None
            if frame is None:
                time.sleep(0.05); continue
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = _haar.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            text  = "Verified Student disappeared"
            if len(faces) > 0 and self.known_face_encodings:
                x, y, w, h = faces[0]
                roi = gray[y:y+h, x:x+w]
                _, des = orb.detectAndCompute(roi, None)
                if des is not None:
                    best = 0
                    for enc in self.known_face_encodings:
                        try:
                            m = bf.match(des, enc)
                            best = max(best, len([x for x in m if x.distance < 50]))
                        except Exception:
                            pass
                    if best >= 8:
                        text = "Verified Student appeared"
            elif len(faces) > 0:
                text = "Verified Student appeared"
            monitoring_status["face_detected"] = (text == "Verified Student appeared")
            faceDetectionRecording(frame, text)
            time.sleep(0.1)

# ═══════════════════════════════════════════════════════════════════════════════
#  AUDIO  (adaptive noise floor VAD)
# ═══════════════════════════════════════════════════════════════════════════════

class Recorder:
    def __init__(self):
        self.quiet     = []
        self.quiet_idx = -1
        self.timeout   = 0

    @staticmethod
    def rms(frame_bytes):
        count = len(frame_bytes) // SHORT_WIDTH
        if not count:
            return 0
        shorts  = struct.unpack(f"{count}h", frame_bytes)
        sum_sq  = sum((s * SHORT_NORMALIZE) ** 2 for s in shorts)
        return math.pow(sum_sq / count, 0.5) * 1000

    def inSound(self, data):
        """Adaptive noise floor — 3× above background = speech."""
        global _noise_floor
        rms_val = self.rms(data)
        # Slowly adapt floor upward; fast reset downward
        if rms_val < _noise_floor or _noise_floor == 0:
            _noise_floor = _noise_floor * 0.98 + rms_val * 0.02
        else:
            _noise_floor = _noise_floor * 0.995 + rms_val * 0.005
        threshold = max(TRIGGER_RMS, _noise_floor * 3.0)
        curr = time.time()
        if rms_val > threshold:
            self.timeout = curr + TIMEOUT_SECS
            return True
        return curr < self.timeout

    def record(self):
        global Globalflag
        sound      = []
        begin_time = None

        def callback(indata, frames, time_info, status):
            nonlocal sound, begin_time
            raw = bytes(indata)
            if self.inSound(raw):
                sound.append(raw)
                if begin_time is None:
                    begin_time = datetime.datetime.now()
            else:
                if sound:
                    dur = math.floor((datetime.datetime.now() - begin_time).total_seconds())
                    self._save(sound, begin_time, dur)
                    sound.clear(); begin_time = None
                else:
                    self._queue_quiet(raw)

        with sd.RawInputStream(samplerate=RATE, channels=CHANNELS,
                               dtype='int16', blocksize=CHUNK, callback=callback):
            while True:
                if not Globalflag:
                    time.sleep(0.2)
                time.sleep(0.1)

    def _queue_quiet(self, data):
        self.quiet_idx = (self.quiet_idx + 1) % CUSHION_FRAMES
        if len(self.quiet) < CUSHION_FRAMES:
            self.quiet.append(data)
        else:
            self.quiet[self.quiet_idx] = data

    def _dequeue_quiet(self, sound):
        if not self.quiet:
            return sound
        idx = self.quiet_idx
        return (self.quiet[idx+1:] + self.quiet[:idx+1] + sound)

    def _save(self, sound, begin_time, duration):
        global _audio_violation_logged
        sound = self._dequeue_quiet(sound)
        keep  = len(sound) - TIMEOUT_FRAMES + CUSHION_FRAMES
        data  = b''.join(sound[:max(keep, 1)])
        fn    = str(random.randint(1, 50000)) + "VoiceViolation"
        path  = os.path.join(f_name_directory, f'{fn}.wav')
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SHORT_WIDTH)
            wf.setframerate(RATE)
            wf.writeframes(data)
        # Only log the violation once per exam session to avoid noise spam
        if not _audio_violation_logged:
            _audio_violation_logged = True
            v = {"Name": "Common Noise is detected.",
                 "Time": begin_time.strftime("%Y-%m-%d %H:%M:%S"),
                 "Duration": f"{duration} seconds", "Mark": duration,
                 "Link": f"{fn}.wav", "RId": get_resultId()}
            write_json(v)
            _push_violation("Audio Detected", f"Duration: {duration}s")

# ═══════════════════════════════════════════════════════════════════════════════
#  DETECTION THREADS
# ═══════════════════════════════════════════════════════════════════════════════

def cheat_Detection1():
    """
    Thread 1: Head pose (solvePnP) + iris gaze + EAR drowsiness.
    Uses MediaPipe FaceLandmarker Tasks API (iris landmarks bundled).
    """
    global Globalflag
    while True:
        if not Globalflag:
            monitoring_status["active"] = False
            time.sleep(0.2); continue
        monitoring_status["active"] = True
        with frame_lock:
            image = latest_frame.copy() if latest_frame is not None else None
        if image is None:
            time.sleep(0.05); continue

        # Face count via best available detector
        n = count_faces(image)
        monitoring_status["face_count"]   = n
        monitoring_status["face_detected"] = n > 0

        # Head pose + iris gaze + drowsiness
        headMovmentDetection(image)
        time.sleep(0.05)


def cheat_Detection2():
    """
    Thread 2: Multi-person detection + window switch + ONNX object detection.
    Runs YOLO every 1.5 s to keep CPU load manageable.
    """
    global Globalflag
    _last_yolo = 0
    while True:
        if not Globalflag:
            time.sleep(0.2); continue
        with frame_lock:
            image = latest_frame.copy() if latest_frame is not None else None
        if image is None:
            time.sleep(0.05); continue
        MTOP_Detection(image.copy())
        screenDetection()
        now = time.time()
        if now - _last_yolo >= 1.5:
            electronicDevicesDetection(image.copy())
            _last_yolo = now
        time.sleep(0.15)

# ═══════════════════════════════════════════════════════════════════════════════
#  QUERY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_resultId():
    with open('result.json', 'r+') as f:
        data = json.load(f)
        data.sort(key=lambda item: item["Id"])
        return data[-1]['Id'] + 1

def get_TrustScore(rid):
    with open('violation.json', 'r+') as f:
        data = json.load(f)
        total = sum(item["Mark"] for item in data if item["RId"] == rid)
        return total

def getResults():
    with open('result.json', 'r+') as f:
        return json.load(f)

def getResultDetails(rid):
    with open('result.json', 'r+') as f:
        results = [x for x in json.load(f) if x["Id"] == int(rid)]
    with open('violation.json', 'r+') as f:
        violations = [x for x in json.load(f) if x["RId"] == int(rid)]
    return {"Result": results, "Violation": violations}

# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE INIT
# ═══════════════════════════════════════════════════════════════════════════════

a  = Recorder()
fr = FaceRecognition()
