"""Uso: python -m sofia [--modo pellizco|permanencia|cabeza] [opciones]"""
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
    return p.parse_args(argv)


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

    from .app import App  # importa MediaPipe/OpenCV solo al ejecutar

    return App(cfg).run()


if __name__ == "__main__":
    sys.exit(main())
