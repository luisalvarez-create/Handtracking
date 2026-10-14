"""Asistente de voz: acciones, palabra clave y bucle con Gemini (cliente simulado, sin internet)."""
import sys
import types as pytypes

import pytest
from google.genai import types

from sofia import actions as act
from sofia import assistant as asst
from sofia.config import Config
from sofia.listener import RATE, WakeLogic, match_wake, phonetic, trim
from sofia.voice import VoiceAssistant

INSTALLED = ["Google Chrome", "Safari", "Microsoft Word", "Microsoft Excel", "Notes", "Calculator", "System Settings", "zoom.us"]


# --- acciones ----------------------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Chrome", "Google Chrome"),
        ("chrome", "Google Chrome"),
        ("Word", "Microsoft Word"),
        ("calculadora", "Calculator"),
        ("Configuración", "System Settings"),
        ("safari", "Safari"),
        ("Sáfari", "Safari"),
        ("notes", "Notes"),
        ("Zoom", "zoom.us"),
        ("Excell", "Microsoft Excel"),
    ],
)
def test_resolve_app(name, expected):
    assert act.resolve_app(name, INSTALLED) == (expected, [])


def test_resolve_app_not_found_and_ambiguous():
    assert act.resolve_app("Photoshop", INSTALLED) == (None, [])
    app, suggestions = act.resolve_app("microsoft", INSTALLED)
    assert app is None and suggestions == ["Microsoft Word", "Microsoft Excel"]


@pytest.mark.parametrize(
    "url, expected",
    [
        ("gmail.com", "https://gmail.com"),
        ("https://www.google.com/maps", "https://www.google.com/maps"),
        ("http://localhost:8000/admin", "http://localhost:8000/admin"),
        ("localhost:8000", "https://localhost:8000"),
        ("javascript:alert(1)", None),
        ("file:///etc/passwd", None),
        ("mailto:alguien@correo.com", None),
        ("", None),
    ],
)
def test_safe_url(url, expected):
    assert act.safe_url(url) == expected


def test_search_url():
    assert act.search_url("hoteles en México") == "https://www.google.com/search?q=hoteles+en+M%C3%A9xico"
    assert act.search_url("recetas", "YouTube").startswith("https://www.youtube.com/results?search_query=recetas")
    assert act.search_url("x", "sitio raro").startswith("https://www.google.com/")


@pytest.mark.parametrize(
    "shortcut, expected",
    [
        ("cmd+n", (["cmd"], "n")),
        ("Cmd + Shift + T", (["cmd", "shift"], "t")),
        ("comando+w", (["cmd"], "w")),
        ("intro", ([], "enter")),
        ("flecha abajo".split()[-1], ([], "down")),
        ("cmd+-", (["cmd"], "-")),
        ("ctrl-a", (["ctrl"], "a")),
    ],
)
def test_parse_shortcut(shortcut, expected):
    assert act.parse_shortcut(shortcut) == expected


@pytest.mark.parametrize("bad", ["", "cmd+ñ", "hiper+a", "cmd+"])
def test_parse_shortcut_rejects(bad):
    with pytest.raises(ValueError):
        act.parse_shortcut(bad)


def test_pick_voice_prefers_female_spanish_voices():
    # Orden real de `say -v ?` en macOS: alfabético, con voces masculinas de México antes que Paulina.
    listing = (
        "Alex                es_US    # no\n"
        "Eddy (Español (México)) es_MX    # Hola, me llamo Eddy.\n"
        "Flo (Español (México))  es_MX    # Hola, me llamo Flo.\n"
        "Grandpa (Español (México)) es_MX # Hola.\n"
        "Jorge               es_ES    # Hola, me llamo Jorge.\n"
        "Juan                es_MX    # Hola, me llamo Juan.\n"
        "Mónica              es_ES    # Hola, me llamo Mónica.\n"
        "Paulina             es_MX    # Hola, me llamo Paulina.\n"
        "Reed (Español (México)) es_MX    # Hola.\n"
    )
    assert act.pick_voice(listing) == "Paulina"
    assert act.pick_voice(listing + "Paulina (Enhanced)  es_MX    # Hola.\n") == "Paulina (Enhanced)"
    assert act.pick_voice("Eddy (Español (México)) es_MX # Hola\nFlo (Español (México)) es_MX # Hola\n") == "Flo (Español (México))"
    assert act.pick_voice("Juan es_MX # Hola\nMónica es_ES # Hola\n") == "Mónica"  # femenina de España antes que masculina
    assert act.pick_voice("Juan es_MX # Hola\n") == "Juan"  # si no hay femenina, al menos en español
    assert act.pick_voice("Alex en_US # Hi\n") == ""


def test_system_prompt_speaks_in_feminine():
    assert "femenino" in asst.SYSTEM and "lista" in asst.SYSTEM


def test_actions_validate_before_acting():
    a = act.Actions()
    assert a.open_url("javascript:alert(1)")["ok"] is False
    assert a.press_keys("cmd+ñ")["ok"] is False
    assert a.set_volume("muy fuerte")["ok"] is False
    assert a.cursor("iniciar")["ok"] is False  # sin supervisor de cámara en esta sesión
    assert a.cursor("volar")["ok"] is False
    assert a.cursor("iniciar", "pies")["ok"] is False
    assert a.rename("")["ok"] is False
    assert a.log == []
    assert a.open_app("Chrome") == {"ok": True, "app": "Google Chrome"}
    assert a.scroll("abajo", 100) == {"ok": True}
    assert a.log == [("abrir_app", {"app": "Google Chrome"}), ("desplazar", {"lineas": -30})]


def test_mac_keyboard_with_fake_quartz(monkeypatch):
    log = []
    q = pytypes.ModuleType("Quartz")
    q.kCGEventFlagMaskCommand, q.kCGEventFlagMaskShift, q.kCGEventFlagMaskAlternate, q.kCGEventFlagMaskControl = 1, 2, 4, 8
    q.kCGHIDEventTap = "tap"
    q.CGEventCreateKeyboardEvent = lambda src, code, down: {"code": code, "down": down}
    q.CGEventSetFlags = lambda ev, flags: ev.__setitem__("flags", flags)
    q.CGEventPost = lambda tap, ev: log.append(ev)
    monkeypatch.setitem(sys.modules, "Quartz", q)
    monkeypatch.setattr(act.MacActions, "_spanish_voice", staticmethod(lambda: "Paulina"))
    m = act.MacActions()
    assert m.press_keys("cmd+shift+t") == {"ok": True}
    assert log == [{"code": 17, "down": True, "flags": 3}, {"code": 17, "down": False, "flags": 3}]


# --- palabra clave -----------------------------------------------------------

def words(text, conf=0.95, start=1.0):
    out = []
    for i, w in enumerate(text.split()):
        out.append({"word": w, "conf": conf, "start": start + i * 0.4, "end": start + i * 0.4 + 0.35})
    return out


def test_wake_command_in_one_phrase():
    logic = WakeLogic(["sofía"])
    d = logic.decide(words("sofía abre crown y busca hoteles"), now=10)
    assert d.kind == "command" and d.hint == "abre crown y busca hoteles"
    assert d.start == 1.0 and d.end == pytest.approx(1.0 + 5 * 0.4 + 0.35)
    assert logic.decide(words("oye sofía pon música"), now=11).kind == "command"


def test_wake_alone_then_followup_without_wake_word():
    logic = WakeLogic(["sofía"], followup_seconds=8)
    assert logic.decide(words("sofía"), now=10).kind == "ack"
    d = logic.decide(words("abre la calculadora"), now=15)
    assert d.kind == "command" and d.hint == "abre la calculadora"
    # La espera de respuesta se usa una sola vez.
    assert logic.decide(words("y también word"), now=16).kind == "ignore"


def test_followup_expires():
    logic = WakeLogic(["sofía"], followup_seconds=8)
    logic.expect_reply(now=10)
    assert logic.decide(words("sí envíalo"), now=19).kind == "ignore"


def test_ignores_conversation_noise_and_low_confidence():
    logic = WakeLogic(["sofía"], min_conf=0.6)
    assert logic.decide(words("hoy fuimos al mercado"), now=1).kind == "ignore"
    assert logic.decide(words("ayer vi a mi amiga sofía"), now=1).kind == "ignore"  # no está al inicio
    assert logic.decide(words("sofía abre chrome", conf=0.4), now=1).kind == "ignore"
    assert logic.decide([{"word": "[unk]", "conf": 0.9}], now=1).kind == "ignore"
    assert logic.decide([], now=1).kind == "ignore"


# --- nombre y frase de activación configurables ("hi Maki") -----------------

def test_phonetic():
    assert phonetic("hi Maki") == phonetic("Jai Maki") == "jaimaki"
    assert phonetic("jaime aquí") == "jaimeaki"  # así escucha "hi Maki" el modelo en español
    assert phonetic("Sofía") == "sofia"
    assert phonetic("quiero chocolate y llaves") == "kierochokolateiabes"


def test_match_wake_by_sound():
    assert match_wake(["jaime", "aquí", "abre", "crown"], "hi maki", 0.8)[0] == 2
    assert match_wake(["maqui", "abre"], "maki", 0.8)[0] == 1
    assert match_wake(["sofía", "abre"], "sofía", 0.8)[0] == 1
    assert match_wake(["hay", "mami", "ya", "llegué"], "hi maki", 0.8) is None
    assert match_wake(["hay", "muchos", "maquillajes"], "hi maki", 0.8) is None
    assert match_wake(["abre", "chrome"], "sofía", 0.8) is None


def test_wake_logic_with_hi_maki():
    logic = WakeLogic(["hi maki"])
    d = logic.decide(words("jaime aquí abre crown y busca hoteles"), now=1)
    assert d.kind == "command" and d.hint == "abre crown y busca hoteles"
    assert logic.decide(words("jaime aquí"), now=2).kind == "ack"
    assert logic.decide(words("abre la calculadora"), now=3).kind == "command"
    assert logic.decide(words("hay mami ya llegué"), now=20).kind == "ignore"
    assert logic.decide(words("sofía abre chrome"), now=21).kind == "ignore"  # ya no se llama Sofía


def test_hola_maki_is_the_default_and_ignores_similar_greetings():
    cfg = Config()
    assert cfg.assistant_name == "Maki" and cfg.wake_words == ["hola maki"]
    logic = WakeLogic(cfg.wake_words)
    # Así escucha el modelo en español "hola Maki":
    assert logic.decide(words("hola maqui abre crown"), now=1).hint == "abre crown"
    assert logic.decide(words("hola aquí abre la calculadora"), now=1).hint == "abre la calculadora"
    for greeting in ["hola mami ya llegué", "hola mary cómo estás", "hola mati que haces", "hola cómo estás", "hola amiga buenos días"]:
        assert logic.decide(words(greeting), now=1).kind == "ignore", greeting


def test_rename_by_voice(monkeypatch):
    saved = []
    monkeypatch.setattr(Config, "save", lambda self, path=None: saved.append((self.assistant_name, list(self.wake_words))))
    actions = act.Actions()
    actions.speak = lambda text: None
    client = FakeClient([call("cambiar_nombre", nombre="Maki", frase_activacion="hi Maki"), text("Listo, ahora me llamo Maki.")])
    v = VoiceAssistant(Config(), actions, api_key="x", client=client)
    v.command(text="a partir de hoy te llamas Maki y te despiertas con hi Maki")
    assert saved == [("Maki", ["hi Maki"])]
    assert v.logic.wake_words == ["hi Maki"] and v.idle_text() == 'Di "hi Maki"'
    assert actions.name == "Maki"
    client.responses.append(text("Hola."))
    v.command(text="hola")
    assert "Eres Maki" in client.requests[-1]["config"].system_instruction
    assert "«hi Maki»" in client.requests[-1]["config"].system_instruction


def test_runner_starts_and_controls_camera_by_voice():
    from sofia.app import Runner

    actions = act.Actions()
    voice = pytypes.SimpleNamespace(actions=actions)
    cfg = Config()
    runner = Runner(cfg, voice, camera=False)

    assert actions.cursor("pausar")["ok"] is False  # cámara apagada
    assert actions.cursor("iniciar", "cabeza")["ok"] is True
    assert runner.want_camera is True and cfg.mode == "head"

    runner.app = pytypes.SimpleNamespace(mode_request=None, pause_request=None, stop_request=False)
    assert actions.cursor("pausar")["ok"] is True and runner.app.pause_request is True
    assert actions.cursor("iniciar", "mano")["ok"] is True
    assert runner.app.mode_request == "hand_pinch" and runner.app.pause_request is False
    assert actions.cursor("detener")["ok"] is True
    assert runner.app.stop_request is True and runner.want_camera is False


def test_trim_to_phrase():
    pcm = bytes(2 * RATE * 10)  # 10 s
    out = trim(pcm, first_sample=RATE * 5, start=6.0, end=8.0)  # el búfer empieza en el segundo 5
    assert len(out) == int((8.0 - 6.0 + 2 * 0.35) * RATE) * 2
    assert trim(pcm, 0, None, None) == pcm


# --- Gemini (cliente simulado) -----------------------------------------------

def call(name, **args):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(id=f"id-{name}", name=name, args=args))]
    ))])


def text(reply):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part.from_text(text=reply)]
    ))])


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        return self.responses.pop(0)


def test_assistant_runs_tool_chain_and_returns_reply():
    client = FakeClient([
        call("abrir_app", nombre="Chrome"),
        call("buscar_en_web", consulta="hoteles en México", navegador="Google Chrome"),
        text("Listo, abrí Chrome con hoteles en México."),
    ])
    actions = act.Actions()
    a = asst.Assistant(actions, api_key="x", client=client)
    reply = a.handle(audio_pcm=b"\0\0" * 1600, hint="abre crown y busca hoteles en méxico")

    assert reply == "Listo, abrí Chrome con hoteles en México."
    assert [name for name, _ in actions.log] == ["abrir_app", "abrir_url"]
    assert actions.log[1][1] == {"url": "https://www.google.com/search?q=hoteles+en+M%C3%A9xico", "app": "Google Chrome"}

    first = client.requests[0]
    assert first["model"] == "gemini-3.5-flash-lite"
    user_parts = first["contents"][0].parts
    assert user_parts[0].inline_data.mime_type == "audio/wav" and user_parts[0].inline_data.data[:4] == b"RIFF"
    assert "abre crown" in user_parts[1].text
    names = [f.name for f in first["config"].tools[0].function_declarations]
    assert {"abrir_app", "buscar_en_web", "escribir_texto", "presionar_teclas"} <= set(names)
    assert "Google Chrome" in first["config"].system_instruction

    # El resultado de cada función regresa a Gemini con su id.
    second = client.requests[1]["contents"]
    fr = second[-1].parts[0].function_response
    assert fr.name == "abrir_app" and fr.id == "id-abrir_app" and fr.response == {"ok": True, "app": "Google Chrome"}

    # El turno completo queda en el historial para la siguiente orden ("ahora ciérralo").
    client.responses.append(text("Hecho."))
    a.handle(text="ahora ciérralo")
    assert len(client.requests[-1]["contents"]) == 7  # 6 del turno anterior + la orden nueva


def test_assistant_reports_tool_errors_to_gemini():
    client = FakeClient([call("abrir_app", nombre="Photoshop"), text("No encontré Photoshop en tu Mac.")])
    a = asst.Assistant(act.Actions(), api_key="x", client=client)
    assert a.handle(text="abre photoshop") == "No encontré Photoshop en tu Mac."
    fr = client.requests[1]["contents"][-1].parts[0].function_response
    assert fr.response["ok"] is False and "Photoshop" in fr.response["error"]


def test_assistant_ignores_noise_without_history():
    client = FakeClient([text("(nada)")])
    a = asst.Assistant(act.Actions(), api_key="x", client=client)
    assert a.handle(text="...") == ""
    assert a.turns == []


def test_unknown_tool_and_bad_args_do_not_crash():
    assert asst.run_tool(act.Actions(), "borrar_todo", {})["ok"] is False
    assert asst.run_tool(act.Actions(), "desplazar", {"direccion": "abajo", "cantidad": "mucho"})["ok"] is False


def test_friendly_errors():
    class E(Exception):
        def __init__(self, code, msg=""):
            super().__init__(msg)
            self.code = code

    assert "clave" in asst.friendly_error(E(400, "API key not valid"))
    assert "cuota" in asst.friendly_error(E(429))
    assert "internet" in asst.friendly_error(ConnectionError())


def test_api_key_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(asst, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert asst.load_api_key() == ""
    path = asst.save_api_key("  abc123 \n")
    assert asst.load_api_key() == "abc123"
    if sys.platform != "win32":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    assert asst.load_api_key() == "env-key"


def test_voice_assistant_speaks_and_detects_question():
    spoken = []
    actions = act.Actions()
    actions.speak = spoken.append
    client = FakeClient([text("¿Para quién es la carta?"), text("Listo.")])
    v = VoiceAssistant(Config(), actions, api_key="x", client=client)
    assert v.command(text="ayúdame a redactar una carta") is True
    assert v.command(text="para mi hermana") is False
    assert spoken == ["¿Para quién es la carta?", "Listo."]


def test_voice_assistant_survives_gemini_errors():
    spoken = []
    actions = act.Actions()
    actions.speak = spoken.append

    class Broken(FakeClient):
        def generate_content(self, **kw):
            raise ConnectionError("sin red")

    v = VoiceAssistant(Config(), actions, api_key="x", client=Broken([]))
    assert v.command(text="abre chrome") is False
    assert spoken == ["No pude conectarme con Gemini. Revisa el internet."]


def test_voice_assistant_requires_key(monkeypatch):
    monkeypatch.setattr("sofia.voice.load_api_key", lambda: "")
    with pytest.raises(RuntimeError, match="aistudio"):
        VoiceAssistant(Config(), act.Actions())
