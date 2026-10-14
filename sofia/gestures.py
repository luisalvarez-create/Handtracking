"""Convierte lo que detecta la cámara en acciones del ratón.

Todo este módulo es lógica pura (sin cámara ni ratón real) para poder probarlo.
Las coordenadas de MediaPipe vienen normalizadas (0–1) y SIN espejo; aquí se
aplica el espejo para que mover la mano a la derecha mueva el cursor a la derecha.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Config
from .filters import OneEuro2D

Point = tuple[float, float]
Landmark = tuple[float, float, float]

# Índices de MediaPipe Hand Landmarker.
WRIST, THUMB_TIP, INDEX_MCP, INDEX_TIP, MIDDLE_MCP, MIDDLE_TIP, RING_TIP = 0, 4, 5, 8, 9, 12, 16
# Índice de la punta de la nariz en Face Landmarker.
NOSE_TIP = 1


@dataclass
class Action:
    # move | click | down | up | scroll | pause | window_grab | window_move | window_release | gesture
    kind: str
    x: float = 0.0
    y: float = 0.0
    button: str = "left"
    amount: int = 0
    value: str = ""  # para "gesture": "atajo:cmd+w", "orden:abre Chrome", "escuchar"


@dataclass
class HandObservation:
    landmarks: list[Landmark]
    handedness: str = "right"  # mano del usuario: left | right
    gesture: str = ""  # postura reconocida por MediaPipe: puño | palma | paz | pulgar_arriba | pulgar_abajo | te_quiero
    gesture_score: float = 0.0


# --- Posturas de la mano y lo que hace cada una ------------------------------

POSES = {
    "puño": "Puño",
    "palma": "Palma abierta",
    "paz": "Paz (índice y medio)",
    "pulgar_arriba": "Pulgar arriba",
    "pulgar_abajo": "Pulgar abajo",
    "te_quiero": "Te quiero (índice, meñique y pulgar)",
}
GESTURE_ACTIONS = {
    "ninguna": "nada",
    "mover_ventana": "mover la ventana",
    "desplazar": "desplazar (subir o bajar la mano)",
    "arrastrar": "arrastrar",
    "clic": "clic",
    "doble_clic": "doble clic",
    "clic_derecho": "clic derecho",
    "pausar_cursor": "pausar o reanudar el cursor",
    "escuchar": "despertar al asistente",
    "atajo": "atajo de teclado",
    "orden": "orden al asistente",
}
CONTINUOUS = {"mover_ventana", "desplazar", "arrastrar"}  # duran mientras se mantiene la postura
GESTURE_MIN_SCORE = 0.6


def parse_binding(binding: str) -> tuple[str, str]:
    """"atajo:cmd+w" → ("atajo", "cmd+w"); "desplazar" → ("desplazar", "")."""
    action, _, value = (binding or "ninguna").partition(":")
    return action.strip(), value.strip()


def describe_bindings(bindings: dict[str, str]) -> str:
    parts = []
    for pose, label in POSES.items():
        action, value = parse_binding(bindings.get(pose, "ninguna"))
        if action == "ninguna":
            continue
        text = GESTURE_ACTIONS.get(action, action)
        parts.append(f"{label} = {text}{f' «{value}»' if value else ''}")
    return "; ".join(parts) or "ninguno"


class PoseTracker:
    """Una postura cuenta solo si se sostiene `hold` segundos; se suelta tras `release` segundos sin verla.

    Así un puño a medias o un cuadro mal reconocido no dispara nada.
    """

    def __init__(self, hold: float = 0.35, release: float = 0.25):
        self.hold, self.release = hold, release
        self.stable = ""
        self.candidate = ""
        self.since = 0.0
        self.lost_since: float | None = None

    def reset(self) -> None:
        self.stable = self.candidate = ""
        self.lost_since = None

    def update(self, pose: str, t: float) -> str:
        if pose != self.candidate:
            self.candidate, self.since = pose, t
        if pose == self.stable:
            self.lost_since = None
            return self.stable
        if self.stable:
            # Mientras dura un gesto se toleran cuadros sueltos con otra postura.
            if self.lost_since is None:
                self.lost_since = t
            if t - self.lost_since < self.release:
                return self.stable
            self.stable, self.lost_since = "", None
        if pose and t - self.since >= self.hold:
            self.stable = pose
        return self.stable


@dataclass
class FaceObservation:
    landmarks: list[Landmark]
    blendshapes: dict[str, float] = field(default_factory=dict)


@dataclass
class Status:
    message: str = ""
    pointer: Point | None = None
    dwell_progress: float = 0.0
    gesture: str = ""


def _dist(a: Landmark, b: Landmark) -> float:
    return math.dist(a[:2], b[:2])


def map_region(x: float, y: float, region_x, region_y, mirror: bool = True) -> Point:
    """Lleva un punto de la zona activa de la cámara a coordenadas normalizadas de pantalla."""
    if mirror:
        x = 1.0 - x
    u = (x - region_x[0]) / (region_x[1] - region_x[0])
    v = (y - region_y[0]) / (region_y[1] - region_y[0])
    return min(1.0, max(0.0, u)), min(1.0, max(0.0, v))


class Hysteresis:
    """Activa por debajo de `on` y desactiva por encima de `off` (evita parpadeos)."""

    def __init__(self, on: float, off: float):
        self.on, self.off = on, off
        self.active = False

    def update(self, value: float) -> bool:
        self.active = value < self.off if self.active else value < self.on
        return self.active


class DwellClicker:
    """Hace clic cuando el cursor se queda quieto `dwell_time` segundos dentro de `radius` píxeles.

    Después de un clic hay que mover el cursor fuera del radio para volver a activarlo,
    así el clic no se repite si la persona deja la mano quieta.
    """

    def __init__(self, dwell_time: float, radius: float):
        self.dwell_time = dwell_time
        self.radius = radius
        self.reset()

    def reset(self) -> None:
        self.anchor: Point | None = None
        self.start = 0.0
        self.armed = True
        self.progress = 0.0

    def update(self, pos: Point, t: float) -> bool:
        if self.anchor is None or math.dist(pos, self.anchor) > self.radius:
            self.anchor, self.start, self.armed, self.progress = pos, t, True, 0.0
            return False
        if not self.armed:
            self.progress = 0.0
            return False
        self.progress = min(1.0, (t - self.start) / self.dwell_time)
        if self.progress >= 1.0:
            self.armed = False
            self.progress = 0.0
            return True
        return False


class Pointer:
    """Coordenadas normalizadas → píxeles de pantalla suavizados."""

    def __init__(self, cfg: Config, screen: tuple[int, int]):
        self.w, self.h = screen
        self.filter = OneEuro2D(cfg.min_cutoff, cfg.beta)

    def reset(self) -> None:
        self.filter.reset()

    def update(self, nx: float, ny: float, t: float) -> Point:
        x, y = self.filter(nx * (self.w - 1), ny * (self.h - 1), t)
        return min(self.w - 1.0, max(0.0, x)), min(self.h - 1.0, max(0.0, y))


class HandController:
    """Control con la mano.

    click_mode="pinch":
      - pulgar + índice rápido → clic izquierdo (dos seguidos → doble clic)
      - pulgar + índice sostenido → arrastrar
      - pulgar + medio → clic derecho
      - pulgar + anular sostenido y mover arriba/abajo → desplazar (scroll)
    click_mode="dwell": clic izquierdo al dejar el cursor quieto.

    El cursor sigue los nudillos (no la punta del dedo), así no se mueve al pellizcar.
    """

    def __init__(self, cfg: Config, screen: tuple[int, int], click_mode: str = "pinch"):
        self.cfg = cfg
        self.click_mode = click_mode
        self.pointer = Pointer(cfg, screen)
        self.dwell = DwellClicker(cfg.dwell_time, cfg.dwell_radius)
        self.pinch = {name: Hysteresis(cfg.pinch_on, cfg.pinch_off) for name in ("index", "middle", "ring")}
        # idle | pressing | dragging | scrolling | right, o un gesto: g_window | g_scroll | g_drag | g_fired
        self.state = "idle"
        self.anchor: Point = (0.0, 0.0)
        self.press_time = 0.0
        self.scroll_y = 0.0
        self.last_pos: Point | None = None
        self.poses = PoseTracker(cfg.gesture_hold)
        self.g_pose = ""
        self.g_label = ""
        self.g_y0 = 0.0
        self.g_x0 = 0.0
        self.g_t = 0.0
        self.g_acc = 0.0
        self.still_pos: Point | None = None
        self.still_since = 0.0

    def reset(self) -> list[Action]:
        actions = []
        if self.state in ("dragging", "g_drag"):
            actions.append(Action("up", *self.anchor))
        elif self.state == "g_window":
            actions.append(Action("window_release", *self.anchor))
        self.state = "idle"
        self.pointer.reset()
        self.dwell.reset()
        self.poses.reset()
        for p in self.pinch.values():
            p.active = False
        self.last_pos = None
        return actions

    # --- gestos con toda la mano -------------------------------------------

    def _binding(self, pose: str) -> tuple[str, str]:
        if not pose:
            return "ninguna", ""
        action, value = parse_binding(self.cfg.gestures.get(pose, "ninguna"))
        return (action, value) if action in GESTURE_ACTIONS else ("ninguna", "")

    def _still_for(self, pos: Point, t: float) -> float:
        """Segundos que el cursor lleva casi quieto."""
        if self.still_pos is None or math.dist(pos, self.still_pos) > self.cfg.dwell_radius:
            self.still_pos, self.still_since = pos, t
        return t - self.still_since

    def _start_gesture(self, pose: str, action: str, value: str, pos: Point, hand: Point, t: float) -> list[Action]:
        self.g_pose = pose
        self.g_label = f"{POSES[pose].split(' (')[0]}: {GESTURE_ACTIONS[action].split(' (')[0]}"
        self.anchor = pos
        self.dwell.reset()
        if action == "mover_ventana":
            self.state = "g_window"
            return [Action("window_grab", *pos)]
        if action == "desplazar":
            self.state, self.g_x0, self.g_y0, self.g_t, self.g_acc = "g_scroll", hand[0], hand[1], t, 0.0
            return [Action("gesture_sound")]
        if action == "arrastrar":
            self.state = "g_drag"
            return [Action("down", *pos)]
        self.state = "g_fired"  # acción de una sola vez: no se repite hasta soltar la postura
        if action == "clic":
            return [Action("click", *pos)]
        if action == "doble_clic":
            return [Action("click", *pos), Action("click", *pos)]
        if action == "clic_derecho":
            return [Action("click", *pos, button="right")]
        if action == "pausar_cursor":
            return [Action("pause")]
        return [Action("gesture", *pos, value=f"{action}:{value}" if value else action)]

    def _continue_gesture(self, pos: Point, hand: Point, palm: float, t: float, status: Status) -> list[Action]:
        status.gesture = self.g_label
        if self.state == "g_window":
            return [Action("window_move", *pos)]
        if self.state == "g_drag":
            return [Action("move", *pos)]
        if self.state == "g_scroll":
            # Como palanca: cuanto más se aleja la mano del punto inicial, más rápido desplaza.
            if abs(hand[0] - self.g_x0) / max(palm, 1e-6) > 1.0:
                # Mover la mano hacia un lado = quiere mover el cursor, no desplazar.
                self.state = "idle"
                self.still_pos = None
                return [Action("move", *pos)]
            status.pointer = self.anchor
            offset = (hand[1] - self.g_y0) / max(palm, 1e-6)
            strength = min(1.0, max(0.0, abs(offset) - self.cfg.palm_deadzone))
            dt, self.g_t = max(0.0, t - self.g_t), t
            self.g_acc += -math.copysign(1, offset) * strength * self.cfg.palm_scroll_speed * dt
            lines = int(self.g_acc)
            if lines:
                self.g_acc -= lines
                return [Action("scroll", *self.anchor, amount=lines)]
            return []
        return [Action("move", *pos)]  # g_fired: el cursor sigue normal

    def _end_gesture(self, pos: Point) -> list[Action]:
        state, self.state = self.state, "idle"
        if state == "g_window":
            return [Action("window_release", *pos)]
        if state == "g_drag":
            return [Action("up", *pos)]
        return []

    def _gestures(self, obs: HandObservation, pos: Point, palm: float, hand: Point, t: float, status: Status):
        """Devuelve acciones si un gesto de mano toma el control en este cuadro; None si no."""
        seen = obs.gesture if obs.gesture_score >= GESTURE_MIN_SCORE else ""
        pose = self.poses.update(seen, t)
        still = self._still_for(pos, t)
        if self.state.startswith("g_"):
            if pose == self.g_pose:
                return self._continue_gesture(pos, hand, palm, t, status)
            return self._end_gesture(pos) + [Action("move", *pos)]
        if self.state not in ("idle", "pressing"):
            return None
        action, value = self._binding(pose)
        if action == "desplazar" and still < self.cfg.palm_hold:
            # La palma solo desplaza si se muestra quieta: al apuntar con la mano abierta no se activa.
            action = "ninguna"
        if action != "ninguna":
            # Si un pellizco empezó al cerrar el puño, se cancela sin hacer clic.
            actions = self._start_gesture(pose, action, value, pos, hand, t)
            status.gesture = self.g_label
            return actions
        forming, _ = self._binding(seen)
        if forming not in ("ninguna", "desplazar") and self.state == "pressing":
            # Se está formando un gesto (por ejemplo, cerrando el puño): el pellizco espera, sin clic.
            status.pointer = self.anchor
            return []
        return None

    @staticmethod
    def features(lm: list[Landmark]) -> tuple[Point, dict[str, float]]:
        palm = _dist(lm[WRIST], lm[MIDDLE_MCP]) or 1e-6
        center = ((lm[INDEX_MCP][0] + lm[MIDDLE_MCP][0]) / 2, (lm[INDEX_MCP][1] + lm[MIDDLE_MCP][1]) / 2)
        ratios = {
            "index": _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / palm,
            "middle": _dist(lm[THUMB_TIP], lm[MIDDLE_TIP]) / palm,
            "ring": _dist(lm[THUMB_TIP], lm[RING_TIP]) / palm,
        }
        return center, ratios

    def update(self, obs: HandObservation | None, t: float) -> tuple[list[Action], Status]:
        if obs is None:
            return self.reset(), Status("Mano no detectada")

        center, ratios = self.features(obs.landmarks)
        nx, ny = map_region(center[0], center[1], self.cfg.region_x, self.cfg.region_y)
        pos = self.pointer.update(nx, ny, t)
        status = Status("", pos)
        actions: list[Action] = []

        palm = _dist(obs.landmarks[WRIST], obs.landmarks[MIDDLE_MCP])
        gesture_actions = self._gestures(obs, pos, palm, center, t, status)
        if gesture_actions is not None:
            return gesture_actions, status

        if self.click_mode == "dwell":
            actions.append(Action("move", *pos))
            if self.dwell.update(pos, t):
                actions.append(Action("click", *pos))
                status.gesture = "clic"
            status.dwell_progress = self.dwell.progress
            return actions, status

        # Solo cuenta el dedo más cercano al pulgar, para no confundir índice con medio.
        closest = min(ratios, key=ratios.get)
        active = {name: self.pinch[name].update(r) and name == closest for name, r in ratios.items()}
        if self.state != "idle":
            # Mientras dura un gesto se mantiene el dedo que lo inició.
            finger = {"pressing": "index", "dragging": "index", "right": "middle", "scrolling": "ring"}[self.state]
            active = {name: (name == finger and self.pinch[name].active) for name in ratios}

        if self.state == "idle":
            if active["index"]:
                self.state, self.anchor, self.press_time = "pressing", pos, t
            elif active["middle"]:
                self.state = "right"
                actions.append(Action("click", *pos, button="right"))
                status.gesture = "clic derecho"
            elif active["ring"]:
                self.state, self.anchor, self.scroll_y = "scrolling", pos, pos[1]
            else:
                actions.append(Action("move", *pos))
        elif self.state == "pressing":
            if not active["index"]:
                actions.append(Action("click", *self.anchor))
                status.gesture = "clic"
                self.state = "idle"
            elif t - self.press_time >= self.cfg.drag_after:
                actions.append(Action("down", *self.anchor))
                self.state = "dragging"
                status.gesture = "arrastrando"
            else:
                status.gesture = "pellizco"
        elif self.state == "dragging":
            if active["index"]:
                actions.append(Action("move", *pos))
                status.gesture = "arrastrando"
            else:
                actions.append(Action("up", *pos))
                self.state = "idle"
        elif self.state == "right":
            if not active["middle"]:
                self.state = "idle"
        elif self.state == "scrolling":
            if not active["ring"]:
                self.state = "idle"
            else:
                lines = int((self.scroll_y - pos[1]) / self.cfg.scroll_step)
                if lines:
                    actions.append(Action("scroll", *self.anchor, amount=lines))
                    self.scroll_y -= lines * self.cfg.scroll_step
                status.gesture = "desplazando"

        if self.state in ("pressing", "scrolling"):
            status.pointer = self.anchor
        return actions, status


class HeadController:
    """Control con la cabeza: el cursor sigue la nariz respecto a una posición neutra.

    Clic por permanencia, o abriendo y cerrando la boca. Mantener la boca abierta
    1.5 s pausa/reanuda el control (funciona en cualquier modo de clic).
    """

    PAUSE_HOLD = 1.5
    MOUTH_FREEZE = 0.2  # a partir de aquí se considera que la boca se está abriendo

    def __init__(self, cfg: Config, screen: tuple[int, int]):
        self.cfg = cfg
        self.pointer = Pointer(cfg, screen)
        self.dwell = DwellClicker(cfg.dwell_time, cfg.dwell_radius)
        self.neutral: Point | None = None
        self._reset_mouth()

    def _reset_mouth(self) -> None:
        self.mouth_start: float | None = None
        self.mouth_peak = 0.0
        self.frozen: Point | None = None
        self.wide_start: float | None = None  # desde cuándo la boca está bien abierta
        self.pause_sent = False

    def recalibrate(self) -> None:
        """La siguiente posición de la nariz será el centro de la pantalla."""
        self.neutral = None

    def reset(self) -> list[Action]:
        self.pointer.reset()
        self.dwell.reset()
        self._reset_mouth()
        return []

    def update(self, obs: FaceObservation | None, t: float) -> tuple[list[Action], Status]:
        if obs is None:
            return self.reset(), Status("Cara no detectada")
        nose = obs.landmarks[NOSE_TIP]
        if self.neutral is None:
            self.neutral = (nose[0], nose[1])
        nx = 0.5 - (nose[0] - self.neutral[0]) * self.cfg.head_gain_x
        ny = 0.5 + (nose[1] - self.neutral[1]) * self.cfg.head_gain_y
        pos = self.pointer.update(min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny)), t)
        status = Status("", pos)
        actions: list[Action] = []

        jaw = obs.blendshapes.get("jawOpen", 0.0)
        if jaw > self.MOUTH_FREEZE:
            # Al abrir la boca la nariz se mueve un poco: se congela el cursor.
            if self.mouth_start is None:
                self.mouth_start, self.frozen = t, pos
            self.mouth_peak = max(self.mouth_peak, jaw)
            if jaw >= self.cfg.mouth_open:
                self.wide_start = t if self.wide_start is None else self.wide_start
            else:
                self.wide_start = None
            status.pointer = self.frozen
            if not self.pause_sent and self.wide_start is not None and t - self.wide_start >= self.PAUSE_HOLD:
                self.pause_sent = True
                actions.append(Action("pause"))
                status.gesture = "pausa"
            elif self.cfg.head_click == "mouth" and not self.pause_sent:
                status.gesture = "boca abierta"
            return actions, status

        if self.mouth_start is not None:
            # Boca cerrada de nuevo: clic si se abrió lo suficiente y no fue una pausa.
            if self.cfg.head_click == "mouth" and not self.pause_sent and self.mouth_peak >= self.cfg.mouth_open:
                actions.append(Action("click", *self.frozen))
                status.gesture = "clic"
            self._reset_mouth()
            self.dwell.reset()

        actions.insert(0, Action("move", *pos))
        if self.cfg.head_click == "dwell":
            if self.dwell.update(pos, t):
                actions.append(Action("click", *pos))
                status.gesture = "clic"
            status.dwell_progress = self.dwell.progress
        return actions, status
