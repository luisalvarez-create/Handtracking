"""Acciones que el asistente de voz puede hacer en la computadora.

Gemini nunca ejecuta comandos libres: solo puede pedir estas acciones, y cada una
valida sus datos (apps instaladas, ligas http/https, teclas conocidas).
"""
from __future__ import annotations

import difflib
import os
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import webbrowser
from pathlib import Path


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni espacios repetidos: "Cálculadora " → "calculadora"."""
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace(".app", "").split())


# Nombres en español (o abreviados) → nombre de la app en macOS.
APP_ALIASES = {
    "chrome": "Google Chrome",
    "google": "Google Chrome",
    "navegador": "Safari",
    "internet": "Safari",
    "edge": "Microsoft Edge",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "power point": "Microsoft PowerPoint",
    "outlook": "Microsoft Outlook",
    "teams": "Microsoft Teams",
    "zoom": "zoom.us",
    "calculadora": "Calculator",
    "notas": "Notes",
    "correo": "Mail",
    "calendario": "Calendar",
    "musica": "Music",
    "fotos": "Photos",
    "mapas": "Maps",
    "mensajes": "Messages",
    "recordatorios": "Reminders",
    "contactos": "Contacts",
    "ajustes": "System Settings",
    "configuracion": "System Settings",
    "preferencias": "System Settings",
    "preferencias del sistema": "System Settings",
    "vista previa": "Preview",
    "editor de texto": "TextEdit",
    "libros": "Books",
    "reloj": "Clock",
    "clima": "Weather",
    "tiempo": "Weather",
    "camara": "Photo Booth",
    "tienda": "App Store",
}

APP_DIRS = [
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]


def installed_apps(dirs=None) -> list[str]:
    names = set()
    for d in dirs or APP_DIRS:
        try:
            names.update(p.stem for p in d.glob("*.app"))
        except OSError:
            pass
    return sorted(names)


def resolve_app(name: str, installed: list[str]) -> tuple[str | None, list[str]]:
    """Devuelve (app encontrada, sugerencias). Busca alias, nombre exacto, parcial y parecido."""
    by_norm = {normalize(a): a for a in installed}

    def target(key: str) -> str | None:
        """Una clave normalizada (alias o nombre) → app instalada, si existe."""
        alias = APP_ALIASES.get(key)
        if alias and normalize(alias) in by_norm:
            return by_norm[normalize(alias)]
        return by_norm.get(key)

    wanted = normalize(name)
    if not wanted:
        return None, []
    if app := target(wanted):
        return app, []
    partial = [a for n, a in by_norm.items() if wanted in n]
    if len(partial) == 1:
        return partial[0], []
    if partial:
        return None, partial[:3]
    close = []
    for key in difflib.get_close_matches(wanted, list(APP_ALIASES) + list(by_norm), n=3, cutoff=0.75):
        app = target(key)
        if app and app not in close:
            close.append(app)
    if len(close) == 1:
        return close[0], []
    return None, close


def safe_url(url: str) -> str | None:
    """Solo ligas web. Agrega https:// si falta; rechaza file:, javascript:, etc."""
    url = url.strip()
    if not url:
        return None
    if "://" not in url and not url.lower().startswith(("http:", "https:")):
        if ":" in url.split("/")[0] and not url.split("/")[0].split(":")[-1].isdigit():
            return None  # esquema distinto, por ejemplo "javascript:" o "mailto:"
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url


SEARCH_SITES = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "maps": "https://www.google.com/maps/search/{}",
    "mapas": "https://www.google.com/maps/search/{}",
    "wikipedia": "https://es.wikipedia.org/w/index.php?search={}",
    "amazon": "https://www.amazon.com.mx/s?k={}",
    "mercado libre": "https://listado.mercadolibre.com.mx/{}",
    "mercadolibre": "https://listado.mercadolibre.com.mx/{}",
}


def search_url(query: str, site: str = "google") -> str:
    template = SEARCH_SITES.get(normalize(site or "google"), SEARCH_SITES["google"])
    return template.format(urllib.parse.quote_plus(query.strip()))


# Códigos de tecla de macOS (posición física, teclado QWERTY).
KEYCODES = {
    **{c: k for c, k in zip("asdfhgzxcv", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])},
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
    "=": 24, "-": 27, ",": 43, ".": 47, "/": 44,
    "enter": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53, "forwarddelete": 117,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101,
    "f10": 109, "f11": 103, "f12": 111,
}
KEY_ALIASES = {
    "intro": "enter", "return": "enter", "entrar": "enter", "tabulador": "tab", "esc": "escape",
    "espacio": "space", "borrar": "delete", "retroceso": "delete", "backspace": "delete", "suprimir": "forwarddelete",
    "supr": "forwarddelete", "inicio": "home", "fin": "end", "arriba": "up", "abajo": "down",
    "izquierda": "left", "derecha": "right", "avpag": "pagedown", "repag": "pageup",
}
MODIFIERS = {
    "cmd": "cmd", "command": "cmd", "comando": "cmd", "⌘": "cmd",
    "shift": "shift", "mayus": "shift", "mayusculas": "shift",
    "alt": "alt", "option": "alt", "opcion": "alt",
    "ctrl": "ctrl", "control": "ctrl",
}


def parse_shortcut(text: str) -> tuple[list[str], str]:
    """"cmd+shift+t" → (["cmd", "shift"], "t"). Lanza ValueError si la tecla no existe."""
    parts = [normalize(p) for p in text.replace(" + ", "+").replace("-", "+").split("+") if p.strip()]
    if text.strip().endswith("-"):
        parts.append("-")
    if not parts:
        raise ValueError("Atajo vacío")
    *mods, key = parts
    raw_key = text.replace(" + ", "+").replace("-", "+").split("+")[-1].strip().lower() or key
    if len(raw_key) == 1:
        key = raw_key  # una sola letra se respeta tal cual ("ñ" no se vuelve "n")
    mods_out = []
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"Modificador desconocido: {m}")
        mods_out.append(MODIFIERS[m])
    key = KEY_ALIASES.get(key, key)
    if key not in KEYCODES:
        raise ValueError(f"Tecla desconocida: {key}")
    return mods_out, key


class Actions:
    """Implementación base: registra lo que haría (modo simulación y pruebas)."""

    def __init__(self) -> None:
        self.log: list[tuple[str, dict]] = []
        self.on_cursor = None  # callback(pausar: bool) que pone la app principal

    def _record(self, name: str, **kw) -> dict:
        self.log.append((name, kw))
        print(f"  [simulación] {name} {kw}", flush=True)
        return {"ok": True}

    def apps(self) -> list[str]:
        return ["Google Chrome", "Safari", "Microsoft Word", "Notes", "Calculator", "Mail", "System Settings"]

    # --- acciones ---------------------------------------------------------

    def open_app(self, name: str) -> dict:
        app, suggestions = resolve_app(name, self.apps())
        if not app:
            return {"ok": False, "error": f"No encontré la app «{name}».", "sugerencias": suggestions}
        self._launch(app)
        return {"ok": True, "app": app}

    def open_url(self, url: str, browser: str = "") -> dict:
        clean = safe_url(url)
        if not clean:
            return {"ok": False, "error": "Solo puedo abrir páginas web (http o https)."}
        return self._open(clean, browser)

    def web_search(self, query: str, site: str = "google", browser: str = "") -> dict:
        if not query.strip():
            return {"ok": False, "error": "Falta qué buscar."}
        return self._open(search_url(query, site), browser)

    def _open(self, url: str, browser: str) -> dict:
        app = None
        if browser:
            app, _ = resolve_app(browser, self.apps())
        self._open_url(url, app)
        return {"ok": True, "url": url, "navegador": app or "predeterminado"}

    def type_text(self, text: str) -> dict:
        if not text:
            return {"ok": False, "error": "No hay texto."}
        self._paste(text)
        return {"ok": True, "caracteres": len(text)}

    def press_keys(self, shortcut: str) -> dict:
        try:
            mods, key = parse_shortcut(shortcut)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        self._key(mods, key)
        return {"ok": True}

    def scroll(self, direction: str, amount: int = 5) -> dict:
        amount = max(1, min(30, int(amount or 5)))
        lines = amount if normalize(direction) in ("arriba", "up") else -amount
        self._scroll(lines)
        return {"ok": True}

    def set_volume(self, level: str) -> dict:
        level = normalize(str(level))
        if level not in ("subir", "bajar", "silenciar", "activar") and not level.isdigit():
            return {"ok": False, "error": "Usa subir, bajar, silenciar, activar o un número de 0 a 100."}
        self._volume(level)
        return {"ok": True}

    def cursor(self, pause: bool) -> dict:
        if self.on_cursor is None:
            return {"ok": False, "error": "El control con cámara no está activo."}
        self.on_cursor(pause)
        return {"ok": True}

    def wait(self, seconds: float) -> dict:
        time.sleep(max(0.0, min(5.0, float(seconds or 1))))
        return {"ok": True}

    def speak(self, text: str) -> None:
        print(f"Sofía: {text}", flush=True)

    # --- primitivas (las reemplaza cada sistema) --------------------------

    def _launch(self, app: str) -> None:
        self._record("abrir_app", app=app)

    def _open_url(self, url: str, app: str | None) -> None:
        self._record("abrir_url", url=url, app=app)

    def _paste(self, text: str) -> None:
        self._record("escribir", texto=text)

    def _key(self, mods: list[str], key: str) -> None:
        self._record("teclas", mods=mods, key=key)

    def _scroll(self, lines: int) -> None:
        self._record("desplazar", lineas=lines)

    def _volume(self, level: str) -> None:
        self._record("volumen", nivel=level)


UTF8 = {**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}  # para que pbcopy respete acentos


class MacActions(Actions):
    def __init__(self, voice: str = "") -> None:
        super().__init__()
        import Quartz

        self.Q = Quartz
        self._apps: list[str] | None = None
        self.voice = voice or self._spanish_voice()

    def _record(self, name: str, **kw) -> dict:
        self.log.append((name, kw))
        return {"ok": True}

    def apps(self) -> list[str]:
        if self._apps is None:
            self._apps = installed_apps()
        return self._apps

    def _launch(self, app: str) -> None:
        subprocess.run(["open", "-a", app], check=False, capture_output=True, timeout=15)
        self._wait_front(app)

    def _wait_front(self, app: str, timeout: float = 6.0) -> None:
        """Espera a que la app quede al frente para que las teclas lleguen a ella."""
        try:
            from AppKit import NSWorkspace
        except ImportError:
            time.sleep(1.5)
            return
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            if front and normalize(str(front.localizedName())) in (normalize(app), normalize(APP_ALIASES.get(normalize(app), app))):
                time.sleep(0.4)
                return
            time.sleep(0.2)

    def _open_url(self, url: str, app: str | None) -> None:
        cmd = ["open", "-a", app, url] if app else ["open", url]
        subprocess.run(cmd, check=False, capture_output=True, timeout=15)

    def _paste(self, text: str) -> None:
        old = subprocess.run(["pbpaste"], capture_output=True, env=UTF8).stdout
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), env=UTF8, check=False)
        time.sleep(0.1)
        self._key(["cmd"], "v")

        def restore():
            time.sleep(1.5)
            subprocess.run(["pbcopy"], input=old, env=UTF8, check=False)

        threading.Thread(target=restore, daemon=True).start()

    def _key(self, mods: list[str], key: str) -> None:
        q = self.Q
        flags = 0
        for m in mods:
            flags |= {
                "cmd": q.kCGEventFlagMaskCommand,
                "shift": q.kCGEventFlagMaskShift,
                "alt": q.kCGEventFlagMaskAlternate,
                "ctrl": q.kCGEventFlagMaskControl,
            }[m]
        for down in (True, False):
            ev = q.CGEventCreateKeyboardEvent(None, KEYCODES[key], down)
            q.CGEventSetFlags(ev, flags)
            q.CGEventPost(q.kCGHIDEventTap, ev)
            time.sleep(0.02)

    def _scroll(self, lines: int) -> None:
        q = self.Q
        q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, int(lines)))

    def _volume(self, level: str) -> None:
        script = {
            "subir": "set volume output volume ((output volume of (get volume settings)) + 15)",
            "bajar": "set volume output volume ((output volume of (get volume settings)) - 15)",
            "silenciar": "set volume output muted true",
            "activar": "set volume output muted false",
        }.get(level, f"set volume output volume {max(0, min(100, int(level) if level.isdigit() else 50))}")
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=10)

    @staticmethod
    def _spanish_voice() -> str:
        """La primera voz de español de México instalada (por ejemplo Paulina); si no, cualquier español."""
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
        return pick_voice(out)

    def speak(self, text: str) -> None:
        print(f"Sofía: {text}", flush=True)
        cmd = ["say", "-v", self.voice, text] if self.voice else ["say", text]
        subprocess.run(cmd, check=False, timeout=120)


def pick_voice(say_list: str) -> str:
    """Elige voz de `say -v ?`: primero es_MX, luego cualquier es_*."""
    voices = []
    for line in say_list.splitlines():
        if "#" not in line:
            continue
        head = line.split("#")[0].split()
        if len(head) >= 2:
            voices.append((" ".join(head[:-1]), head[-1]))
    for prefix in ("es_MX", "es_"):
        for name, locale in voices:
            if locale.startswith(prefix):
                return name
    return ""


class GenericActions(Actions):
    """Windows y Linux: abre páginas con el navegador; el resto aún no está disponible."""

    def _record(self, name: str, **kw) -> dict:
        self.log.append((name, kw))
        return {"ok": True}

    def _open_url(self, url: str, app: str | None) -> None:
        webbrowser.open(url)

    def open_app(self, name: str) -> dict:
        return {"ok": False, "error": "Abrir apps por voz por ahora solo funciona en Mac."}

    def type_text(self, text: str) -> dict:
        return {"ok": False, "error": "Escribir por voz por ahora solo funciona en Mac."}

    def press_keys(self, shortcut: str) -> dict:
        return {"ok": False, "error": "Los atajos por voz por ahora solo funcionan en Mac."}

    def set_volume(self, level: str) -> dict:
        return {"ok": False, "error": "El volumen por voz por ahora solo funciona en Mac."}

    def scroll(self, direction: str, amount: int = 5) -> dict:
        return {"ok": False, "error": "Desplazar por voz por ahora solo funciona en Mac."}


def create_actions(voice: str = "", simulate: bool = False) -> Actions:
    if simulate:
        return Actions()
    return MacActions(voice) if sys.platform == "darwin" else GenericActions()
