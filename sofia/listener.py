"""Escucha del micrófono con la palabra clave "Sofía".

El reconocimiento de la palabra clave es local (Vosk, sin internet): solo
cuando una frase empieza con "Sofía" se manda ese audio a Gemini. Después de
que Sofía pregunta algo, la siguiente frase cuenta como respuesta sin tener
que volver a decir "Sofía".
"""
from __future__ import annotations

import collections
import json
import queue
import ssl
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .actions import normalize
from .config import config_dir

RATE = 16000
BLOCK = 1600  # 0.1 s
VOSK_MODEL = "vosk-model-small-es-0.42"
VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip"
WAKE_POSITIONS = 3  # "Sofía" debe estar entre las primeras palabras ("oye Sofía…", "hola Sofía…")
PAD = 0.35  # segundos de audio extra antes y después de la frase


@dataclass
class Decision:
    kind: str  # ignore | ack | command
    hint: str = ""
    start: float | None = None  # segundos desde que empezó la escucha
    end: float | None = None


@dataclass
class WakeLogic:
    """Decide qué hacer con cada frase reconocida. No depende del micrófono (se prueba sola)."""

    wake_words: list[str] = field(default_factory=lambda: ["sofia"])
    min_conf: float = 0.6
    followup_seconds: float = 8.0
    followup_until: float = 0.0

    def expect_reply(self, now: float) -> None:
        self.followup_until = now + self.followup_seconds

    def decide(self, words: list[dict], now: float) -> Decision:
        words = [w for w in words if w.get("word") and w["word"] != "[unk]"]
        if not words:
            return Decision("ignore")
        wake = {normalize(w) for w in self.wake_words}
        for i, w in enumerate(words[:WAKE_POSITIONS]):
            if normalize(w["word"]) in wake and w.get("conf", 1.0) >= self.min_conf:
                rest = words[i + 1:]
                if not rest:
                    self.expect_reply(now)
                    return Decision("ack")
                self.followup_until = 0.0
                return Decision("command", " ".join(x["word"] for x in rest), words[0].get("start"), words[-1].get("end"))
        if now <= self.followup_until:
            self.followup_until = 0.0
            return Decision("command", " ".join(x["word"] for x in words), words[0].get("start"), words[-1].get("end"))
        return Decision("ignore")


def ensure_vosk_model(directory: Path | None = None) -> Path:
    """Descarga el modelo de voz en español (unos 40 MB) la primera vez."""
    directory = directory or config_dir() / "models"
    path = directory / VOSK_MODEL
    if (path / "am").exists():
        return path
    directory.mkdir(parents=True, exist_ok=True)
    print("Descargando el modelo de voz en español (40 MB, solo la primera vez)…", flush=True)
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    tmp = directory / f"{VOSK_MODEL}.zip.part"
    with urllib.request.urlopen(VOSK_URL, context=context, timeout=120) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(directory)
    tmp.unlink(missing_ok=True)
    return path


class VoiceListener(threading.Thread):
    """Hilo que escucha el micrófono y llama a on_command(pcm, pista) con cada orden."""

    def __init__(self, logic: WakeLogic, on_command, on_ack, on_state=None, device=None):
        super().__init__(daemon=True, name="sofia-voz")
        self.logic = logic
        self.on_command = on_command  # (pcm: bytes, hint: str) -> bool (True si Sofía hizo una pregunta)
        self.on_ack = on_ack  # () -> None: responde "¿Sí?"
        self.on_state = on_state or (lambda s: None)
        self.device = device
        self.audio: queue.Queue[bytes] = queue.Queue()
        self.stop_event = threading.Event()
        self.error: str = ""

    def stop(self) -> None:
        self.stop_event.set()

    def _callback(self, indata, frames, time_info, status) -> None:
        self.audio.put(bytes(indata))

    def _drain(self) -> None:
        while True:
            try:
                self.audio.get_nowait()
            except queue.Empty:
                return

    def run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)
            model = Model(str(ensure_vosk_model()))
            stream = sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, channels=1, dtype="int16", device=self.device, callback=self._callback)
        except Exception as e:  # sin micrófono, sin permiso o sin internet para el modelo
            self.error = f"{type(e).__name__}: {e}"
            self.on_state("Voz no disponible")
            print(f"⚠️  El asistente de voz no pudo iniciar: {self.error}", flush=True)
            return

        rec = KaldiRecognizer(model, RATE)
        rec.SetWords(True)
        buf: collections.deque[bytes] = collections.deque(maxlen=int(30 * RATE / BLOCK))  # máximo 30 s
        fed = 0  # muestras procesadas desde el último Reset
        buf_start = 0  # muestra en la que empieza buf
        with stream:
            self.on_state("Di «Sofía»")
            print("🎙️  Escuchando. Di «Sofía» y tu orden.", flush=True)
            while not self.stop_event.is_set():
                try:
                    block = self.audio.get(timeout=0.3)
                except queue.Empty:
                    continue
                if len(buf) == buf.maxlen:
                    buf_start += len(buf[0]) // 2
                buf.append(block)
                fed += len(block) // 2
                if not rec.AcceptWaveform(block):
                    continue
                result = json.loads(rec.Result())
                pcm, first = b"".join(buf), buf_start
                decision = self.logic.decide(result.get("result", []), time.monotonic())
                buf.clear()
                buf_start = fed
                if decision.kind == "ignore":
                    continue

                stream.stop()  # no escucharse a sí misma mientras habla o actúa
                try:
                    if decision.kind == "ack":
                        self.on_ack()
                    else:
                        pcm = trim(pcm, first, decision.start, decision.end)
                        self.on_state("Pensando…")
                        if self.on_command(pcm, decision.hint):
                            self.logic.expect_reply(time.monotonic())
                finally:
                    self._drain()
                    rec.Reset()
                    fed = buf_start = 0
                    if not self.stop_event.is_set():
                        stream.start()
                    self.on_state("Te escucho…" if time.monotonic() <= self.logic.followup_until else "Di «Sofía»")


def trim(pcm: bytes, first_sample: int, start: float | None, end: float | None) -> bytes:
    """Recorta el audio a la frase (con un margen) usando los tiempos de las palabras."""
    if start is None or end is None:
        return pcm
    a = max(0, int((start - PAD) * RATE) - first_sample) * 2
    b = min(len(pcm), (int((end + PAD) * RATE) - first_sample) * 2)
    return pcm[a:b] if b - a > RATE // 2 else pcm  # si algo no cuadra, se manda completo
