"""
AI Lip Reading App — Powered by Auto-AVSR (State-of-the-art, 19.1% WER on LRS3)

This Flask app uses the Chaplin/Auto-AVSR pipeline for real-time visual speech recognition.
The model predicts full sentences from lip movements, not just fixed words.

Usage:
    1. python setup_model.py   (one-time setup)
    2. python app.py           (start the web app)
    3. Open http://localhost:5000
"""

import os
import sys
# Import mediapipe BEFORE any other ML libraries to prevent protobuf conflicts 
# with tensorflow (which is loaded by espnet/tensorboard).
import mediapipe as mp
import cv2
import time
import math
import tempfile
import threading
import traceback
import numpy as np
from collections import deque
from flask import Flask, render_template, Response, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

# ─── Fix for Python 3.12+ (distutils removed) ───
# The bundled espnet code uses distutils, so we patch it before importing
try:
    from distutils.version import LooseVersion
except ImportError:
    # Python 3.12+ removed distutils; provide a shim
    import importlib
    import types
    
    # Create distutils.version shim
    class LooseVersion:
        def __init__(self, vstring):
            self.vstring = vstring
            self.version = [int(x) if x.isdigit() else x for x in vstring.split('.')]
        def __lt__(self, other):
            if isinstance(other, str): other = LooseVersion(other)
            return self.version < other.version
        def __le__(self, other):
            if isinstance(other, str): other = LooseVersion(other)
            return self.version <= other.version
        def __gt__(self, other):
            if isinstance(other, str): other = LooseVersion(other)
            return self.version > other.version
        def __ge__(self, other):
            if isinstance(other, str): other = LooseVersion(other)
            return self.version >= other.version
        def __eq__(self, other):
            if isinstance(other, str): other = LooseVersion(other)
            return self.version == other.version
    
    # Create distutils.util shim
    def strtobool(val):
        val = str(val).lower()
        if val in ('y', 'yes', 't', 'true', 'on', '1'):
            return 1
        elif val in ('n', 'no', 'f', 'false', 'off', '0'):
            return 0
        else:
            raise ValueError(f"invalid truth value {val!r}")
    
    # Inject into sys.modules so espnet imports work
    distutils_mod = types.ModuleType('distutils')
    distutils_version_mod = types.ModuleType('distutils.version')
    distutils_util_mod = types.ModuleType('distutils.util')
    distutils_version_mod.LooseVersion = LooseVersion
    distutils_util_mod.strtobool = strtobool
    distutils_mod.version = distutils_version_mod
    distutils_mod.util = distutils_util_mod
    sys.modules['distutils'] = distutils_mod
    sys.modules['distutils.version'] = distutils_version_mod
    sys.modules['distutils.util'] = distutils_util_mod
    print("  (Patched distutils for Python 3.12+)")

# ─── Setup paths for Chaplin pipeline ───
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAPLIN_DIR = os.path.join(SCRIPT_DIR, "chaplin")

# CRITICAL: Chaplin's bundled espnet must take priority over any system-installed espnet.
# Remove any pre-loaded espnet modules from cache
espnet_keys = [k for k in sys.modules if k == 'espnet' or k.startswith('espnet.')]
for k in espnet_keys:
    del sys.modules[k]

# Insert chaplin dir at the VERY FRONT of sys.path
if CHAPLIN_DIR in sys.path:
    sys.path.remove(CHAPLIN_DIR)
sys.path.insert(0, CHAPLIN_DIR)

# ─── Flask app ───
app = Flask(__name__)

# ─── Configuration ───
CONFIG_FILE = os.path.join(CHAPLIN_DIR, "configs", "LRS3_V_WER19.1.ini")
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp_videos")
SAMPLE_DIR = os.path.join(SCRIPT_DIR, "sample_videos")
UPLOAD_DIR = os.path.join(SCRIPT_DIR, "uploaded_videos")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SAMPLE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Video recording settings
WEBCAM_FPS = 25  # Auto-AVSR expects 25 fps

# ─── Load the Auto-AVSR model ───
print("=" * 60)
print("  Loading Auto-AVSR Model (State-of-the-art Lip Reading)")
print("=" * 60)

import torch

# Determine device
if torch.cuda.is_available():
    DEVICE = "cuda:0"
    print(f"  Using GPU: {torch.cuda.get_device_name(0)}")
else:
    DEVICE = "cpu"
    print("  Using CPU (inference will be slower)")

try:
    # Change to chaplin dir so that config's relative paths resolve correctly
    original_cwd = os.getcwd()
    os.chdir(CHAPLIN_DIR)
    
    from pipelines.pipeline import InferencePipeline
    pipeline = InferencePipeline(
        CONFIG_FILE,
        device=torch.device(DEVICE),
        detector="mediapipe",
        face_track=True,
    )
    
    # Restore original working directory
    os.chdir(original_cwd)
    print("  ✓ Auto-AVSR model loaded successfully!")
except Exception as e:
    print(f"  ✗ Failed to load model: {e}")
    traceback.print_exc()
    print("\n  Make sure you ran: python setup_model.py")
    sys.exit(1)

print("=" * 60)

# ─── Face/lip detection with MediaPipe ───
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# MediaPipe lip landmark indices for distance calculation
UPPER_LIP_IDX = 13  # Upper lip center
LOWER_LIP_IDX = 14  # Lower lip center
# Outer lip landmarks for drawing
LIP_OUTLINE_INDICES = [
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
    308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78, 61
]

# ─── Global State ───
latest_frame_global = None
lip_roi_global = None
current_prediction = None
inference_running = False

# Manual recording state (controlled by Start/Stop buttons)
is_recording = False
recording_frames = []
recording_start_time = 0

# For the lip ROI display
LIP_DISPLAY_SIZE = (160, 120)


def calculate_lip_distance(face_landmarks, frame_h, frame_w):
    """Calculate the distance between upper and lower lip."""
    upper = face_landmarks.landmark[UPPER_LIP_IDX]
    lower = face_landmarks.landmark[LOWER_LIP_IDX]
    dist = math.hypot(
        (upper.x - lower.x) * frame_w,
        (upper.y - lower.y) * frame_h,
    )
    return dist


def get_lip_roi(frame, face_landmarks, frame_h, frame_w):
    """Extract the lip region of interest for display."""
    # Get bounding box of all lip landmarks
    lip_indices = list(range(61, 69)) + list(range(78, 96)) + [
        146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
        308, 324, 318, 402, 317, 14, 87, 178, 88, 95,
    ]
    xs = [int(face_landmarks.landmark[i].x * frame_w) for i in lip_indices]
    ys = [int(face_landmarks.landmark[i].y * frame_h) for i in lip_indices]

    margin = 20
    x_min = max(0, min(xs) - margin)
    x_max = min(frame_w, max(xs) + margin)
    y_min = max(0, min(ys) - margin)
    y_max = min(frame_h, max(ys) + margin)

    lip_crop = frame[y_min:y_max, x_min:x_max]
    if lip_crop.size == 0:
        return None

    try:
        lip_crop = cv2.resize(lip_crop, LIP_DISPLAY_SIZE)
    except Exception:
        return None

    return lip_crop


def draw_lip_landmarks(frame, face_landmarks, frame_h, frame_w):
    """Draw lip outline on the frame."""
    points = []
    for idx in LIP_OUTLINE_INDICES:
        lm = face_landmarks.landmark[idx]
        x = int(lm.x * frame_w)
        y = int(lm.y * frame_h)
        points.append((x, y))
        cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)

    # Draw connected lip outline
    for i in range(len(points) - 1):
        cv2.line(frame, points[i], points[i + 1], (0, 255, 0), 1)


def run_inference(frames, fps):
    """Save frames to temp video and run Auto-AVSR inference."""
    global current_prediction, inference_running

    if inference_running:
        return
    inference_running = True

    try:
        if len(frames) < 10:
            print(f"  ⚠ Too few frames ({len(frames)}), need at least 10. Speak longer.")
            return

        # Save frames as a temp video file
        temp_path = os.path.join(TEMP_DIR, f"speech_{int(time.time() * 1000)}.mp4")
        h, w = frames[0].shape[:2]

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(temp_path, fourcc, fps, (w, h))
        for frame in frames:
            writer.write(frame)
        writer.release()

        # Run Auto-AVSR inference
        duration = len(frames) / fps
        print(f"  🎤 Running inference on {len(frames)} frames ({duration:.1f}s)...")
        transcript = pipeline(temp_path)
        transcript = transcript.strip()

        if transcript:
            print(f"  📝 Prediction: \"{transcript}\"")
            current_prediction = {
                "text": transcript,
                "timestamp": time.time(),
                "duration": round(duration, 1),
                "num_frames": len(frames),
            }
        else:
            print("  (empty prediction)")

        # Clean up temp file
        try:
            os.remove(temp_path)
        except OSError:
            pass

    except Exception as e:
        print(f"  ✗ Inference error: {e}")
        traceback.print_exc()
    finally:
        inference_running = False


def camera_thread_loop():
    """Background thread: capture webcam frames and record when active."""
    global latest_frame_global, lip_roi_global
    global recording_frames, is_recording

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FPS, WEBCAM_FPS)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_interval = 1.0 / WEBCAM_FPS
    last_frame_time = 0

    while True:
        current_time = time.time()
        if current_time - last_frame_time < frame_interval:
            time.sleep(0.001)
            continue

        success, frame = cap.read()
        if not success:
            time.sleep(0.05)
            continue

        last_frame_time = current_time
        frame_h, frame_w = frame.shape[:2]

        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb_frame)

        if results.multi_face_landmarks:
            face_landmarks = results.multi_face_landmarks[0]

            # Draw lip landmarks on display frame
            draw_lip_landmarks(frame, face_landmarks, frame_h, frame_w)

            # Extract lip ROI for display
            lip_roi = get_lip_roi(frame, face_landmarks, frame_h, frame_w)
            if lip_roi is not None:
                lip_roi_global = lip_roi.copy()

        # If recording is active, accumulate frames
        if is_recording:
            recording_frames.append(frame.copy())
            # Draw red recording indicator
            cv2.circle(frame, (frame_w - 30, 30), 12, (0, 0, 255), -1)
            cv2.putText(frame, "REC", (frame_w - 80, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        latest_frame_global = frame.copy()


# ─── Start background camera thread ───
bg_thread = threading.Thread(target=camera_thread_loop, daemon=True)
bg_thread.start()


# ─── Flask Routes ───

def generate_frames():
    """Generate MJPEG stream from webcam."""
    while True:
        if latest_frame_global is not None:
            ret, buffer = cv2.imencode(".jpg", latest_frame_global)
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                )
        time.sleep(0.03)


def generate_lip_frames():
    """Generate MJPEG stream of lip ROI."""
    while True:
        if lip_roi_global is not None:
            ret, buffer = cv2.imencode(".jpg", lip_roi_global)
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                )
        else:
            blank = np.zeros((LIP_DISPLAY_SIZE[1], LIP_DISPLAY_SIZE[0], 3), dtype=np.uint8)
            ret, buffer = cv2.imencode(".jpg", blank)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        time.sleep(0.03)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/lip_feed")
def lip_feed():
    return Response(generate_lip_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status")
def status():
    global current_prediction, inference_running, is_recording, recording_frames
    response = {
        "recording": is_recording,
        "prediction": current_prediction,
        "processing": inference_running,
        "recorded_frames": len(recording_frames),
        "recorded_seconds": round(len(recording_frames) / WEBCAM_FPS, 1) if recording_frames else 0,
    }
    return jsonify(response)


@app.route("/start_recording")
def start_recording():
    """Start recording frames for lip reading."""
    global is_recording, recording_frames, recording_start_time
    recording_frames = []  # Clear any previous frames
    is_recording = True
    recording_start_time = time.time()
    print("  🔴 Recording started...")
    return jsonify({"status": "recording"})


@app.route("/stop_recording")
def stop_recording():
    """Stop recording and trigger inference."""
    global is_recording, recording_frames
    is_recording = False
    
    frames_copy = list(recording_frames)
    recording_frames = []
    
    print(f"  ⏹ Recording stopped. Captured {len(frames_copy)} frames.")
    
    if len(frames_copy) >= 10:
        # Run inference in background thread
        threading.Thread(
            target=run_inference,
            args=(frames_copy, WEBCAM_FPS),
            daemon=True,
        ).start()
        return jsonify({"status": "processing", "frames": len(frames_copy)})
    else:
        return jsonify({"status": "too_short", "frames": len(frames_copy)})


@app.route("/reset")
def reset():
    global current_prediction, recording_frames, is_recording
    current_prediction = None
    recording_frames = []
    is_recording = False
    return jsonify({"status": "success"})


# ─── Sample Video Routes ───

@app.route("/sample_videos")
def list_sample_videos():
    """Return list of available sample video clips."""
    manifest_path = os.path.join(SAMPLE_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        import json
        with open(manifest_path, "r") as f:
            clips = json.load(f)
        # Only include clips whose files actually exist
        clips = [c for c in clips if os.path.exists(os.path.join(SAMPLE_DIR, c["filename"]))]
        return jsonify({"clips": clips})
    
    # Fallback: list any .mp4 files in the directory
    clips = []
    if os.path.isdir(SAMPLE_DIR):
        for fname in sorted(os.listdir(SAMPLE_DIR)):
            if fname.lower().endswith(".mp4"):
                clips.append({
                    "filename": fname,
                    "name": fname.replace("_", " ").replace(".mp4", "").title(),
                    "description": "Sample video clip",
                    "source": "Local file",
                    "duration": 0,
                })
    return jsonify({"clips": clips})


@app.route("/sample_video/<path:filename>")
def serve_sample_video(filename):
    """Serve a sample video file for browser playback."""
    safe_name = secure_filename(filename)
    return send_from_directory(SAMPLE_DIR, safe_name)


@app.route("/run_sample_inference", methods=["POST"])
def run_sample_inference():
    """Run Auto-AVSR inference on a sample video file."""
    global current_prediction

    data = request.get_json()
    filename = data.get("filename", "")
    source = data.get("source", "sample")  # "sample" or "upload"

    if source == "upload":
        video_path = os.path.join(UPLOAD_DIR, secure_filename(filename))
    else:
        video_path = os.path.join(SAMPLE_DIR, secure_filename(filename))

    if not os.path.exists(video_path):
        return jsonify({"status": "error", "message": f"File not found: {filename}"}), 404

    try:
        print(f"  🎬 Running inference on sample: {filename}...")
        transcript = pipeline(video_path)
        transcript = transcript.strip()

        result = {
            "status": "success",
            "text": transcript if transcript else "(no speech detected)",
            "filename": filename,
        }
        print(f"  📝 Sample prediction: \"{transcript}\"")

        # Also update the global prediction for the status endpoint
        current_prediction = {
            "text": transcript if transcript else "(no speech detected)",
            "timestamp": time.time(),
            "duration": 0,
            "num_frames": 0,
            "source": "sample_video",
        }

        return jsonify(result)

    except Exception as e:
        print(f"  ✗ Sample inference error: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/upload_video", methods=["POST"])
def upload_video():
    """Upload a video file for inference."""
    if "video" not in request.files:
        return jsonify({"status": "error", "message": "No video file provided"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No file selected"}), 400

    # Only allow video files
    allowed = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"status": "error", "message": f"Unsupported format: {ext}"}), 400

    safe_name = secure_filename(file.filename)
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(save_path)

    return jsonify({"status": "success", "filename": safe_name})


@app.route("/uploaded_video/<path:filename>")
def serve_uploaded_video(filename):
    """Serve an uploaded video file for browser playback."""
    safe_name = secure_filename(filename)
    return send_from_directory(UPLOAD_DIR, safe_name)


if __name__ == "__main__":
    print("\n  🌐 Open http://localhost:5000 in your browser\n")
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)
