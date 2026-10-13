"""Bucle principal: cámara → MediaPipe → gestos → ratón."""
from __future__ import annotations

import subprocess
import sys
import time

import cv2

from .config import MODE_LABELS, MODES, Config
from .gestures import HandController, HeadController
from .mouse import accessibility_ok, create_mouse, execute
from .preview import draw
from .tracker import Tracker, open_camera

WINDOW = "Sofia"


def play(sound: str, enabled: bool) -> None:
    if not enabled or sys.platform != "darwin":
        return
    try:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class App:
    def __init__(self, cfg: Config, voice=None):
        self.cfg = cfg
        self.voice = voice  # VoiceAssistant o None
        self.pause_request: bool | None = None  # pedido por voz (otro hilo); se aplica en el bucle
        self.mouse = create_mouse()
        self.screen = self.mouse.screen_size()
        self.paused = False
        self.tracker: Tracker | None = None
        self.controller = None
        self.setup_mode()

    def setup_mode(self) -> None:
        kind = "face" if self.cfg.mode == "head" else "hand"
        if self.tracker is None or self.tracker.kind != kind:
            if self.tracker:
                self.tracker.close()
            self.tracker = Tracker(kind, self.cfg.hand)
        if self.cfg.mode == "head":
            self.controller = HeadController(self.cfg, self.screen)
        else:
            click = "dwell" if self.cfg.mode == "hand_dwell" else "pinch"
            self.controller = HandController(self.cfg, self.screen, click)
        print(f"Modo: {MODE_LABELS[self.cfg.mode]}", flush=True)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        for action in self.controller.reset():
            execute(self.mouse, action)  # suelta un arrastre en curso
        play("Pop" if self.paused else "Tink", self.cfg.sounds)
        print("Pausa" if self.paused else "Control reanudado", flush=True)

    def handle_key(self, key: int) -> bool:
        """Devuelve False para salir."""
        if key in (ord("q"), 27):
            return False
        if key == ord("p"):
            self.toggle_pause()
        elif key == ord("m"):
            self.controller.reset()
            self.cfg.mode = MODES[(MODES.index(self.cfg.mode) + 1) % len(MODES)]
            self.setup_mode()
        elif key == ord("c") and isinstance(self.controller, HeadController):
            self.controller.recalibrate()
        elif key in (ord("+"), ord("=")):
            self.set_dwell(self.cfg.dwell_time + 0.2)
        elif key in (ord("-"), ord("_")):
            self.set_dwell(self.cfg.dwell_time - 0.2)
        return True

    def request_pause(self, pause: bool) -> None:
        self.pause_request = pause

    def set_dwell(self, value: float) -> None:
        self.cfg.dwell_time = round(min(3.0, max(0.4, value)), 1)
        self.controller.dwell.dwell_time = self.cfg.dwell_time
        print(f"Tiempo de permanencia: {self.cfg.dwell_time} s", flush=True)

    def run(self) -> int:
        if not accessibility_ok():
            print(
                "\n⚠️  Falta el permiso de Accesibilidad.\n"
                "   Ajustes del Sistema → Privacidad y seguridad → Accesibilidad →\n"
                "   activa la app desde la que ejecutas Sofía (Terminal, iTerm o Visual Studio Code)\n"
                "   y vuelve a abrir Sofía.\n",
                flush=True,
            )
        cap = open_camera(self.cfg.camera_index)
        if not cap.isOpened():
            print(
                "No se pudo abrir la cámara. Revisa Ajustes del Sistema → Privacidad y seguridad → Cámara.",
                flush=True,
            )
            return 1
        if self.cfg.show_preview:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW, 480, 360)
            try:
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)
            except cv2.error:
                pass

        print("Sofía lista. Teclas en la ventana de vista previa: p pausa · m modo · c centrar · +/- tiempo · q salir", flush=True)
        play("Tink", self.cfg.sounds)
        if self.voice:
            self.voice.actions.on_cursor = self.request_pause
            self.voice.start()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                if self.pause_request is not None:
                    if self.pause_request != self.paused:
                        self.toggle_pause()
                    self.pause_request = None
                obs = self.tracker.process(frame)
                actions, status = self.controller.update(obs, time.monotonic())
                for action in actions:
                    if action.kind == "pause":
                        self.toggle_pause()
                    elif not self.paused:
                        execute(self.mouse, action)
                        if action.kind == "click":
                            play("Tink", self.cfg.sounds)

                if self.cfg.show_preview:
                    voice_state = self.voice.state if self.voice else ""
                    img = draw(frame, self.cfg, status, self.tracker.last_landmarks, self.screen, self.paused, self.tracker.kind, voice_state)
                    cv2.imshow(WINDOW, img)
                    if not self.handle_key(cv2.waitKey(1) & 0xFF):
                        break
        except KeyboardInterrupt:
            pass
        finally:
            if self.voice:
                self.voice.stop()
            for action in self.controller.reset():
                execute(self.mouse, action)
            cap.release()
            if self.cfg.show_preview:
                cv2.destroyAllWindows()
            self.tracker.close()
            self.cfg.save()
        return 0
