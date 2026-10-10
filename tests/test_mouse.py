"""Prueba del ratón de macOS con un módulo Quartz simulado."""
import sys
import types

from sofia import mouse as mouse_mod
from sofia.gestures import Action


def fake_quartz(log):
    q = types.ModuleType("Quartz")
    for i, name in enumerate([
        "kCGEventMouseMoved", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGEventLeftMouseDragged",
        "kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGMouseEventClickState", "kCGHIDEventTap",
        "kCGScrollEventUnitLine",
    ]):
        setattr(q, name, name)
    q.CGEventCreateMouseEvent = lambda src, kind, pos, button: {"kind": kind, "pos": pos, "button": button}
    q.CGEventSetIntegerValueField = lambda ev, field, value: ev.__setitem__("click", value)
    q.CGEventCreateScrollWheelEvent = lambda src, unit, count, *wheels: {"kind": "scroll", "wheels": wheels}
    q.CGEventPost = lambda tap, ev: log.append(ev)
    return q


def test_mac_mouse_double_click_and_drag(monkeypatch):
    log = []
    monkeypatch.setitem(sys.modules, "Quartz", fake_quartz(log))
    m = mouse_mod.MacMouse()
    mouse_mod.execute(m, Action("click", 100, 100))
    mouse_mod.execute(m, Action("click", 103, 101))  # segundo clic rápido y cerca → doble clic
    assert [e["click"] for e in log] == [1, 1, 2, 2]
    assert log[0]["kind"] == "kCGEventLeftMouseDown" and log[1]["kind"] == "kCGEventLeftMouseUp"

    log.clear()
    mouse_mod.execute(m, Action("down", 10, 10))
    mouse_mod.execute(m, Action("move", 50, 50))
    mouse_mod.execute(m, Action("up", 50, 50))
    mouse_mod.execute(m, Action("move", 60, 60))
    assert [e["kind"] for e in log] == ["kCGEventLeftMouseDown", "kCGEventLeftMouseDragged", "kCGEventLeftMouseUp", "kCGEventMouseMoved"]

    log.clear()
    mouse_mod.execute(m, Action("click", 5, 5, button="right"))
    mouse_mod.execute(m, Action("scroll", amount=3))
    assert log[0]["button"] == mouse_mod.RIGHT and log[0]["kind"] == "kCGEventRightMouseDown"
    assert log[-1] == {"kind": "scroll", "wheels": (3, 0)}
