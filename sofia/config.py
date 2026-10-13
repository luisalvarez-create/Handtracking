"""Configuración persistente de Sofía."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

MODES = ("hand_pinch", "hand_dwell", "head")
MODE_LABELS = {
    "hand_pinch": "Mano + pellizco",
    "hand_dwell": "Mano + permanencia",
    "head": "Cabeza",
}


def config_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home() / ".config"
    return base / "Sofia"


@dataclass
class Config:
    mode: str = "hand_pinch"
    camera_index: int = 0
    hand: str = "any"  # any | left | right

    # Zona de la imagen de la cámara que cubre toda la pantalla (coordenadas normalizadas).
    # Más pequeña = menos movimiento necesario para llegar a las orillas.
    region_x: list[float] = field(default_factory=lambda: [0.25, 0.75])
    region_y: list[float] = field(default_factory=lambda: [0.2, 0.7])

    # Cabeza: cuánto se mueve el cursor por cada unidad de movimiento de la nariz.
    head_gain_x: float = 9.0
    head_gain_y: float = 12.0
    head_click: str = "dwell"  # dwell | mouth
    mouth_open: float = 0.45  # umbral de "boca abierta" (blendshape jawOpen)

    # Suavizado (filtro One Euro): menor min_cutoff = más estable; mayor beta = más ágil.
    min_cutoff: float = 1.0
    beta: float = 0.015

    # Clic por permanencia.
    dwell_time: float = 1.2  # segundos
    dwell_radius: float = 30.0  # píxeles

    # Pellizco (distancia pulgar–dedo dividida entre el tamaño de la palma).
    pinch_on: float = 0.28
    pinch_off: float = 0.42
    drag_after: float = 0.7  # segundos de pellizco sostenido para arrastrar
    scroll_step: float = 25.0  # píxeles de movimiento por línea de desplazamiento

    show_preview: bool = True
    sounds: bool = True

    # Asistente de voz (Gemini).
    voice: bool = True
    gemini_model: str = "gemini-3.5-flash-lite"
    assistant_name: str = "Maki"
    wake_words: list[str] = field(default_factory=lambda: ["hola maki"])  # frases de activación, por ejemplo ["sofía"]
    wake_similarity: float = 0.8  # qué tan parecido debe sonar el inicio de la frase (0–1)
    wake_confidence: float = 0.5  # confianza mínima del reconocimiento local en al menos una de esas palabras (0–1)
    followup_seconds: float = 8.0  # tiempo para contestar sin decir "Sofía" después de una pregunta
    voice_name: str = ""  # voz de `say` (vacío = la primera de español de México)
    mic_device: int | None = None  # micrófono (vacío = el predeterminado)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_dir() / "config.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        if cfg.mode not in MODES:
            cfg.mode = "hand_pinch"
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "config.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
