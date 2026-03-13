#!/usr/bin/env python3
"""
JARVIS Camera Daemon — runs on the Mac Mini.

Connects to a TP-Link Tapo camera via RTSP, serves snapshots/MJPEG,
handles ONVIF PTZ commands, and runs MediaPipe gesture recognition.

Environment variables:
    CAMERA_IP           Camera IP on local network (required)
    CAMERA_USERNAME     Camera account username (default: mr.stark)
    CAMERA_PASSWORD     Camera account password (required)
    CAMERA_RTSP_PORT    RTSP port (default: 554)
    CAMERA_ONVIF_PORT   ONVIF port (default: 2020)
    CAMERA_DAEMON_PORT  HTTP port for this daemon (default: 5055)
    JARVIS_BACKEND_URL  Backend URL for gesture events (optional)
    SERVICE_API_KEY     Backend service key for auth (optional)

Usage:
    pip install opencv-python mediapipe fastapi uvicorn numpy httpx
    pip install python-onvif-zeep  # optional, for PTZ
    python camera_daemon.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

# Optional imports
try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False

try:
    from onvif import ONVIFCamera
    ONVIF_AVAILABLE = True
except ImportError:
    ONVIF_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("jarvis.camera")

# ── Configuration ───────────────────────────────────────────────────────

CAMERA_IP = os.getenv("CAMERA_IP", "")
CAMERA_USERNAME = os.getenv("CAMERA_USERNAME", "mr.stark")
CAMERA_PASSWORD = os.getenv("CAMERA_PASSWORD", "")
CAMERA_RTSP_PORT = int(os.getenv("CAMERA_RTSP_PORT", "554"))
CAMERA_ONVIF_PORT = int(os.getenv("CAMERA_ONVIF_PORT", "2020"))
DAEMON_PORT = int(os.getenv("CAMERA_DAEMON_PORT", "5055"))
BACKEND_URL = os.getenv("JARVIS_BACKEND_URL", "")
SERVICE_KEY = os.getenv("SERVICE_API_KEY", "")

# URL-encode password for RTSP (handles special chars like !)
ENCODED_PASSWORD = quote(CAMERA_PASSWORD, safe="")


def rtsp_url(stream: int = 2) -> str:
    """Build RTSP URL. stream=1 for main (2K), stream=2 for sub (lower res)."""
    return f"rtsp://{CAMERA_USERNAME}:{ENCODED_PASSWORD}@{CAMERA_IP}:{CAMERA_RTSP_PORT}/stream{stream}"


# ── Gesture Recognition ────────────────────────────────────────────────

@dataclass
class GestureState:
    current_gesture: Optional[str] = None
    confidence: float = 0.0
    hand_count: int = 0
    landmarks: Optional[list] = None
    last_detected: float = 0.0
    recent_gestures: deque = field(default_factory=lambda: deque(maxlen=30))
    gesture_hold_frames: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, gesture: Optional[str], confidence: float, hand_count: int):
        with self.lock:
            if gesture == self.current_gesture:
                self.gesture_hold_frames += 1
            else:
                self.gesture_hold_frames = 1

            self.current_gesture = gesture
            self.confidence = confidence
            self.hand_count = hand_count
            if gesture:
                self.last_detected = time.time()
                self.recent_gestures.append({
                    "gesture": gesture,
                    "confidence": round(confidence, 2),
                    "time": time.time(),
                })

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "active": MP_AVAILABLE,
                "gesture": self.current_gesture,
                "confidence": round(self.confidence, 2),
                "hand_count": self.hand_count,
                "hold_frames": self.gesture_hold_frames,
                "last_detected": self.last_detected,
                "recent": list(self.recent_gestures)[-5:],
            }


def classify_gesture(hand_landmarks) -> tuple[Optional[str], float]:
    """Classify hand gesture from MediaPipe landmarks."""
    lm = hand_landmarks.landmark

    # Finger tip and pip indices
    # Thumb: 4 (tip), 3 (ip), 2 (mcp)
    # Index: 8 (tip), 6 (pip)
    # Middle: 12 (tip), 10 (pip)
    # Ring: 16 (tip), 14 (pip)
    # Pinky: 20 (tip), 18 (pip)

    # Check finger extension (tip above pip = extended, y inverted)
    fingers = []

    # Thumb — check x distance from palm center
    thumb_extended = abs(lm[4].x - lm[2].x) > 0.05
    fingers.append(1 if thumb_extended else 0)

    # Other fingers — tip.y < pip.y means extended (screen coords)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        fingers.append(1 if lm[tip].y < lm[pip].y else 0)

    total = sum(fingers)

    # Wrist orientation for thumbs up/down
    wrist_y = lm[0].y
    middle_mcp_y = lm[9].y

    # Classification
    if total == 5:
        return "open_palm", 0.9
    elif total == 0:
        return "fist", 0.9
    elif fingers == [1, 0, 0, 0, 0]:
        # Thumb only — check if up or down
        if lm[4].y < lm[2].y:
            return "thumbs_up", 0.85
        else:
            return "thumbs_down", 0.85
    elif fingers[1] == 1 and sum(fingers[2:]) == 0 and fingers[0] == 0:
        return "point", 0.85
    elif fingers[1] == 1 and fingers[2] == 1 and sum(fingers[3:]) == 0:
        return "peace", 0.85
    elif total >= 4:
        return "open_palm", 0.7
    else:
        return None, 0.0


# ── Camera Capture Thread ──────────────────────────────────────────────

class CameraCapture:
    """Background thread that captures RTSP frames and runs gesture detection."""

    def __init__(self):
        self.frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.connected = False
        self.fps = 0.0
        self.resolution = (0, 0)
        self.gesture_state = GestureState()
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

        # MediaPipe hands
        self._mp_hands = None
        if MP_AVAILABLE:
            self._mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5,
            )

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Camera capture thread started")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._cap:
            self._cap.release()
        logger.info("Camera capture thread stopped")

    def _connect(self) -> bool:
        """Connect/reconnect to RTSP stream."""
        if self._cap:
            self._cap.release()

        url = rtsp_url(stream=2)  # Use sub-stream for lower bandwidth
        logger.info("Connecting to RTSP: %s@%s:%d/stream2", CAMERA_USERNAME, CAMERA_IP, CAMERA_RTSP_PORT)

        self._cap = cv2.VideoCapture(url)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self._cap.isOpened():
            self.resolution = (
                int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            self.connected = True
            logger.info("Connected! Resolution: %dx%d", *self.resolution)
            return True

        logger.error("Failed to connect to RTSP stream")
        self.connected = False
        return False

    def _capture_loop(self):
        reconnect_delay = 5
        frame_count = 0
        fps_start = time.time()

        while self.running:
            if not self.connected:
                if not self._connect():
                    time.sleep(reconnect_delay)
                    continue

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Frame capture failed, reconnecting...")
                self.connected = False
                time.sleep(1)
                continue

            with self.frame_lock:
                self.frame = frame

            # FPS counter
            frame_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 2.0:
                self.fps = frame_count / elapsed
                frame_count = 0
                fps_start = time.time()

            # Gesture recognition (every 3rd frame to reduce CPU)
            if self._mp_hands and frame_count % 3 == 0:
                self._detect_gestures(frame)

    def _detect_gestures(self, frame: np.ndarray):
        """Run MediaPipe hand detection on a frame."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._mp_hands.process(rgb)

        if results.multi_hand_landmarks:
            hand_count = len(results.multi_hand_landmarks)
            # Use first detected hand
            gesture, confidence = classify_gesture(results.multi_hand_landmarks[0])
            self.gesture_state.update(gesture, confidence, hand_count)

            # Report sustained gestures to backend
            if (gesture and self.gesture_state.gesture_hold_frames == 10
                    and BACKEND_URL and HTTPX_AVAILABLE):
                threading.Thread(
                    target=self._report_gesture, args=(gesture, confidence), daemon=True
                ).start()
        else:
            self.gesture_state.update(None, 0.0, 0)

    def _report_gesture(self, gesture: str, confidence: float):
        """POST gesture event to JARVIS backend."""
        try:
            import httpx as hx
            hx.post(
                f"{BACKEND_URL}/api/v1/camera/gesture-event",
                json={"gesture": gesture, "confidence": confidence, "time": time.time()},
                headers={"X-Service-Key": SERVICE_KEY} if SERVICE_KEY else {},
                timeout=5,
            )
        except Exception:
            pass  # Non-critical

    def get_jpeg(self, quality: int = 85) -> Optional[bytes]:
        """Get current frame as JPEG bytes."""
        with self.frame_lock:
            if self.frame is None:
                return None
            _, buf = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            return buf.tobytes()

    def mjpeg_generator(self):
        """Generator for MJPEG stream."""
        while self.running:
            jpeg = self.get_jpeg(quality=70)
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                    + jpeg + b"\r\n"
                )
            time.sleep(0.066)  # ~15 fps


# ── ONVIF PTZ Control ──────────────────────────────────────────────────

class PTZController:
    """ONVIF PTZ control for the camera."""

    def __init__(self):
        self._camera = None
        self._ptz = None
        self._profile_token = None

    def connect(self):
        if not ONVIF_AVAILABLE:
            logger.warning("python-onvif-zeep not installed, PTZ disabled")
            return False
        try:
            self._camera = ONVIFCamera(
                CAMERA_IP, CAMERA_ONVIF_PORT, CAMERA_USERNAME, CAMERA_PASSWORD
            )
            media = self._camera.create_media_service()
            profiles = media.GetProfiles()
            if profiles:
                self._profile_token = profiles[0].token
            self._ptz = self._camera.create_ptz_service()
            logger.info("ONVIF PTZ connected, profile: %s", self._profile_token)
            return True
        except Exception as exc:
            logger.error("ONVIF connection failed: %s", exc)
            return False

    def move(self, action: str, speed: float = 0.5, duration: float = 0.5) -> dict:
        if not self._ptz or not self._profile_token:
            return {"ok": False, "error": "PTZ not connected"}

        try:
            velocity = {"PanTilt": {"x": 0.0, "y": 0.0}, "Zoom": {"x": 0.0}}

            if action == "left":
                velocity["PanTilt"]["x"] = -speed
            elif action == "right":
                velocity["PanTilt"]["x"] = speed
            elif action == "up":
                velocity["PanTilt"]["y"] = speed
            elif action == "down":
                velocity["PanTilt"]["y"] = -speed
            elif action == "zoom_in":
                velocity["Zoom"]["x"] = speed
            elif action == "zoom_out":
                velocity["Zoom"]["x"] = -speed
            elif action == "home":
                self._ptz.GotoHomePosition({"ProfileToken": self._profile_token})
                return {"ok": True, "action": "home"}
            elif action == "stop":
                self._ptz.Stop({"ProfileToken": self._profile_token})
                return {"ok": True, "action": "stop"}
            else:
                return {"ok": False, "error": f"Unknown action: {action}"}

            request = self._ptz.create_type("ContinuousMove")
            request.ProfileToken = self._profile_token
            request.Velocity = velocity
            self._ptz.ContinuousMove(request)

            # Stop after duration
            if duration > 0:
                def stop_later():
                    time.sleep(duration)
                    try:
                        self._ptz.Stop({"ProfileToken": self._profile_token})
                    except Exception:
                        pass
                threading.Thread(target=stop_later, daemon=True).start()

            return {"ok": True, "action": action, "speed": speed, "duration": duration}

        except Exception as exc:
            logger.error("PTZ move error: %s", exc)
            return {"ok": False, "error": str(exc)}


# ── FastAPI Application ────────────────────────────────────────────────

capture = CameraCapture()
ptz = PTZController()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not CAMERA_IP:
        logger.error("CAMERA_IP not set! Set the environment variable and restart.")
    else:
        capture.start()
        ptz.connect()
    yield
    capture.stop()


app = FastAPI(title="JARVIS Camera Daemon", lifespan=lifespan)


class PTZBody(BaseModel):
    speed: float = 0.5
    duration: float = 0.5


@app.get("/status")
def status():
    return {
        "online": capture.connected,
        "fps": round(capture.fps, 1),
        "resolution": list(capture.resolution),
        "camera_ip": CAMERA_IP,
        "gestures_enabled": MP_AVAILABLE,
        "ptz_enabled": ONVIF_AVAILABLE and ptz._ptz is not None,
        "model": "TP-Link Tapo TCW30",
    }


@app.get("/snapshot")
def snapshot():
    jpeg = capture.get_jpeg(quality=90)
    if not jpeg:
        return Response(status_code=503, content=b"No frame available")
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/stream")
def stream():
    return StreamingResponse(
        capture.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/ptz/{action}")
def ptz_control(action: str, body: PTZBody = PTZBody()):
    return ptz.move(action, body.speed, body.duration)


@app.get("/gestures")
def gestures():
    return capture.gesture_state.to_dict()


@app.post("/gesture-event")
def gesture_event_webhook(data: dict):
    """Receive gesture events (for forwarding, if needed)."""
    logger.info("Gesture event: %s", data)
    return {"received": True}


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting JARVIS Camera Daemon on port %d", DAEMON_PORT)
    uvicorn.run(app, host="0.0.0.0", port=DAEMON_PORT, log_level="info")
