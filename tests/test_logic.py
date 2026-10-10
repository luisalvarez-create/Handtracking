"""Pruebas de la lógica de gestos (sin cámara ni ratón)."""
import math

from sofia.config import Config
from sofia.filters import OneEuroFilter
from sofia.gestures import (
    DwellClicker,
    FaceObservation,
    HandController,
    HandObservation,
    HeadController,
    map_region,
)

SCREEN = (1440, 900)
FPS = 30


def hand(cx=0.5, cy=0.45, pinch=None):
    """Mano sintética abierta centrada en (cx, cy); pinch = 'index' | 'middle' | 'ring' junta ese dedo con el pulgar."""
    lm = [(cx, cy + 0.1, 0.0)] * 21
    lm = list(lm)
    lm[0] = (cx, cy + 0.12, 0)  # muñeca
    lm[5] = (cx - 0.03, cy, 0)  # nudillo índice
    lm[9] = (cx, cy, 0)  # nudillo medio
    lm[4] = (cx - 0.09, cy + 0.02, 0)  # pulgar
    lm[8] = (cx - 0.04, cy - 0.1, 0)
    lm[12] = (cx, cy - 0.11, 0)
    lm[16] = (cx + 0.03, cy - 0.1, 0)
    tips = {"index": 8, "middle": 12, "ring": 16}
    if pinch:
        lm[4] = (lm[tips[pinch]][0] + 0.005, lm[tips[pinch]][1], 0)
    return HandObservation(lm, "right")


def run(ctrl, frames, t0=0.0):
    out = []
    t = t0
    for obs in frames:
        actions, status = ctrl.update(obs, t)
        out.append((t, actions, status))
        t += 1 / FPS
    return out


def kinds(results):
    return [a.kind if a.button == "left" else f"{a.kind}:{a.button}" for _, actions, _ in results for a in actions if a.kind != "move"]


def test_map_region_mirrors_and_clamps():
    assert map_region(0.25, 0.2, [0.25, 0.75], [0.2, 0.7]) == (1.0, 0.0)  # x en espejo
    assert map_region(0.75, 0.7, [0.25, 0.75], [0.2, 0.7]) == (0.0, 1.0)
    assert map_region(0.0, 1.0, [0.25, 0.75], [0.2, 0.7]) == (1.0, 1.0)  # fuera de zona → orilla


def test_one_euro_smooths_jitter():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    values = [f(100 + (5 if i % 2 else -5), i / 30) for i in range(60)]
    assert max(values[30:]) - min(values[30:]) < 3


def test_dwell_clicks_once_until_moved():
    d = DwellClicker(1.0, 20)
    clicks = sum(d.update((100, 100), i / 30) for i in range(100))
    assert clicks == 1
    d.update((200, 200), 4.0)
    clicks = sum(d.update((200, 200), 4.0 + i / 30) for i in range(40))
    assert clicks == 1


def test_quick_index_pinch_is_click_and_cursor_does_not_jump():
    ctrl = HandController(Config(), SCREEN, "pinch")
    res = run(ctrl, [hand()] * 20 + [hand(pinch="index")] * 5 + [hand()] * 5)
    assert kinds(res) == ["click"]
    click = next(a for _, acts, _ in res for a in acts if a.kind == "click")
    before = res[19][2].pointer
    assert math.dist((click.x, click.y), before) < 15


def test_held_pinch_drags():
    cfg = Config(drag_after=0.5)
    ctrl = HandController(cfg, SCREEN, "pinch")
    frames = [hand()] * 10 + [hand(pinch="index")] * 20 + [hand(cx=0.4, pinch="index")] * 10 + [hand(cx=0.4)] * 3
    assert kinds(run(ctrl, frames)) == ["down", "up"]


def test_middle_pinch_right_click_and_ring_scroll():
    ctrl = HandController(Config(), SCREEN, "pinch")
    assert kinds(run(ctrl, [hand()] * 10 + [hand(pinch="middle")] * 8 + [hand()] * 5)) == ["click:right"]
    ctrl = HandController(Config(), SCREEN, "pinch")
    frames = [hand()] * 10 + [hand(pinch="ring")] * 3 + [hand(cy=0.45 - i * 0.01, pinch="ring") for i in range(15)] + [hand()] * 3
    res = run(ctrl, frames)
    scrolls = [a.amount for _, acts, _ in res for a in acts if a.kind == "scroll"]
    assert scrolls and sum(scrolls) > 0  # mano hacia arriba → desplazar hacia arriba


def test_losing_hand_releases_drag():
    cfg = Config(drag_after=0.3)
    ctrl = HandController(cfg, SCREEN, "pinch")
    res = run(ctrl, [hand()] * 5 + [hand(pinch="index")] * 15 + [None])
    assert kinds(res) == ["down", "up"]


def test_hand_dwell_mode():
    ctrl = HandController(Config(dwell_time=1.0), SCREEN, "dwell")
    assert kinds(run(ctrl, [hand()] * 60)) == ["click"]


def face(dx=0.0, dy=0.0, jaw=0.0):
    lm = [(0.5, 0.5, 0.0)] * 478
    lm = list(lm)
    lm[1] = (0.5 + dx, 0.5 + dy, 0.0)
    return FaceObservation(lm, {"jawOpen": jaw})


def test_head_moves_cursor_relative_to_neutral():
    ctrl = HeadController(Config(), SCREEN)
    res = run(ctrl, [face()] * 30 + [face(dx=-0.03, dy=0.02)] * 60)
    x, y = res[-1][2].pointer
    assert x > SCREEN[0] * 0.7 and y > SCREEN[1] * 0.6  # nariz a la izquierda en la imagen = derecha del usuario


def test_head_mouth_click_and_pause():
    ctrl = HeadController(Config(head_click="mouth"), SCREEN)
    res = run(ctrl, [face()] * 20 + [face(jaw=0.7)] * 10 + [face()] * 5)
    assert kinds(res) == ["click"]
    ctrl = HeadController(Config(head_click="mouth"), SCREEN)
    res = run(ctrl, [face()] * 10 + [face(jaw=0.7)] * 60 + [face()] * 5)
    assert kinds(res) == ["pause"]  # boca abierta mucho tiempo: pausa, sin clic


def test_head_dwell_click():
    ctrl = HeadController(Config(dwell_time=1.0), SCREEN)
    assert kinds(run(ctrl, [face()] * 50)) == ["click"]
