"""Asistente de voz: Gemini entiende la orden y pide acciones permitidas.

Cada orden se manda como audio (y la transcripción local como pista). Gemini
responde con llamadas a funciones; se ejecutan, se le devuelve el resultado y
así hasta que contesta con un texto corto que la asistente dice en voz alta.
"""
from __future__ import annotations

import io
import os
import wave
from datetime import datetime
from pathlib import Path

from .actions import Actions
from .config import config_dir

DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_STEPS = 10
HISTORY_TURNS = 4

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

SYSTEM = """Eres {name}, una asistente de voz en español de México que ayuda a una persona con poca movilidad en las manos a usar su computadora Mac. La persona te activa diciendo «{wake}», mueve el cursor con la cámara (control con la mano o con la cabeza, "hand tracking") y te habla para todo lo demás.

Cómo trabajar:
- Usa las funciones para actuar. Puedes encadenar varias: por ejemplo abrir_app y luego buscar_en_web.
- Para escribir en un documento nuevo de Word, Pages o TextEdit: abre la app, presiona "cmd+n", espera 2 segundos y luego usa escribir_texto.
- Si te piden redactar algo (una carta, un correo, una nota), escríbelo tú completo, bien redactado, con saludo y despedida, y pégalo con escribir_texto. Si falta un dato indispensable (por ejemplo a quién va dirigida la carta), pregunta primero con una sola pregunta corta.
- Si piden abrir, activar o encender el control con la mano, el hand tracking o el cursor con la cámara, usa control_cursor con accion "iniciar" (modo "mano", o "cabeza" si lo piden con la cabeza). Para apagarlo usa "detener"; para dejarlo quieto un momento, "pausar" y "reanudar".
- Si piden que cambies de nombre o de frase de activación, usa cambiar_nombre.
- La persona también hace gestos con toda la mano frente a la cámara: puño, palma (abierta), paz, pulgar_arriba, pulgar_abajo y te_quiero (índice, meñique y pulgar). Si pide que un gesto haga algo, usa asignar_gesto. Para un atajo (cerrar ventana, pestaña nueva, copiar…) usa la acción "atajo" con el atajo en valor; para algo que harías tú (abrir una app, buscar, escribir algo) usa "orden" con la orden en palabras; "escuchar" la despierta sin decir la frase; "ninguna" quita el gesto. Si preguntan qué gestos hay, explícalos con la lista de abajo.
- Gestos configurados ahora: {gestures}.
- Atajos útiles: cerrar ventana "cmd+w", pestaña nueva "cmd+t", salir de una app "cmd+q", deshacer "cmd+z", guardar "cmd+s", buscar en la página "cmd+f", recargar "cmd+r", copiar "cmd+c", pegar "cmd+v", seleccionar todo "cmd+a".
- Nunca envíes mensajes o correos, compres, pagues ni borres archivos sin que la persona lo confirme en ese momento. Pregunta "¿Lo envío?" antes de presionar enviar.
- Si el audio no es una orden para ti (ruido, una conversación con otra persona) o no se entiende, no uses funciones y responde exactamente: (nada)

Eres mujer: habla siempre de ti en femenino ("estoy lista", "quedé atenta", "soy tu asistente", "encantada").

Tu respuesta final se lee en voz alta: una o dos frases cortas, sin listas, sin emojis y sin formato. Di qué hiciste ("Ya abrí Chrome con hoteles en México") o haz la pregunta que necesitas."""


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    {
        "name": "abrir_app",
        "description": "Abre o pasa al frente una aplicación instalada en la Mac (por ejemplo Chrome, Word, Notas, Calculadora).",
        "parameters": _schema({"nombre": {"type": "string", "description": "Nombre de la app"}}, ["nombre"]),
    },
    {
        "name": "buscar_en_web",
        "description": "Busca algo en internet y abre los resultados en el navegador.",
        "parameters": _schema(
            {
                "consulta": {"type": "string", "description": "Qué buscar"},
                "sitio": {"type": "string", "description": "google (predeterminado), youtube, mapas, wikipedia, amazon o mercado libre"},
                "navegador": {"type": "string", "description": "App del navegador si la persona la pidió, por ejemplo Google Chrome"},
            },
            ["consulta"],
        ),
    },
    {
        "name": "abrir_pagina",
        "description": "Abre una página web por su dirección.",
        "parameters": _schema(
            {
                "url": {"type": "string", "description": "Dirección, por ejemplo gmail.com"},
                "navegador": {"type": "string", "description": "App del navegador si la persona la pidió"},
            },
            ["url"],
        ),
    },
    {
        "name": "escribir_texto",
        "description": "Escribe (pega) texto donde está el cursor de escritura de la app que está al frente.",
        "parameters": _schema({"texto": {"type": "string", "description": "Texto completo a escribir"}}, ["texto"]),
    },
    {
        "name": "presionar_teclas",
        "description": "Presiona una tecla o un atajo de teclado en la app que está al frente.",
        "parameters": _schema(
            {"atajo": {"type": "string", "description": "Por ejemplo enter, tab, escape, cmd+t, cmd+shift+t, abajo"}},
            ["atajo"],
        ),
    },
    {
        "name": "desplazar",
        "description": "Desplaza la página o ventana hacia arriba o hacia abajo.",
        "parameters": _schema(
            {
                "direccion": {"type": "string", "enum": ["arriba", "abajo"]},
                "cantidad": {"type": "integer", "description": "Líneas, de 1 a 30 (5 si no se indica)"},
            },
            ["direccion"],
        ),
    },
    {
        "name": "volumen",
        "description": "Cambia el volumen de la computadora.",
        "parameters": _schema({"nivel": {"type": "string", "description": "subir, bajar, silenciar, activar o un número de 0 a 100"}}, ["nivel"]),
    },
    {
        "name": "control_cursor",
        "description": "Inicia, detiene, pausa o reanuda el control del cursor con la cámara (con la mano o con la cabeza).",
        "parameters": _schema(
            {
                "accion": {"type": "string", "enum": ["iniciar", "detener", "pausar", "reanudar"]},
                "modo": {"type": "string", "enum": ["mano", "permanencia", "cabeza"], "description": "mano = pellizco para clic; permanencia = clic al quedarse quieto; cabeza = mover con la cabeza"},
            },
            ["accion"],
        ),
    },
    {
        "name": "cambiar_nombre",
        "description": "Cambia el nombre de la asistente y la frase con la que se activa (por ejemplo nombre Luna, frase hola Luna).",
        "parameters": _schema(
            {
                "nombre": {"type": "string", "description": "Nuevo nombre, por ejemplo Maki"},
                "frase_activacion": {"type": "string", "description": "Frase para activarla, por ejemplo hola Luna. Si no la dicen, se usa el nombre"},
            },
            ["nombre"],
        ),
    },
    {
        "name": "asignar_gesto",
        "description": "Asigna lo que hace un gesto de la mano frente a la cámara (se guarda).",
        "parameters": _schema(
            {
                "gesto": {"type": "string", "enum": ["puño", "palma", "paz", "pulgar_arriba", "pulgar_abajo", "te_quiero"]},
                "accion": {
                    "type": "string",
                    "enum": ["ninguna", "mover_ventana", "desplazar", "arrastrar", "clic", "doble_clic", "clic_derecho", "pausar_cursor", "escuchar", "atajo", "orden"],
                },
                "valor": {"type": "string", "description": "Para atajo: el atajo (cmd+w). Para orden: la orden en palabras (abre Chrome)."},
            },
            ["gesto", "accion"],
        ),
    },
    {
        "name": "esperar",
        "description": "Espera unos segundos (máximo 5), por ejemplo a que cargue una app.",
        "parameters": _schema({"segundos": {"type": "number"}}, ["segundos"]),
    },
]


def run_tool(actions: Actions, name: str, args: dict) -> dict:
    """Ejecuta una función pedida por Gemini. Nunca lanza excepciones: devuelve el error."""
    a = args or {}
    try:
        if name == "abrir_app":
            return actions.open_app(str(a.get("nombre", "")))
        if name == "buscar_en_web":
            return actions.web_search(str(a.get("consulta", "")), str(a.get("sitio") or "google"), str(a.get("navegador") or ""))
        if name == "abrir_pagina":
            return actions.open_url(str(a.get("url", "")), str(a.get("navegador") or ""))
        if name == "escribir_texto":
            return actions.type_text(str(a.get("texto", "")))
        if name == "presionar_teclas":
            return actions.press_keys(str(a.get("atajo", "")))
        if name == "desplazar":
            return actions.scroll(str(a.get("direccion", "abajo")), int(a.get("cantidad") or 5))
        if name == "volumen":
            return actions.set_volume(str(a.get("nivel", "")))
        if name == "control_cursor":
            return actions.cursor(str(a.get("accion", "")), str(a.get("modo") or ""))
        if name == "asignar_gesto":
            return actions.assign_gesture(str(a.get("gesto", "")), str(a.get("accion", "")), str(a.get("valor") or ""))
        if name == "cambiar_nombre":
            return actions.rename(str(a.get("nombre", "")), str(a.get("frase_activacion") or ""))
        if name == "esperar":
            return actions.wait(float(a.get("segundos") or 1))
    except Exception as e:  # una acción fallida no debe tumbar al asistente
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": f"Función desconocida: {name}"}


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def now_text(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{DAYS[now.weekday()]} {now.day} de {MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}"


# --- clave de la API ---------------------------------------------------------

def key_path() -> Path:
    return config_dir() / "gemini_api_key"


def load_api_key() -> str:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    try:
        return key_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_api_key(key: str) -> Path:
    path = key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # solo el usuario puede leerla
    except OSError:
        pass
    return path


# --- asistente ---------------------------------------------------------------

class Assistant:
    def __init__(self, actions: Actions, api_key: str, model: str = DEFAULT_MODEL, client=None, name: str = "Maki", wake: str = "hola Maki"):
        from google.genai import types

        self.types = types
        self.name = name
        self.wake = wake
        self.gestures_text = lambda: "puño = mover la ventana; palma abierta = desplazar"  # lo reemplaza VoiceAssistant
        self.actions = actions
        self.model = model or DEFAULT_MODEL
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client
        self.turns: list[list] = []  # cada turno: lista de Content (usuario, modelo, funciones…)

    def _config(self):
        t = self.types
        apps = ", ".join(self.actions.apps()[:120])
        system = SYSTEM.format(name=self.name, wake=self.wake, gestures=self.gestures_text()) + f"\n\nFecha y hora actual: {now_text()}.\nApps instaladas: {apps}."
        return t.GenerateContentConfig(
            system_instruction=system,
            tools=[t.Tool(function_declarations=[
                t.FunctionDeclaration(name=d["name"], description=d["description"], parameters_json_schema=d["parameters"])
                for d in TOOLS
            ])],
        )

    def handle(self, audio_pcm: bytes | None = None, hint: str = "", text: str = "") -> str:
        """Procesa una orden (audio o texto). Devuelve lo que la asistente debe decir ("" si nada)."""
        t = self.types
        parts = []
        if audio_pcm:
            parts.append(t.Part.from_bytes(data=pcm_to_wav(audio_pcm), mime_type="audio/wav"))
            note = "Orden de voz de la persona (audio adjunto)."
            if hint:
                note += f" Transcripción aproximada hecha en la computadora (puede tener errores): «{hint}»."
            parts.append(t.Part.from_text(text=note))
        else:
            parts.append(t.Part.from_text(text=text))
        turn = [t.Content(role="user", parts=parts)]
        history = [c for old in self.turns[-HISTORY_TURNS:] for c in old]
        config = self._config()

        reply = ""
        for _ in range(MAX_STEPS):
            response = self.client.models.generate_content(model=self.model, contents=history + turn, config=config)
            content = response.candidates[0].content if response.candidates else None
            calls = response.function_calls or []
            if content is not None:
                turn.append(content)
            if not calls:
                reply = (response.text or "").strip()
                break
            results = []
            for call in calls:
                result = run_tool(self.actions, call.name, dict(call.args or {}))
                print(f"  → {call.name}({dict(call.args or {})}) = {result}", flush=True)
                results.append(t.Part(function_response=t.FunctionResponse(id=call.id, name=call.name, response=result)))
            turn.append(t.Content(role="user", parts=results))
        else:
            reply = "Me tardé demasiado con eso. ¿Lo intentamos por partes?"

        if reply.strip("().").lower() == "nada":
            return ""
        # Solo se guardan en el historial los turnos completos (terminan en respuesta del modelo).
        if turn[-1].role == "model":
            self.turns.append(turn)
            self.turns = self.turns[-HISTORY_TURNS:]
        return reply


def friendly_error(exc: Exception) -> str:
    """Mensaje para decir en voz alta cuando Gemini falla."""
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    if code in (401, 403) or "api key" in text or "api_key" in text:
        return "Mi clave de Gemini no es válida. Hay que revisarla."
    if code == 429 or "quota" in text or "resource_exhausted" in text:
        return "Se acabó mi cuota de Gemini por ahora. Intenta en un rato."
    if code and int(code) >= 500:
        return "Gemini no está respondiendo. Intenta en un momento."
    return "No pude conectarme con Gemini. Revisa el internet."
