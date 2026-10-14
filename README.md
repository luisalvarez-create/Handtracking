# Sofía – Asistente de accesibilidad

Sofía permite usar la computadora **sin ratón** a personas con poca movilidad en las manos:

- **Cursor con la cámara:** con la cámara web y [MediaPipe](https://ai.google.dev/edge/mediapipe), el cursor sigue la **mano** o la **cabeza**. El clic se hace con un pellizco, dejando el cursor quieto o abriendo la boca.
- **Asistente de voz "Maki" con Gemini:** *"Hola Maki, abre Chrome y busca hoteles en México"*, *"Hola Maki, abre Word y ayúdame a redactar una carta"*, *"Hola Maki, activa el control con la mano"*.

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

### Gestos con toda la mano

Además de los pellizcos, Sofía reconoce **posturas de toda la mano** (con el reconocedor de gestos de MediaPipe). Funcionan en los modos *pellizco* y *permanencia*:

| Gesto | Qué hace (predeterminado) |
| --- | --- |
| ✊ **Puño** | **Mover la ventana** que está bajo el cursor: cierra el puño, mueve la mano y ábrela para soltar. La agarra desde cualquier parte, no solo desde la barra de título |
| 🖐️ **Palma abierta, quieta 0.6 s** y luego subir o bajar la mano | **Desplazar**, como palanca: mientras más lejos del punto donde empezaste, más rápido. Para salir, cierra la mano o muévela hacia un lado |
| ✌️ **Paz** · 👍 **Pulgar arriba** · 👎 **Pulgar abajo** · 🤟 **Te quiero** | Libres: asígnales lo que quieras |

- Un gesto cuenta cuando se sostiene un momento (0.35 s), así un movimiento a medias no hace nada. Al empezar a mover una ventana o a desplazar suena un "pop".
- La palma solo desplaza si se muestra **quieta**: si apuntas con la mano abierta mientras la mueves, no pasa nada.
- **Se programan por voz**, por ejemplo:
  - *"Hola Maki, cuando haga la señal de paz, cierra la ventana"* (atajo `cmd+w`)
  - *"Hola Maki, cuando levante el pulgar, abre Chrome"* (una orden completa para Maki)
  - *"Hola Maki, con el pulgar abajo haz doble clic"*
  - *"Hola Maki, que el gesto de te quiero te despierte"* (sin decir "Hola Maki")
  - *"Hola Maki, quita el gesto de la palma"* · *"¿qué gestos tengo?"*
- Acciones posibles: mover ventana, desplazar, arrastrar, clic, doble clic, clic derecho, pausar el cursor, despertar a Maki, un atajo de teclado o una orden para Maki. Se guardan para la próxima vez.

### Teclas (en la ventana de vista previa, para el terapeuta o cuidador)

| Tecla | Acción |
| --- | --- |
| `p` | Pausar / reanudar |
| `m` | Cambiar de modo |
| `c` | Centrar la cabeza (la posición actual queda como centro de la pantalla) |
| `+` / `-` | Más / menos tiempo de permanencia |
| `q` o `Esc` | Salir |

La ventana muestra la cámara en espejo, los puntos detectados, la **zona activa** (rectángulo naranja: mover la mano dentro de él cubre toda la pantalla), una mini pantalla con la posición del cursor y el círculo de progreso del clic por permanencia.

## Asistente de voz "Maki"

Di **"Hola Maki"** y luego lo que necesitas, en una sola frase. Si solo dices "Hola Maki", te responde "¿Sí?" y escucha lo que sigue.

| Puedes decir | Qué hace |
| --- | --- |
| *"Hola Maki, abre Chrome y busca hoteles en México"* | Abre Chrome con los resultados de la búsqueda |
| *"Hola Maki, abre Word y ayúdame a redactar una carta"* | Abre Word con un documento nuevo, te pregunta para quién es y de qué trata, y escribe la carta |
| *"Hola Maki, pon videos de recetas en YouTube"* | Busca en YouTube (también Google Maps, Wikipedia, Amazon y Mercado Libre) |
| *"Hola Maki, abre gmail.com"* | Abre la página |
| *"Hola Maki, cierra esta ventana"* · *"abre una pestaña nueva"* · *"guarda"* | Usa el atajo de teclado correspondiente |
| *"Hola Maki, baja la página"* · *"sube el volumen"* | Desplaza la página o cambia el volumen |
| *"Hola Maki, activa el control con la mano"* · *"…con la cabeza"* | Abre la cámara y el control del cursor (también si Sofía se abrió solo con voz) |
| *"Hola Maki, pausa el cursor"* · *"reanuda el cursor"* · *"apaga el control con la mano"* | Pausa, reanuda o cierra el control con la cámara; la voz sigue activa |
| *"Hola Maki, a partir de hoy te llamas Luna y te despiertas con hola Luna"* | Cambia su nombre y la frase de activación (se guarda) |

- Cuando Maki hace una pregunta, puedes contestar **sin volver a decir "Hola Maki"** (tienes 8 segundos).
- Recuerda las últimas órdenes, así que entiende cosas como *"ahora ciérralo"*.
- **Antes de enviar, comprar o borrar algo, siempre pide confirmación.**
- Gemini no puede ejecutar cualquier cosa en la computadora. Solo puede pedir estas acciones: abrir apps instaladas, abrir páginas web (http/https), escribir texto, presionar teclas, desplazar, volumen, controlar la cámara del cursor y cambiar el nombre.

### Cambiar el nombre o la frase

Se puede pedir por voz (ver la tabla) o desde la Terminal:

```bash
python -m sofia --nombre Maki --activacion "hola Maki"   # el predeterminado
python -m sofia --nombre Sofía                          # se activa diciendo "Sofía"
```

La frase se reconoce **por cómo suena**: el modelo de voz en español no conoce "Maki" y escucha "hola maqui" o "hola aquí", así que se compara el sonido. Para evitar activaciones con saludos parecidos ("hola mami", "hola Mari"), tanto la frase completa como el nombre deben sonar parecidos. Si se activa sola, sube `wake_similarity` (por ejemplo a 0.85); si no te reconoce, bájalo a 0.75. Funcionan mejor los nombres de dos sílabas o más, distintos de palabras comunes.

### Privacidad y costo

- La frase "Hola Maki" se reconoce **en la computadora, sin internet** (modelo [Vosk](https://alphacephei.com/vosk/) en español, de unos 40 MB, que se descarga la primera vez). **Solo** las frases que empiezan con "Hola Maki" (o la respuesta a una pregunta suya) se envían a Gemini.
- Se usa el modelo `gemini-3.5-flash-lite`, de los más baratos. Cada orden usa unos pocos miles de tokens (las instrucciones de Maki, el audio y cada paso), alrededor de una décima de centavo de dólar. La clave de Google AI Studio tiene un **nivel gratuito**, pero en ese nivel Google puede usar lo que se envía para mejorar sus productos. Si se van a dictar datos personales, conviene activar la facturación (nivel de pago), donde eso no ocurre.

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
python -m sofia --solo-voz           # solo asistente de voz; la cámara se abre cuando se la pidas
python -m sofia --orden "abre Chrome y busca hoteles en México"   # probar una orden escrita
python -m sofia --orden "abre Word y escribe una carta" --simular # ver qué haría, sin hacerlo
python -m sofia --help               # todas las opciones
```

### Permisos de macOS (solo la primera vez)

En **Ajustes del Sistema → Privacidad y seguridad**, activa para la app desde la que se ejecuta Sofía (**Terminal**, iTerm o Visual Studio Code):

1. **Cámara**: para ver la mano o la cara.
2. **Accesibilidad**: para mover el cursor, hacer clic y que el asistente pueda escribir y usar atajos. Sin este permiso, Sofía ve la mano pero el cursor no se mueve.
3. **Micrófono**: para el asistente de voz. macOS lo pregunta la primera vez que Maki escucha.

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
| `gestures` | Qué hace cada gesto, por ejemplo `{"puño": "mover_ventana", "palma": "desplazar", "paz": "atajo:cmd+w", "pulgar_arriba": "orden:abre Chrome"}` (más fácil pedirlo por voz) |
| `gesture_hold` | Segundos sosteniendo un gesto para que cuente |
| `palm_hold`, `palm_scroll_speed`, `palm_deadzone` | Palma: segundos quieta para empezar, velocidad máxima (líneas por segundo) y cuánto mover la mano antes de desplazar |
| `voice` | `false` para apagar el asistente de voz |
| `gemini_model` | Modelo de Gemini (`gemini-3.5-flash-lite`; uno más capaz, por ejemplo `gemini-3.8-flash`, cuesta más) |
| `assistant_name`, `wake_words` | Nombre (`Maki`) y frase de activación (`["hola maki"]`) |
| `wake_similarity`, `wake_confidence` | Qué tan parecido debe sonar (0–1, `0.8`) y la confianza mínima del reconocimiento local (`0.5`) |
| `followup_seconds` | Segundos para contestar una pregunta de Maki sin repetir la frase de activación |
| `voice_name` | Voz de macOS (vacío = una voz femenina en español: Paulina de preferencia, en su mejor calidad). Para ver las instaladas: `say -v "?" \| grep es_`. Más voces: Ajustes del Sistema → Accesibilidad → Contenido leído |
| `mic_device` | Número de micrófono (vacío = el predeterminado) |

## Desarrollo

```bash
pip install -r requirements.txt pytest
python -m pytest
```

Las pruebas de `tests/test_logic.py`, `tests/test_mouse.py`, `tests/test_voice.py` y `tests/test_hand_gestures.py` no necesitan cámara, micrófono ni internet (Gemini y la API de Accesibilidad se simulan). `tests/test_tracker.py` usa MediaPipe real con fotos de muestra, incluidos gestos (necesita internet la primera vez).

```
sofia/
  __main__.py   Línea de comandos (python -m sofia)
  app.py        Bucle principal: cámara → MediaPipe → gestos → ratón
  tracker.py    MediaPipe Gesture Recognizer (mano y gestos) / Face Landmarker y descarga de modelos
  gestures.py   Lógica de gestos: pellizco, permanencia, cabeza, boca y gestos con toda la mano (sin hardware)
  windows.py    Mover la ventana bajo el cursor (API de Accesibilidad de macOS; arrastre como respaldo)
  filters.py    Filtro One Euro para suavizar el cursor
  mouse.py      Ratón: Quartz en macOS (doble clic correcto), pynput en otros sistemas
  preview.py    Ventana de vista previa
  config.py     Configuración persistente
  voice.py      Asistente de voz: une la escucha, Gemini y las acciones
  listener.py   Micrófono y frase de activación por sonido (Vosk, sin internet)
  assistant.py  Gemini: funciones permitidas, historial corto y clave de la API
  actions.py    Acciones en la Mac: abrir apps, páginas, escribir, atajos, volumen, voz (say)
```
