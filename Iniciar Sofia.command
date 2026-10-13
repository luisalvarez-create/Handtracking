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

# Instala la primera vez, y de nuevo si requirements.txt cambió (por ejemplo, con una versión nueva de Sofía).
REQ_HASH="$(shasum requirements.txt | cut -d' ' -f1)"
if [ ! -x .venv/bin/python ] || [ "$(cat .venv/.requirements 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "Instalando dependencias (tarda unos minutos)…"
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  if .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt; then
    echo "$REQ_HASH" > .venv/.requirements
  else
    read -r -p "La instalación falló. Revisa el internet y presiona Enter para cerrar…"
    exit 1
  fi
fi

# Asistente de voz: la primera vez pide la clave de Gemini (Enter para omitir).
KEY_FILE="$HOME/Library/Application Support/Sofia/gemini_api_key"
if [ -z "$GEMINI_API_KEY" ] && [ ! -s "$KEY_FILE" ] && [ ! -f "$KEY_FILE.omitida" ]; then
  echo
  echo "Para el asistente de voz «Sofía» se necesita una clave de Gemini."
  echo "Créala gratis en https://aistudio.google.com/apikey"
  if .venv/bin/python -m sofia --clave-gemini; then
    :
  else
    mkdir -p "$(dirname "$KEY_FILE")" && touch "$KEY_FILE.omitida"
    echo "Sin clave: Sofía funcionará solo con el cursor. Para agregarla después: borra el archivo"
    echo "  \"$KEY_FILE.omitida\" y vuelve a abrir Sofía."
  fi
fi

.venv/bin/python -m sofia "$@"
