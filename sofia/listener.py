"""Escucha del micrófono con la frase de activación ("hola Maki", "Sofía"…).

El reconocimiento es local (Vosk, sin internet): solo cuando una frase empieza
con la frase de activación se manda ese audio a Gemini. Después de que el
asistente pregunta algo, la siguiente frase cuenta como respuesta sin repetirla.

La comparación es por cómo suena, no por palabras: el modelo en español no
conoce "Maki" y escucha "hola Maki" como "hola maqui" o "hola aquí".
"""
from __future__ import annotations

import collections
import difflib
import json
import re
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
WAKE_POSITIONS = 3  # la activación puede empezar en las primeras palabras ("oye Sofía…", "hola Sofía…")
PAD = 0.35  # segundos de audio extra antes y después de la frase


@dataclass
class Decision:
    kind: str  # ignore | ack | command
    hint: str = ""
    start: float | None = None  # segundos desde que empezó la escucha
    end: float | None = None


ENGLISH = {"hi": "jai", "hey": "jei", "ok": "okei", "okay": "okei"}


def phonetic(text: str) -> str:
    """Escritura aproximada de cómo suena en español, sin espacios: "hi Maki" → "jaimaki"."""
    out = []
    for word in normalize(text).split():
        word = ENGLISH.get(word, word)
        word = re.sub(r"[^a-zñ]", "", word)
        word = word.replace("ch", "1").replace("qu", "k").replace("ll", "y").replace("h", "")
        word = re.sub(r"c(?=[ei])", "s", word).replace("c", "k").replace("z", "s").replace("v", "b")
        word = re.sub(r"g(?=[ei])", "j", word).replace("x", "ks").replace("w", "u").replace("y", "i")
        out.append(word.replace("1", "ch"))
    return re.sub(r"(.)\1+", r"\1", "".join(out))


def _tail_score(name: str, sounds: str) -> float:
    """Qué tan parecido suena el final de lo escuchado al nombre ("maki")."""
    return max(
        difflib.SequenceMatcher(None, name, sounds[-n:]).ratio()
        for n in range(max(1, len(name) - 1), len(name) + 2)
    )


def match_wake(words: list[str], phrase: str, threshold: float) -> tuple[int, float] | None:
    """Si las palabras empiezan con algo que suena como la frase, devuelve (palabras usadas, parecido).

    Pide dos cosas: que toda la frase suene parecida y que el nombre (la última
    palabra) también, para que "hola mami" o "hola Mari" no activen "hola Maki".
    """
    target = phonetic(phrase)
    name = phonetic(phrase.split()[-1]) if phrase.split() else ""
    if not target:
        return None
    best = None
    sounds = ""
    for i, w in enumerate(words):
        sounds += phonetic(w)
        if len(sounds) > len(target) + 3:
            break
        score = difflib.SequenceMatcher(None, target, sounds).ratio()
        if score >= threshold and _tail_score(name, sounds) >= threshold and (best is None or score > best[1]):
            best = (i + 1, score)
    return best


@dataclass
class WakeLogic:
    """Decide qué hacer con cada frase reconocida. No depende del micrófono (se prueba sola)."""

    wake_words: list[str] = field(default_factory=lambda: ["hola maki"])
    min_conf: float = 0.5
    followup_seconds: float = 8.0
    similarity: float = 0.8
    followup_until: float = 0.0

    def expect_reply(self, now: float) -> None:
        self.followup_until = now + self.followup_seconds

    def find_wake(self, words: list[dict]) -> int | None:
        """Índice de la primera palabra después de la activación, o None."""
        texts = [w["word"] for w in words]
        for start in range(min(WAKE_POSITIONS, len(words))):
            for phrase in self.wake_words:
                found = match_wake(texts[start:], phrase, self.similarity)
                if not found:
                    continue
                # El modelo no conoce nombres como "Maki" y duda en alguna palabra:
                # basta con que una se haya oído con seguridad; el sonido decide lo demás.
                used = words[start:start + found[0]]
                if max(w.get("conf", 1.0) for w in used) >= self.min_conf:
                    return start + found[0]
        return None

    def decide(self, words: list[dict], now: float) -> Decision:
        words = [w for w in words if w.get("word") and w["word"] != "[unk]"]
        if not words:
            return Decision("ignore")
        after = self.find_wake(words)
        if after is not None:
            rest = words[after:]
            if not rest:
                self.expect_reply(now)
                return Decision("ack")
            self.followup_until = 0.0
            return Decision("command", " ".join(x["word"] for x in rest), words[0].get("start"), words[-1].get("end"))
        if now < self.followup_until:
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

    def __init__(self, logic: WakeLogic, on_command, on_ack, on_state=None, device=None, idle_text="Te escucho"):
        super().__init__(daemon=True, name="sofia-voz")
        self.logic = logic
        self.on_command = on_command  # (pcm: bytes, hint: str) -> bool (True si Sofía hizo una pregunta)
        self.on_ack = on_ack  # () -> None: responde "¿Sí?"
        self.on_state = on_state or (lambda s: None)
        self.device = device
        self.idle_text = idle_text  # por ejemplo «Di "hola Maki"»
        self.audio: queue.Queue[bytes] = queue.Queue()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()  # despertar sin decir la frase (por ejemplo, con un gesto)
        self.error: str = ""

    def stop(self) -> None:
        self.stop_event.set()

    def wake(self) -> None:
        """Como si se hubiera dicho solo la frase de activación: responde "¿Sí?" y escucha."""
        self.wake_event.set()

    def _callback(self, indata, frames, time_info, status) -> None:
        self.audio.put(bytes(indata))

    def _drain(self) -> None:
        while True:
            try:
                self.audio.get_nowait()
            except queue.Empty:
                return

    def run(self) -> None:
        step = "Preparando la voz…"
        try:
            self.on_state(step)
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)
            if not (config_dir() / "models" / VOSK_MODEL / "am").exists():
                step = "Descargando voz (40 MB)…"
                self.on_state(step)
            path = ensure_vosk_model()
            step = "Cargando voz…"
            self.on_state(step)
            model = Model(str(path))
            step = "Abriendo micrófono…"
            self.on_state(step)
            stream = sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, channels=1, dtype="int16", device=self.device, callback=self._callback)
        except Exception as e:  # sin micrófono, sin permiso o sin internet para el modelo
            self.error = f"{type(e).__name__}: {e}"
            self.on_state("Error de voz: ver Terminal")
            print(f"⚠️  El asistente de voz no pudo iniciar ({step}): {self.error}", flush=True)
            return

        rec = KaldiRecognizer(model, RATE)
        rec.SetWords(True)
        buf: collections.deque[bytes] = collections.deque(maxlen=int(30 * RATE / BLOCK))  # máximo 30 s
        fed = 0  # muestras procesadas desde el último Reset
        buf_start = 0  # muestra en la que empieza buf
        silent_blocks = 0  # macOS entrega puro silencio si la app no tiene permiso de Micrófono
        warned_silence = False
        with stream:
            self.on_state(self.idle_text)
            print(f"🎙️  Escuchando. {self.idle_text} y tu orden.", flush=True)
            while not self.stop_event.is_set():
                if self.wake_event.is_set():
                    self.wake_event.clear()
                    stream.stop()
                    try:
                        self.on_ack()
                        self.logic.expect_reply(time.monotonic())
                    finally:
                        self._drain()
                        rec.Reset()
                        buf.clear()
                        fed = buf_start = 0
                        if not self.stop_event.is_set():
                            stream.start()
                        self.on_state("Te escucho…")
                    continue
                try:
                    block = self.audio.get(timeout=0.3)
                except queue.Empty:
                    continue
                if not warned_silence:
                    silent_blocks = silent_blocks + 1 if not any(block) else -1_000_000
                    if silent_blocks >= 50:  # 5 s de ceros exactos
                        warned_silence = True
                        self.on_state("Sin audio: permiso de Micrófono")
                        print(
                            "⚠️  El micrófono solo entrega silencio. Activa la Terminal en\n"
                            "   Ajustes del Sistema → Privacidad y seguridad → Micrófono, y vuelve a abrir Sofía.",
                            flush=True,
                        )
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
                    self.on_state("Te escucho…" if time.monotonic() < self.logic.followup_until else self.idle_text)


def trim(pcm: bytes, first_sample: int, start: float | None, end: float | None) -> bytes:
    """Recorta el audio a la frase (con un margen) usando los tiempos de las palabras."""
    if start is None or end is None:
        return pcm
    a = max(0, int((start - PAD) * RATE) - first_sample) * 2
    b = min(len(pcm), (int((end + PAD) * RATE) - first_sample) * 2)
    return pcm[a:b] if b - a > RATE // 2 else pcm  # si algo no cuadra, se manda completo
