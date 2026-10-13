"""Une la escucha, Gemini y las acciones en el asistente "Sofía"."""
from __future__ import annotations

import threading

from .actions import Actions, create_actions
from .assistant import Assistant, friendly_error, load_api_key
from .config import Config
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
        self.assistant = Assistant(self.actions, key, cfg.gemini_model, client=client)
        self.state = "Voz apagada"
        self.listener: VoiceListener | None = None
        self.lock = threading.Lock()

    def set_state(self, text: str) -> None:
        self.state = text

    def start(self) -> None:
        logic = WakeLogic(self.cfg.wake_words, self.cfg.wake_confidence, self.cfg.followup_seconds)
        self.listener = VoiceListener(logic, self.command, self.ack, self.set_state, self.cfg.mic_device)
        self.listener.start()

    def stop(self) -> None:
        if self.listener:
            self.listener.stop()

    def ack(self) -> None:
        self.set_state("Te escucho…")
        self.actions.speak("¿Sí?")

    def command(self, pcm: bytes | None = None, hint: str = "", text: str = "") -> bool:
        """Procesa una orden. Devuelve True si Sofía hizo una pregunta (espera respuesta)."""
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
