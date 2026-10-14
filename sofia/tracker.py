"""Detección de mano o cara con MediaPipe Tasks.

La mano usa Gesture Recognizer: da los 21 puntos de la mano (igual que Hand
Landmarker) y además reconoce posturas entrenadas (puño, palma, paz…).
"""
from __future__ import annotations

import ssl
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from .config import config_dir
from .gestures import FaceObservation, HandObservation

MODEL_URLS = {
    "hand": "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
    "face": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}
# Nombres de MediaPipe → posturas de Sofía ("Pointing_Up" se ignora: es la mano normal al apuntar).
GESTURE_NAMES = {
    "Closed_Fist": "puño",
    "Open_Palm": "palma",
    "Victory": "paz",
    "Thumb_Up": "pulgar_arriba",
    "Thumb_Down": "pulgar_abajo",
    "ILoveYou": "te_quiero",
}


def ensure_model(kind: str, directory: Path | None = None) -> Path:
    """Descarga el modelo la primera vez y lo guarda para usarlo sin internet."""
    directory = directory or config_dir() / "models"
    path = directory / MODEL_URLS[kind].rsplit("/", 1)[-1]
    if path.exists() and path.stat().st_size > 0:
        return path
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Descargando modelo de MediaPipe ({kind})…", flush=True)
    try:
        import certifi  # Python de python.org en Mac no trae certificados por defecto.

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(MODEL_URLS[kind], context=context, timeout=60) as resp, open(tmp, "wb") as out:
        out.write(resp.read())
    tmp.replace(path)
    return path


class Tracker:
    """Procesa cuadros BGR de OpenCV y devuelve una observación de mano o cara (o None)."""

    def __init__(self, kind: str, hand_preference: str = "any", model_dir: Path | None = None):
        self.kind = kind
        self.hand_preference = hand_preference
        self._last_ts = -1
        model = str(ensure_model(kind, model_dir))
        if kind == "hand":
            options = vision.GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=model),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1 if hand_preference == "any" else 2,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._landmarker = vision.GestureRecognizer.create_from_options(options)
        else:
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self.last_landmarks: list[tuple[float, float, float]] | None = None

    def _timestamp(self) -> int:
        ts = int(time.monotonic() * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def process(self, frame_bgr) -> HandObservation | FaceObservation | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if self.kind == "hand":
            result = self._landmarker.recognize_for_video(image, self._timestamp())
        else:
            result = self._landmarker.detect_for_video(image, self._timestamp())
        obs = self._hand(result) if self.kind == "hand" else self._face(result)
        self.last_landmarks = obs.landmarks if obs else None
        return obs

    def _hand(self, result) -> HandObservation | None:
        candidates = []
        for i, lms in enumerate(result.hand_landmarks):
            label = result.handedness[i][0].category_name if result.handedness and result.handedness[i] else "Right"
            # MediaPipe asume imagen en espejo; la cámara la entrega sin espejo, así que se invierte.
            handedness = "right" if label == "Left" else "left"
            gesture, score = "", 0.0
            if getattr(result, "gestures", None) and i < len(result.gestures) and result.gestures[i]:
                top = result.gestures[i][0]
                gesture, score = GESTURE_NAMES.get(top.category_name, ""), float(top.score)
            candidates.append(HandObservation([(p.x, p.y, p.z) for p in lms], handedness, gesture, score))
        if self.hand_preference != "any":
            candidates = [c for c in candidates if c.handedness == self.hand_preference]
        return candidates[0] if candidates else None

    @staticmethod
    def _face(result) -> FaceObservation | None:
        if not result.face_landmarks:
            return None
        blend = {}
        if result.face_blendshapes:
            blend = {c.category_name: c.score for c in result.face_blendshapes[0]}
        return FaceObservation([(p.x, p.y, p.z) for p in result.face_landmarks[0]], blend)

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None


def open_camera(index: int):
    backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap
