#!/bin/bash
# Doble clic en Finder para abrir Sofía. La primera vez instala lo necesario.
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "No se encontró Python 3.10 o más reciente."
  echo "Instálalo desde https://www.python.org/downloads/macos/ y vuelve a abrir este archivo."
  read -r -p "Presiona Enter para cerrar…"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Primera vez: instalando dependencias (tarda unos minutos)…"
  "$PY" -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt
  if [ $? -ne 0 ]; then
    rm -rf .venv
    read -r -p "La instalación falló. Presiona Enter para cerrar…"
    exit 1
  fi
fi

.venv/bin/python -m sofia "$@"
