"""Control del ratón del sistema.

En macOS se usan eventos de Quartz directamente para poder marcar el número de
clic (kCGMouseEventClickState); así dos pellizcos seguidos cuentan como doble
clic en Finder y demás apps. En otros sistemas se usa pynput.
"""
from __future__ import annotations

import math
import sys
import time

LEFT, RIGHT = 0, 1  # kCGMouseButtonLeft / kCGMouseButtonRight
DOUBLE_CLICK_TIME = 0.5  # segundos
DOUBLE_CLICK_DISTANCE = 12  # píxeles


class _ClickCounter:
    def __init__(self) -> None:
        self.last = (-1.0, 0.0, 0.0, "")
        self.count = 0

    def next(self, x: float, y: float, button: str) -> int:
        t0, x0, y0, b0 = self.last
        now = time.monotonic()
        if button == b0 and now - t0 < DOUBLE_CLICK_TIME and math.dist((x, y), (x0, y0)) < DOUBLE_CLICK_DISTANCE:
            self.count = min(self.count + 1, 3)
        else:
            self.count = 1
        self.last = (now, x, y, button)
        return self.count


class MacMouse:
    def __init__(self) -> None:
        import Quartz

        self.Q = Quartz
        self.counter = _ClickCounter()
        self.down: set[str] = set()

    def screen_size(self) -> tuple[int, int]:
        b = self.Q.CGDisplayBounds(self.Q.CGMainDisplayID())
        return int(b.size.width), int(b.size.height)

    def _post(self, kind, x: float, y: float, button, click_state: int = 1) -> None:
        q = self.Q
        ev = q.CGEventCreateMouseEvent(None, kind, (x, y), button)
        q.CGEventSetIntegerValueField(ev, q.kCGMouseEventClickState, click_state)
        q.CGEventPost(q.kCGHIDEventTap, ev)

    def move(self, x: float, y: float) -> None:
        q = self.Q
        if "left" in self.down:
            self._post(q.kCGEventLeftMouseDragged, x, y, LEFT)
        else:
            self._post(q.kCGEventMouseMoved, x, y, LEFT)

    def _events(self, button: str):
        q = self.Q
        if button == "right":
            return q.kCGEventRightMouseDown, q.kCGEventRightMouseUp, RIGHT
        return q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp, LEFT

    def press(self, x: float, y: float, button: str = "left") -> None:
        down, _, b = self._events(button)
        self._post(down, x, y, b)
        self.down.add(button)

    def release(self, x: float, y: float, button: str = "left") -> None:
        _, up, b = self._events(button)
        self._post(up, x, y, b)
        self.down.discard(button)

    def click(self, x: float, y: float, button: str = "left") -> None:
        down, up, b = self._events(button)
        n = self.counter.next(x, y, button)
        self._post(down, x, y, b, n)
        self._post(up, x, y, b, n)

    def scroll(self, lines: int) -> None:
        q = self.Q
        ev = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 2, int(lines), 0)
        q.CGEventPost(q.kCGHIDEventTap, ev)


class PynputMouse:
    def __init__(self) -> None:
        from pynput.mouse import Button, Controller

        self.ctrl = Controller()
        self.buttons = {"left": Button.left, "right": Button.right}

    def screen_size(self) -> tuple[int, int]:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        size = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return size

    def move(self, x: float, y: float) -> None:
        self.ctrl.position = (int(x), int(y))

    def press(self, x: float, y: float, button: str = "left") -> None:
        self.move(x, y)
        self.ctrl.press(self.buttons[button])

    def release(self, x: float, y: float, button: str = "left") -> None:
        self.move(x, y)
        self.ctrl.release(self.buttons[button])

    def click(self, x: float, y: float, button: str = "left") -> None:
        self.move(x, y)
        self.ctrl.click(self.buttons[button])

    def scroll(self, lines: int) -> None:
        self.ctrl.scroll(0, lines)


def create_mouse():
    return MacMouse() if sys.platform == "darwin" else PynputMouse()


def accessibility_ok(prompt: bool = True) -> bool:
    """En macOS, controlar el ratón requiere el permiso de Accesibilidad."""
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        return True  # si no se puede verificar, se intenta de todos modos


def execute(mouse, action) -> None:
    """Ejecuta una gestures.Action en el ratón."""
    if action.kind == "move":
        mouse.move(action.x, action.y)
    elif action.kind == "click":
        mouse.click(action.x, action.y, action.button)
    elif action.kind == "down":
        mouse.press(action.x, action.y, action.button)
    elif action.kind == "up":
        mouse.release(action.x, action.y, action.button)
    elif action.kind == "scroll":
        mouse.scroll(action.amount)
