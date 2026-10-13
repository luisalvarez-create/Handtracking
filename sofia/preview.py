"""Ventana de vista previa: cámara en espejo, puntos detectados y estado."""
from __future__ import annotations

import cv2

from .config import MODE_LABELS, Config
from .gestures import Status

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]
# OpenCV no dibuja acentos con sus fuentes integradas.
_ASCII = str.maketrans("áéíóúñÁÉÍÓÚÑü«»¿¡…", "aeiounAEIOUNu\"\"?!.")

GREEN = (120, 220, 120)
WHITE = (255, 255, 255)
ORANGE = (60, 160, 255)
RED = (80, 80, 230)


def _text(img, text, org, scale=0.6, color=WHITE, thick=1):
    text = text.translate(_ASCII)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw(frame, cfg: Config, status: Status, landmarks, screen: tuple[int, int], paused: bool, kind: str, voice_state: str = ""):
    img = cv2.flip(frame, 1)
    h, w = img.shape[:2]

    if landmarks:
        pts = [(int((1 - x) * w), int(y * h)) for x, y, _ in landmarks]
        if kind == "hand":
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, pts[a], pts[b], GREEN, 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(img, p, 3, WHITE, -1, cv2.LINE_AA)
        else:
            for p in pts[::4]:
                cv2.circle(img, p, 1, GREEN, -1)
            cv2.circle(img, pts[1], 6, ORANGE, -1, cv2.LINE_AA)  # nariz

    if kind == "hand":
        # Zona activa: moverse dentro de este rectángulo cubre toda la pantalla.
        x0, x1 = cfg.region_x
        y0, y1 = cfg.region_y
        cv2.rectangle(img, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), ORANGE, 1, cv2.LINE_AA)

    # Mini pantalla con la posición del cursor.
    mw, mh = 120, int(120 * screen[1] / max(1, screen[0]))
    mx, my = w - mw - 10, 10
    cv2.rectangle(img, (mx, my), (mx + mw, my + mh), (40, 40, 40), -1)
    cv2.rectangle(img, (mx, my), (mx + mw, my + mh), WHITE, 1)
    if status.pointer:
        px = mx + int(status.pointer[0] / screen[0] * mw)
        py = my + int(status.pointer[1] / screen[1] * mh)
        cv2.circle(img, (px, py), 4, ORANGE, -1, cv2.LINE_AA)
        if status.dwell_progress > 0:
            cv2.ellipse(img, (px, py), (10, 10), -90, 0, 360 * status.dwell_progress, GREEN, 2, cv2.LINE_AA)

    # Progreso de permanencia grande (más fácil de ver).
    if status.dwell_progress > 0:
        c = (w // 2, h - 60)
        cv2.circle(img, c, 28, (60, 60, 60), 3, cv2.LINE_AA)
        cv2.ellipse(img, c, (28, 28), -90, 0, 360 * status.dwell_progress, GREEN, 5, cv2.LINE_AA)

    _text(img, f"Modo: {MODE_LABELS[cfg.mode]}", (10, 25))
    if paused:
        _text(img, "PAUSA", (10, 60), 1.0, RED, 2)
    elif status.message:
        _text(img, status.message, (10, 55), 0.7, ORANGE, 2)
    if status.gesture:
        _text(img, status.gesture, (10, 90), 0.9, GREEN, 2)
    if voice_state:
        _text(img, f"Voz: {voice_state}", (10, h - 36), 0.55, WHITE if voice_state.startswith("Di ") else GREEN)
    _text(img, "p: pausa  m: modo  c: centrar  +/-: tiempo  q: salir", (10, h - 12), 0.45)
    return img
