# Sofía – Asistente de accesibilidad

Sofía permite usar la computadora **sin ratón** a personas con poca movilidad en las manos.
Con la cámara web y [MediaPipe](https://ai.google.dev/edge/mediapipe), el cursor sigue la **mano** o la **cabeza**, y el clic se hace con un pellizco, dejando el cursor quieto o abriendo la boca.

> **Fase 1 (esta versión):** control del cursor con cámara.
> **Fase 2 (siguiente):** asistente de voz "Sofía" con Gemini (por ejemplo, *"Sofía, abre Chrome y busca hoteles en México"* o *"abre Word y ayúdame a redactar una carta"*).

Plataforma principal: **macOS** (Mac con chip Apple o Intel). El código también corre en Windows y Linux, pero todavía no se ha probado ahí.

## Modos de control

| Modo | Mover el cursor | Clic |
| --- | --- | --- |
| **Mano + pellizco** (`pellizco`) | Mover la mano frente a la cámara (sigue los nudillos) | **Pulgar + índice** rápido = clic · dos seguidos = doble clic · sostenido = arrastrar · **pulgar + medio** = clic derecho · **pulgar + anular** sostenido y mover arriba/abajo = desplazar |
| **Mano + permanencia** (`permanencia`) | Igual | Dejar el cursor quieto ~1.2 s (sin pellizcar) |
| **Cabeza** (`cabeza`) | Girar o mover la cabeza (sigue la nariz) | Dejar el cursor quieto, o abrir y cerrar la boca (`--clic-cabeza boca`) |

- En modo cabeza, **mantener la boca bien abierta 1.5 s pausa o reanuda** el control, sin teclado.
- Después de un clic por permanencia hay que mover el cursor para que vuelva a contar, así no se repiten clics si la persona se queda quieta.
- Si la mano o la cara salen de la cámara, el cursor se detiene y se suelta cualquier arrastre.

### Teclas (en la ventana de vista previa, para el terapeuta o cuidador)

| Tecla | Acción |
| --- | --- |
| `p` | Pausar / reanudar |
| `m` | Cambiar de modo |
| `c` | Centrar la cabeza (la posición actual queda como centro de la pantalla) |
| `+` / `-` | Más / menos tiempo de permanencia |
| `q` o `Esc` | Salir |

La ventana muestra la cámara en espejo, los puntos detectados, la **zona activa** (rectángulo naranja: mover la mano dentro de él cubre toda la pantalla), una mini pantalla con la posición del cursor y el círculo de progreso del clic por permanencia.

## Instalación en Mac

1. **Python 3.10 o más reciente.** Descárgalo de [python.org](https://www.python.org/downloads/macos/) (recomendado 3.12). El Python que trae macOS es demasiado antiguo.
2. **Descarga este repositorio:** botón verde *Code → Download ZIP* y descomprímelo, o usa `git clone`.
3. **Doble clic en `Iniciar Sofia.command`.** La primera vez instala las dependencias (unos minutos) y descarga los modelos de MediaPipe.
   - Si macOS dice que el archivo es de un desarrollador no identificado: clic derecho → *Abrir* → *Abrir*.

También se puede ejecutar desde la Terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m sofia                      # usa el último modo elegido
python -m sofia --modo cabeza        # control con la cabeza
python -m sofia --modo permanencia --permanencia 1.5
python -m sofia --help               # todas las opciones
```

### Permisos de macOS (solo la primera vez)

En **Ajustes del Sistema → Privacidad y seguridad**, activa para la app desde la que se ejecuta Sofía (**Terminal**, iTerm o Visual Studio Code):

1. **Cámara**: para ver la mano o la cara.
2. **Accesibilidad**: para mover el cursor y hacer clic. Sin este permiso, Sofía ve la mano pero el cursor no se mueve.

Después de activar los permisos, cierra y vuelve a abrir Sofía.

## Ajustes

La configuración se guarda en `~/Library/Application Support/Sofia/config.json` (los modelos, en la carpeta `models/` de ese mismo lugar). Algunos valores útiles:

| Clave | Para qué sirve |
| --- | --- |
| `region_x`, `region_y` | Tamaño de la zona activa de la mano. Más pequeña = menos movimiento para llegar a las orillas |
| `head_gain_x`, `head_gain_y` | Sensibilidad de la cabeza. Más alto = menos movimiento de cabeza |
| `min_cutoff`, `beta` | Suavizado del cursor. Bajar `min_cutoff` reduce el temblor; subir `beta` lo hace más ágil |
| `dwell_time`, `dwell_radius` | Tiempo (s) y radio (px) del clic por permanencia |
| `pinch_on`, `pinch_off` | Sensibilidad del pellizco |
| `mouth_open` | Qué tan abierta debe estar la boca para el clic |

## Desarrollo

```bash
pip install -r requirements.txt pytest
python -m pytest
```

Las pruebas de `tests/test_logic.py` y `tests/test_mouse.py` no necesitan cámara. `tests/test_tracker.py` usa MediaPipe real con fotos de muestra (necesita internet la primera vez).

```
sofia/
  __main__.py   Línea de comandos (python -m sofia)
  app.py        Bucle principal: cámara → MediaPipe → gestos → ratón
  tracker.py    MediaPipe Hand/Face Landmarker y descarga de modelos
  gestures.py   Lógica de gestos: pellizco, permanencia, cabeza, boca (sin dependencias de hardware)
  filters.py    Filtro One Euro para suavizar el cursor
  mouse.py      Ratón: Quartz en macOS (doble clic correcto), pynput en otros sistemas
  preview.py    Ventana de vista previa
  config.py     Configuración persistente
```
