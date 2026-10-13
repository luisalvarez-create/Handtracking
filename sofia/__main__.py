"""Uso: python -m sofia [--modo pellizco|permanencia|cabeza] [--sin-voz | --solo-voz] [opciones]"""
from __future__ import annotations

import argparse
import sys

from .config import Config

MODE_ALIASES = {"pellizco": "hand_pinch", "permanencia": "hand_dwell", "cabeza": "head"}
HAND_ALIASES = {"cualquiera": "any", "izquierda": "left", "derecha": "right"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="sofia", description="Controla el ratón con la mano o la cabeza usando la cámara.")
    p.add_argument("--modo", choices=MODE_ALIASES, help="pellizco: mano + pellizco · permanencia: mano + clic al quedarse quieto · cabeza: nariz")
    p.add_argument("--mano", choices=HAND_ALIASES, help="mano a seguir")
    p.add_argument("--camara", type=int, help="número de cámara (0 = integrada)")
    p.add_argument("--permanencia", type=float, help="segundos quieto para hacer clic (0.4–3)")
    p.add_argument("--clic-cabeza", choices=["permanencia", "boca"], help="cómo hacer clic en modo cabeza")
    p.add_argument("--sin-vista", action="store_true", help="no mostrar la ventana de la cámara")
    p.add_argument("--sin-sonido", action="store_true", help="desactivar sonidos")
    voz = p.add_argument_group("asistente de voz (Gemini)")
    voz.add_argument("--sin-voz", action="store_true", help="solo control del cursor, sin asistente de voz")
    voz.add_argument("--solo-voz", action="store_true", help="solo asistente de voz, sin cámara")
    voz.add_argument("--clave-gemini", action="store_true", help="guardar la clave de la API de Gemini y salir")
    voz.add_argument("--orden", metavar="TEXTO", help='probar una orden escrita, por ejemplo --orden "abre Chrome y busca hoteles"')
    voz.add_argument("--simular", action="store_true", help="con --orden: solo mostrar las acciones, sin hacerlas")
    voz.add_argument("--modelo-gemini", help="modelo de Gemini (predeterminado: gemini-3.5-flash-lite)")
    return p.parse_args(argv)


def ask_key() -> int:
    from getpass import getpass

    from .assistant import save_api_key

    print("Crea tu clave gratis en https://aistudio.google.com/apikey y pégala aquí (no se mostrará).")
    key = getpass("Clave de Gemini: ").strip()
    if not key:
        print("No se guardó ninguna clave.")
        return 1
    print(f"Clave guardada en {save_api_key(key)}")
    return 0


def start_voice(cfg, simulate: bool = False):
    """Crea el asistente de voz, o devuelve None (con aviso) si no se puede."""
    from .actions import create_actions
    from .voice import VoiceAssistant

    try:
        return VoiceAssistant(cfg, create_actions(cfg.voice_name, simulate=simulate))
    except Exception as e:
        print(f"⚠️  {e}", flush=True)
        return None


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = Config.load()
    if args.modo:
        cfg.mode = MODE_ALIASES[args.modo]
    if args.mano:
        cfg.hand = HAND_ALIASES[args.mano]
    if args.camara is not None:
        cfg.camera_index = args.camara
    if args.permanencia:
        cfg.dwell_time = min(3.0, max(0.4, args.permanencia))
    if args.clic_cabeza:
        cfg.head_click = "mouth" if args.clic_cabeza == "boca" else "dwell"
    if args.sin_vista:
        cfg.show_preview = False
    if args.sin_sonido:
        cfg.sounds = False
    if args.modelo_gemini:
        cfg.gemini_model = args.modelo_gemini
    if args.sin_voz:
        cfg.voice = False

    if args.clave_gemini:
        return ask_key()
    if args.orden:
        voice = start_voice(cfg, simulate=args.simular)
        if voice is None:
            return 1
        voice.command(text=args.orden)
        return 0
    if args.solo_voz:
        return run_voice_only(cfg)

    from .app import App  # importa MediaPipe/OpenCV solo al ejecutar

    voice = start_voice(cfg) if cfg.voice else None
    return App(cfg, voice).run()


def run_voice_only(cfg) -> int:
    import time

    voice = start_voice(cfg)
    if voice is None:
        return 1
    voice.start()
    print("Asistente de voz activo. Ctrl+C para salir.", flush=True)
    try:
        while voice.listener.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    voice.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
