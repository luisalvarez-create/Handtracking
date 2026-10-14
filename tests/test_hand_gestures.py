"""Gestos con toda la mano: puño mueve la ventana, palma desplaza, gestos programables por voz."""
import sys
import types as pytypes

from sofia import actions as act
from sofia.config import Config
from sofia.gestures import HandController, PoseTracker, describe_bindings, parse_binding
from sofia.voice import VoiceAssistant
from sofia.windows import DragMover, MacWindowMover
from test_logic import hand, kinds, run
from test_voice import FakeClient, call, text

FPS = 30


def pose(name, cx=0.5, cy=0.45, score=0.9, pinch=None):
    obs = hand(cx, cy, pinch)
    obs.gesture, obs.gesture_score = name, score
    return obs


def ctrl(gestures=None, mode="pinch"):
    cfg = Config()
    if gestures is not None:
        cfg.gestures = gestures
    return HandController(cfg, (1440, 900), mode)


# --- posturas ------------------------------------------------------------------

def test_pose_tracker_needs_hold_and_tolerates_glitches():
    p = PoseTracker(hold=0.3, release=0.2)
    assert p.update("puño", 0.0) == ""
    assert p.update("puño", 0.2) == ""
    assert p.update("puño", 0.31) == "puño"
    assert p.update("", 0.4) == "puño"  # un cuadro suelto no lo suelta
    assert p.update("puño", 0.45) == "puño"
    assert p.update("", 0.5) == "puño"
    assert p.update("", 0.75) == ""  # 0.25 s sin verlo: se suelta
    assert p.update("palma", 0.8) == ""  # otra postura vuelve a contar desde cero


def test_bindings_text():
    assert parse_binding("atajo:cmd+w") == ("atajo", "cmd+w")
    assert parse_binding("desplazar") == ("desplazar", "")
    assert parse_binding("") == ("ninguna", "")
    text_ = describe_bindings({"puño": "mover_ventana", "paz": "atajo:cmd+w", "palma": "ninguna"})
    assert text_ == "Puño = mover la ventana; Paz (índice y medio) = atajo de teclado «cmd+w»"


# --- puño: mover ventana ---------------------------------------------------------

def test_fist_grabs_moves_and_releases_window():
    c = ctrl()
    frames = [pose("puño", 0.5)] * 15 + [pose("puño", 0.5 - i * 0.01) for i in range(10)] + [pose("", 0.4)] * 12
    res = run(c, frames)
    k = kinds(res)
    assert k.count("window_grab") == 1 and k.count("window_release") == 1
    assert k.index("window_grab") < k.index("window_move") < k.index("window_release")
    assert "click" not in k and "down" not in k
    moves = [a.x for _, acts, _ in res for a in acts if a.kind == "window_move"]
    assert moves[-1] > moves[0]  # la mano va a la izquierda en la cámara → a la derecha en pantalla (espejo)
    assert any(s.gesture.startswith("Puño") for _, _, s in res)


def test_closing_fist_after_pinch_start_does_not_click():
    c = ctrl()
    frames = [pose("", pinch="index")] * 3 + [pose("puño")] * 15 + [pose("")] * 12
    k = kinds(run(c, frames))
    assert "click" not in k and k.count("window_grab") == 1


def test_low_confidence_gesture_is_ignored():
    c = ctrl()
    k = kinds(run(c, [pose("puño", score=0.4)] * 30))
    assert "window_grab" not in k


# --- palma: desplazar como palanca -----------------------------------------------

def test_open_palm_scrolls_like_a_joystick():
    c = ctrl()
    still = [pose("palma", cy=0.45)] * 25  # palma quieta 0.8 s
    down = [pose("palma", cy=0.45 + min(i, 10) * 0.012) for i in range(30)]
    res = run(c, still + down)
    scrolls = [a.amount for _, acts, _ in res for a in acts if a.kind == "scroll"]
    assert scrolls and all(n < 0 for n in scrolls)  # mano abajo → página abajo
    assert sum(scrolls) <= -5
    # El cursor queda quieto mientras desplaza.
    assert not any(a.kind == "move" for _, acts, _ in res[26:] for a in acts)

    c2 = ctrl()
    up = [pose("palma", cy=0.45 - min(i, 10) * 0.012) for i in range(30)]
    assert all(a.amount > 0 for _, acts, _ in run(c2, still + up) for a in acts if a.kind == "scroll")


def test_pointing_with_open_hand_does_not_scroll():
    c = ctrl()
    # La mano abierta se mueve todo el tiempo (apuntando): nunca se activa el desplazamiento.
    frames = [pose("palma", cx=0.3 + i * 0.006, cy=0.35 + (i % 20) * 0.006) for i in range(60)]
    res = run(c, frames)
    assert "scroll" not in kinds(res)
    assert sum(1 for _, acts, _ in res for a in acts if a.kind == "move") == 60


def test_moving_palm_sideways_leaves_scroll_mode():
    c = ctrl()
    frames = [pose("palma")] * 25 + [pose("palma", cx=0.5 - i * 0.02) for i in range(15)]
    res = run(c, frames)
    assert [a.kind for a in res[-1][1]] == ["move"]  # volvió a mover el cursor


def test_small_palm_drift_does_not_scroll():
    c = ctrl()
    frames = [pose("palma", cy=0.45 + (i % 3) * 0.003) for i in range(60)]
    assert "scroll" not in kinds(run(c, frames))


# --- gestos de una sola vez ------------------------------------------------------

def test_programmed_gesture_fires_once_per_pose():
    c = ctrl({"paz": "atajo:cmd+w", "pulgar_arriba": "orden:abre Chrome", "te_quiero": "escuchar"})
    frames = [pose("paz")] * 30 + [pose("")] * 12 + [pose("paz")] * 20 + [pose("")] * 12 + [pose("pulgar_arriba")] * 20 + [pose("")] * 12 + [pose("te_quiero")] * 20
    res = run(c, frames)
    values = [a.value for _, acts, _ in res for a in acts if a.kind == "gesture"]
    assert values == ["atajo:cmd+w", "atajo:cmd+w", "orden:abre Chrome", "escuchar"]


def test_click_gestures_and_unassigned_poses():
    c = ctrl({"pulgar_arriba": "doble_clic", "pulgar_abajo": "clic_derecho"})
    k = kinds(run(c, [pose("pulgar_arriba")] * 20 + [pose("")] * 12 + [pose("pulgar_abajo")] * 20 + [pose("paz")] * 20))
    assert k == ["click", "click", "click:right"]  # "paz" no tiene acción: no hace nada


def test_gestures_work_in_dwell_mode_too():
    c = ctrl(mode="dwell")
    assert "window_grab" in kinds(run(c, [pose("puño")] * 20))


# --- mover ventanas en macOS (API de Accesibilidad simulada) ----------------------

class FakeMouse:
    def __init__(self):
        self.log = []

    def press(self, x, y, button="left"):
        self.log.append(("down", x, y))

    def move(self, x, y):
        self.log.append(("move", x, y))

    def release(self, x, y, button="left"):
        self.log.append(("up", x, y))


def fake_ax(window_found=True):
    AS = pytypes.ModuleType("ApplicationServices")
    AS.kAXWindowAttribute, AS.kAXRoleAttribute, AS.kAXParentAttribute, AS.kAXPositionAttribute = "AXWindow", "AXRole", "AXParent", "AXPosition"
    window = {"AXRole": "AXWindow", "AXPosition": ("val", 100.0, 50.0)}
    button = {"AXRole": "AXButton", "AXWindow": window if window_found else None, "AXParent": None}
    AS.set_calls = []
    AS.AXUIElementCreateSystemWide = lambda: "system"
    AS.AXUIElementCopyElementAtPosition = lambda sysw, x, y, out: (0, button)
    AS.AXUIElementCopyAttributeValue = lambda el, name, out: (0, el.get(name)) if el.get(name) is not None else (-1, None)
    AS.AXValueGetValue = lambda value, kind, out: (True, pytypes.SimpleNamespace(x=value[1], y=value[2]))
    AS.AXValueCreate = lambda kind, point: ("val", point.x, point.y)
    AS.AXUIElementSetAttributeValue = lambda el, name, value: AS.set_calls.append((name, value[1], value[2]))
    Q = pytypes.ModuleType("Quartz")
    Q.CGPointMake = lambda x, y: pytypes.SimpleNamespace(x=x, y=y)
    return AS, Q


def test_mac_window_mover_moves_window_by_delta(monkeypatch):
    AS, Q = fake_ax()
    monkeypatch.setitem(sys.modules, "ApplicationServices", AS)
    monkeypatch.setitem(sys.modules, "Quartz", Q)
    mouse = FakeMouse()
    m = MacWindowMover(mouse)
    m.grab(500, 300)
    m.move(520, 290)
    m.move(600, 400)
    m.release(600, 400)
    assert AS.set_calls == [("AXPosition", 120.0, 40.0), ("AXPosition", 200.0, 150.0)]
    assert ("down", 500, 300) not in mouse.log  # no hizo falta arrastrar


def test_mac_window_mover_falls_back_to_drag(monkeypatch):
    AS, Q = fake_ax(window_found=False)
    monkeypatch.setitem(sys.modules, "ApplicationServices", AS)
    monkeypatch.setitem(sys.modules, "Quartz", Q)
    mouse = FakeMouse()
    m = MacWindowMover(mouse)
    m.grab(10, 10)
    m.move(20, 20)
    m.release(20, 20)
    assert mouse.log == [("down", 10, 10), ("move", 20, 20), ("up", 20, 20)]
    assert AS.set_calls == []


def test_drag_mover_release_only_if_grabbed():
    mouse = FakeMouse()
    d = DragMover(mouse)
    d.release(1, 1)
    assert mouse.log == []


# --- programar gestos por voz -----------------------------------------------------

def assistant(responses, monkeypatch):
    saved = []
    monkeypatch.setattr(Config, "save", lambda self, path=None: saved.append(dict(self.gestures)))
    actions = act.Actions()
    actions.speak = lambda t: None
    cfg = Config()
    v = VoiceAssistant(cfg, actions, api_key="x", client=FakeClient(responses))
    return v, cfg, saved


def test_assign_gesture_by_voice(monkeypatch):
    v, cfg, saved = assistant([
        call("asignar_gesto", gesto="paz", accion="atajo", valor="cmd+w"),
        text("Listo, con la señal de paz cierro la ventana."),
    ], monkeypatch)
    v.command(text="cuando haga la señal de paz cierra la ventana")
    assert cfg.gestures["paz"] == "atajo:cmd+w"
    assert saved and saved[-1]["paz"] == "atajo:cmd+w"
    # El controlador lee la misma configuración: el gesto funciona sin reiniciar.
    c = HandController(cfg, (1440, 900))
    values = [a.value for _, acts, _ in run(c, [pose("paz")] * 20) for a in acts if a.kind == "gesture"]
    assert values == ["atajo:cmd+w"]


def test_assign_gesture_validates(monkeypatch):
    v, cfg, saved = assistant([], monkeypatch)
    assert v.assign_gesture("ojo", "clic")["ok"] is False
    assert v.assign_gesture("paz", "volar")["ok"] is False
    assert v.assign_gesture("paz", "atajo", "cmd+ñ")["ok"] is False
    assert v.assign_gesture("paz", "orden", "")["ok"] is False
    assert saved == []
    assert v.assign_gesture("palma", "ninguna")["ok"] is True
    assert cfg.gestures["palma"] == "ninguna" and cfg.gestures["puño"] == "mover_ventana"


def test_system_prompt_lists_current_gestures(monkeypatch):
    v, cfg, _ = assistant([text("Hola.")], monkeypatch)
    cfg.gestures = {"puño": "mover_ventana", "pulgar_arriba": "orden:abre Chrome"}
    v.command(text="¿qué gestos tengo?")
    system = v.assistant.client.requests[-1]["config"].system_instruction
    assert "Puño = mover la ventana; Pulgar arriba = orden al asistente «abre Chrome»" in system
    names = [f.name for f in v.assistant.client.requests[-1]["config"].tools[0].function_declarations]
    assert "asignar_gesto" in names


def test_gesture_wake_makes_listener_ack():
    from sofia.listener import VoiceListener, WakeLogic

    lis = VoiceListener(WakeLogic(), on_command=lambda pcm, hint: False, on_ack=lambda: None)
    lis.wake()
    assert lis.wake_event.is_set()
