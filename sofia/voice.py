"""Une la escucha, Gemini y las acciones en el asistente de voz ("Maki", "Sofía"…)."""
from __future__ import annotations

import threading

from .actions import Actions, create_actions
from .assistant import Assistant, friendly_error, load_api_key
from .actions import parse_shortcut
from .config import Config
from .gestures import GESTURE_ACTIONS, POSES, describe_bindings
from .listener import VoiceListener, WakeLogic

NO_KEY = (
    "Falta la clave de Gemini para el asistente de voz.\n"
    "   1. Créala gratis en https://aistudio.google.com/apikey\n"
    "   2. Guárdala con:  python -m sofia --clave-gemini\n"
    "   (o vuelve a abrir «Iniciar Sofia.command», que te la pide)."
)


class VoiceAssistant:
    def __init__(self, cfg: Config, actions: Actions | None = None, api_key: str | None = None, client=None):
        self.cfg = cfg
        self.actions = actions or create_actions(cfg.voice_name)
        key = api_key if api_key is not None else load_api_key()
        if not key and client is None:
            raise RuntimeError(NO_KEY)
        self.assistant = Assistant(self.actions, key, cfg.gemini_model, client=client, name=cfg.assistant_name, wake=self.wake_text())
        self.actions.name = cfg.assistant_name
        self.actions.on_rename = self.rename
        self.actions.on_gesture = self.assign_gesture
        self.assistant.gestures_text = lambda: describe_bindings(self.cfg.gestures)
        self.state = "Preparando la voz…"
        self.logic = WakeLogic(cfg.wake_words, cfg.wake_confidence, cfg.followup_seconds, cfg.wake_similarity)
        self.listener: VoiceListener | None = None
        self.lock = threading.Lock()

    def wake_text(self) -> str:
        return self.cfg.wake_words[0] if self.cfg.wake_words else self.cfg.assistant_name

    def idle_text(self) -> str:
        return f'Di "{self.wake_text()}"'

    def rename(self, name: str, phrase: str) -> dict:
        """Cambia el nombre y la frase de activación, y lo guarda para la próxima vez."""
        self.cfg.assistant_name = name
        self.cfg.wake_words = [phrase]
        self.cfg.save()
        self.logic.wake_words = [phrase]
        self.assistant.name, self.assistant.wake = name, phrase
        self.actions.name = name
        if self.listener:
            self.listener.idle_text = self.idle_text()
        return {"ok": True, "nombre": name, "frase_activacion": phrase}

    def assign_gesture(self, pose: str, action: str, value: str = "") -> dict:
        """Programa un gesto de la mano. El control con cámara lo usa al instante (lee la misma configuración)."""
        value = " ".join(value.split())
        if pose not in POSES:
            return {"ok": False, "error": f"Gesto desconocido. Usa: {', '.join(POSES)}."}
        if action not in GESTURE_ACTIONS:
            return {"ok": False, "error": f"Acción desconocida. Usa: {', '.join(GESTURE_ACTIONS)}."}
        if action == "atajo":
            try:
                parse_shortcut(value)
            except ValueError as e:
                return {"ok": False, "error": f"Atajo no válido: {e}"}
        if action == "orden" and not 0 < len(value) <= 200:
            return {"ok": False, "error": "Falta la orden (máximo 200 letras)."}
        binding = f"{action}:{value}" if action in ("atajo", "orden") else action
        self.cfg.gestures = {**self.cfg.gestures, pose: binding}
        self.cfg.save()
        return {"ok": True, "gesto": POSES[pose], "accion": GESTURE_ACTIONS[action], "valor": value}

    def alive(self) -> bool:
        return self.listener is not None and self.listener.is_alive()

    def set_state(self, text: str) -> None:
        self.state = text

    def start(self) -> None:
        self.listener = VoiceListener(self.logic, self.command, self.ack, self.set_state, self.cfg.mic_device, self.idle_text())
        self.listener.start()

    def stop(self) -> None:
        if self.listener:
            self.listener.stop()

    def ack(self) -> None:
        self.set_state("Te escucho…")
        self.actions.speak("¿Sí?")

    def command(self, pcm: bytes | None = None, hint: str = "", text: str = "") -> bool:
        """Procesa una orden. Devuelve True si la asistente hizo una pregunta (espera respuesta)."""
        with self.lock:
            print(f"🗣️  {hint or text}", flush=True)
            self.set_state("Pensando…")
            try:
                reply = self.assistant.handle(audio_pcm=pcm, hint=hint, text=text)
            except Exception as e:  # sin internet, clave inválida, cuota…
                print(f"⚠️  Gemini: {type(e).__name__}: {e}", flush=True)
                reply = friendly_error(e)
            if not reply:
                return False
            self.set_state("Hablando…")
            self.actions.speak(reply)
            return reply.rstrip().endswith("?")
