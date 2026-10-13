# Sofía – Asistente de accesibilidad

Sofía permite usar la computadora **sin ratón** a personas con poca movilidad en las manos:

- **Cursor con la cámara:** con la cámara web y [MediaPipe](https://ai.google.dev/edge/mediapipe), el cursor sigue la **mano** o la **cabeza**. El clic se hace con un pellizco, dejando el cursor quieto o abriendo la boca.
- **Asistente de voz con Gemini:** *"Sofía, abre Chrome y busca hoteles en México"*, *"Sofía, abre Word y ayúdame a redactar una carta"*.

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

## Asistente de voz "Sofía"

Di **"Sofía"** y luego lo que necesitas, en una sola frase. Si solo dices "Sofía", te responde "¿Sí?" y escucha lo que sigue.

| Puedes decir | Qué hace |
| --- | --- |
| *"Sofía, abre Chrome y busca hoteles en México"* | Abre Chrome con los resultados de la búsqueda |
| *"Sofía, abre Word y ayúdame a redactar una carta"* | Abre Word con un documento nuevo, te pregunta para quién es y de qué trata, y escribe la carta |
| *"Sofía, pon videos de recetas en YouTube"* | Busca en YouTube (también Google Maps, Wikipedia, Amazon y Mercado Libre) |
| *"Sofía, abre gmail.com"* | Abre la página |
| *"Sofía, cierra esta ventana"* · *"abre una pestaña nueva"* · *"guarda"* | Usa el atajo de teclado correspondiente |
| *"Sofía, baja la página"* · *"sube el volumen"* | Desplaza la página o cambia el volumen |
| *"Sofía, pausa el cursor"* · *"reanuda el cursor"* | Detiene o reactiva el control con la cámara |

- Cuando Sofía hace una pregunta, puedes contestar **sin volver a decir "Sofía"** (tienes 8 segundos).
- Recuerda las últimas órdenes, así que entiende cosas como *"ahora ciérralo"*.
- **Antes de enviar, comprar o borrar algo, siempre pide confirmación.**
- Gemini no puede ejecutar cualquier cosa en la computadora. Solo puede pedir estas acciones: abrir apps instaladas, abrir páginas web (http/https), escribir texto, presionar teclas, desplazar, volumen y pausar el cursor.

### Privacidad y costo

- La palabra "Sofía" se reconoce **en la computadora, sin internet** (modelo [Vosk](https://alphacephei.com/vosk/) en español, de unos 40 MB, que se descarga la primera vez). **Solo** las frases que empiezan con "Sofía" (o la respuesta a una pregunta suya) se envían a Gemini.
- Se usa el modelo `gemini-3.5-flash-lite`, de los más baratos. Cada orden usa unos pocos miles de tokens (las instrucciones de Sofía, el audio y cada paso), alrededor de una décima de centavo de dólar. La clave de Google AI Studio tiene un **nivel gratuito**, pero en ese nivel Google puede usar lo que se envía para mejorar sus productos. Si se van a dictar datos personales, conviene activar la facturación (nivel de pago), donde eso no ocurre.

### La clave de Gemini

1. Entra a [aistudio.google.com/apikey](https://aistudio.google.com/apikey) con una cuenta de Google y crea una clave.
2. Al abrir `Iniciar Sofia.command`, la primera vez te la pide: pégala y presiona Enter (no se muestra en pantalla). Se guarda solo para tu usuario en `~/Library/Application Support/Sofia/gemini_api_key`.
   - Para cambiarla después: `python -m sofia --clave-gemini`.
   - También se puede usar la variable de entorno `GEMINI_API_KEY`.

## Instalación en Mac

1. **Python 3.10 o más reciente.** Descárgalo de [python.org](https://www.python.org/downloads/macos/) (recomendado 3.12). El Python que trae macOS es demasiado antiguo.
2. **Descarga este repositorio:** botón verde *Code → Download ZIP* y descomprímelo, o usa `git clone`.
3. **Doble clic en `Iniciar Sofia.command`.** La primera vez instala las dependencias (unos minutos), pide la clave de Gemini (Enter para omitirla) y descarga los modelos de MediaPipe y de voz. Si actualizas Sofía, vuelve a instalar solo lo que haga falta.
   - Si macOS dice que el archivo es de un desarrollador no identificado: clic derecho → *Abrir* → *Abrir*.

También se puede ejecutar desde la Terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m sofia                      # usa el último modo elegido
python -m sofia --modo cabeza        # control con la cabeza
python -m sofia --modo permanencia --permanencia 1.5
python -m sofia --sin-voz            # solo cursor
python -m sofia --solo-voz           # solo asistente de voz, sin cámara
python -m sofia --orden "abre Chrome y busca hoteles en México"   # probar una orden escrita
python -m sofia --orden "abre Word y escribe una carta" --simular # ver qué haría, sin hacerlo
python -m sofia --help               # todas las opciones
```

### Permisos de macOS (solo la primera vez)

En **Ajustes del Sistema → Privacidad y seguridad**, activa para la app desde la que se ejecuta Sofía (**Terminal**, iTerm o Visual Studio Code):

1. **Cámara**: para ver la mano o la cara.
2. **Accesibilidad**: para mover el cursor, hacer clic y que el asistente pueda escribir y usar atajos. Sin este permiso, Sofía ve la mano pero el cursor no se mueve.
3. **Micrófono**: para el asistente de voz. macOS lo pregunta la primera vez que Sofía escucha.

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
| `voice` | `false` para apagar el asistente de voz |
| `gemini_model` | Modelo de Gemini (`gemini-3.5-flash-lite`; uno más capaz, por ejemplo `gemini-3.8-flash`, cuesta más) |
| `wake_words`, `wake_confidence` | Palabra clave (`["sofía"]`) y qué tan seguro debe estar el reconocimiento (0–1). Súbelo si se activa sola; bájalo si no te reconoce |
| `followup_seconds` | Segundos para contestar una pregunta de Sofía sin decir "Sofía" |
| `voice_name` | Voz de macOS (vacío = la primera de español de México, por ejemplo Paulina). Más voces: Ajustes del Sistema → Accesibilidad → Contenido leído |
| `mic_device` | Número de micrófono (vacío = el predeterminado) |

## Desarrollo

```bash
pip install -r requirements.txt pytest
python -m pytest
```

Las pruebas de `tests/test_logic.py`, `tests/test_mouse.py` y `tests/test_voice.py` no necesitan cámara, micrófono ni internet (Gemini se simula). `tests/test_tracker.py` usa MediaPipe real con fotos de muestra (necesita internet la primera vez).

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
  voice.py      Asistente de voz: une la escucha, Gemini y las acciones
  listener.py   Micrófono y palabra clave "Sofía" (Vosk, sin internet)
  assistant.py  Gemini: funciones permitidas, historial corto y clave de la API
  actions.py    Acciones en la Mac: abrir apps, páginas, escribir, atajos, volumen, voz (say)
```
