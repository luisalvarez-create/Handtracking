"""Mover la ventana que está bajo el cursor (gesto de puño).

En macOS se usa la API de Accesibilidad: se agarra la ventana desde cualquier
punto, no solo desde la barra de título. Si no se puede (por ejemplo, el
escritorio o una app que no lo permite), se hace un arrastre normal del ratón.
"""
from __future__ import annotations

import sys


class DragMover:
    """Respaldo: mantiene presionado el botón y arrastra (mueve la ventana si se agarró por el título)."""

    def __init__(self, mouse):
        self.mouse = mouse
        self.active = False

    def grab(self, x: float, y: float) -> None:
        self.mouse.press(x, y)
        self.active = True

    def move(self, x: float, y: float) -> None:
        if self.active:
            self.mouse.move(x, y)

    def release(self, x: float, y: float) -> None:
        if self.active:
            self.mouse.release(x, y)
        self.active = False


class MacWindowMover:
    def __init__(self, mouse):
        import ApplicationServices as AS
        import Quartz

        self.AS, self.Q = AS, Quartz
        # El nombre de la constante cambió entre versiones de macOS (kAXValueCGPointType = kAXValueTypeCGPoint = 1).
        self.point_type = getattr(AS, "kAXValueCGPointType", getattr(AS, "kAXValueTypeCGPoint", 1))
        self.mouse = mouse
        self.fallback = DragMover(mouse)
        self.window = None
        self.start = (0.0, 0.0)  # posición del cursor al agarrar
        self.origin = (0.0, 0.0)  # posición de la ventana al agarrar

    def _attr(self, element, name):
        err, value = self.AS.AXUIElementCopyAttributeValue(element, name, None)
        return None if err else value

    def window_at(self, x: float, y: float):
        AS = self.AS
        err, element = AS.AXUIElementCopyElementAtPosition(AS.AXUIElementCreateSystemWide(), x, y, None)
        if err or element is None:
            return None
        window = self._attr(element, AS.kAXWindowAttribute)
        if window is not None:
            return window
        for _ in range(30):  # sube por los padres hasta encontrar la ventana
            if self._attr(element, AS.kAXRoleAttribute) == "AXWindow":
                return element
            element = self._attr(element, AS.kAXParentAttribute)
            if element is None:
                return None
        return None

    def _position(self, window):
        value = self._attr(window, self.AS.kAXPositionAttribute)
        if value is None:
            return None
        ok, point = self.AS.AXValueGetValue(value, self.point_type, None)
        return (point.x, point.y) if ok else None

    def grab(self, x: float, y: float) -> None:
        self.window = None
        try:
            window = self.window_at(x, y)
            origin = self._position(window) if window is not None else None
        except Exception:
            window, origin = None, None
        if window is None or origin is None:
            self.fallback.grab(x, y)
            return
        self.window, self.origin, self.start = window, origin, (x, y)

    def move(self, x: float, y: float) -> None:
        if self.window is None:
            self.fallback.move(x, y)
            return
        self.mouse.move(x, y)
        try:
            point = self.Q.CGPointMake(self.origin[0] + x - self.start[0], self.origin[1] + y - self.start[1])
            value = self.AS.AXValueCreate(self.point_type, point)
            self.AS.AXUIElementSetAttributeValue(self.window, self.AS.kAXPositionAttribute, value)
        except Exception:
            # Si la app no deja moverla, se sigue como arrastre normal desde aquí.
            self.window = None
            self.fallback.grab(x, y)

    def release(self, x: float, y: float) -> None:
        if self.window is None:
            self.fallback.release(x, y)
        self.window = None


def create_window_mover(mouse):
    if sys.platform == "darwin":
        try:
            return MacWindowMover(mouse)
        except ImportError:
            pass
    return DragMover(mouse)
