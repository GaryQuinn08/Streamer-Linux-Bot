# Audio

En Linux Mint, Ubuntu o Debian:

```bash
sudo apt install mpv
```

- **Regla de regalos:** usa Elegir para seleccionar un sonido que se
  reproduzca al llegar un regalo. Deja en blanco si no quieres sonido.
- **Música → Audio autorizado para el directo:** puedes agregar un
  archivo local o una URL HTTPS pública y directa de tu proveedor.
  Solo para audio que tu licencia permita emitir; una página de
  reproducción o enlace a playlist no es un archivo de audio. Usa
  **Detener y vaciar esta cola** para cancelar la reproducción y lo
  pendiente. El operador agrega los enlaces; no se leen desde el chat.
- **Acciones → Leer texto (TTS):** lee texto configurado o, si eliges
  `{text}`, contenido del público. Pon filtros y tiempo de espera
  para evitar abuso. La voz predeterminada usa espeak-ng en español.

## Leer el chat de varias plataformas con una voz

Desde la **beta 15**, abre **Chat → Leer chat en voz alta (TTS)**. La lectura
automática viene apagada. Marca **Leer automáticamente los mensajes nuevos**,
elige cualquiera de Twitch, TikTok, YouTube o Kick y pulsa **Guardar lectura**.
Los mensajes de las plataformas desmarcadas siguen apareciendo en tu chat.
Las cuatro usan la misma voz y las acciones de TTS también. Con voz natural
instalada usan Piper; sin ella, eSpeak NG. No se suben los mensajes a un servicio de voz.

**Probar voz** reproduce una frase de prueba sin conectar cuentas ni activar la
lectura automática. **Detener y vaciar cola** interrumpe la voz del lector y
descarta lo pendiente, pero no impide que se lean los mensajes nuevos. Para
dejar de leer, desmarca la lectura automática y guarda. La opción **Simular
mensaje** sirve para la vista del chat, no dispara la voz automática.

Si instalaste desde el repositorio o el ZIP, ejecuta `bash instalar.sh --voz`
(en la carpeta del instalador) para instalar las dependencias de voz que falten.
Puedes conservar tus opciones habituales, por ejemplo `--tiktok --voz`.
También puedes instalarlas directamente en Mint, Ubuntu o Debian con
`sudo apt install espeak-ng pulseaudio-utils` sin reinstalar el bot.
El paquete .deb para Debian 13 ya declara la voz y un reproductor como dependencias;
instálalo mediante APT para que los resuelva. Si la app informa que la voz se
generó pero no se pudo enviar a una salida, revisa **Sonido** del sistema y
asegúrate de que tu dispositivo pueda reproducir otro audio.

Para emitir la voz, comprueba qué entrada de audio está capturando OBS o LIVE
Studio. Desmarcar una plataforma en el overlay visual no silencia su lectura.
Si compartes la misma mezcla de audio con Twitch durante un multistream,
selecciona solo Twitch para la voz que sale por esa mezcla o deja la voz fuera
de la salida pública.
[Directrices de Twitch](https://help.twitch.tv/s/article/simulcasting-guidelines?language=es_MX).

## Spotify (opcional, solo escucha privada)

**Música → Spotify** agrega canciones por enlace a la cola del reproductor
Spotify activo. Requiere Premium y un cliente [habilitado por el
proyecto](OAUTH.md). Conecta desde el navegador, abre Spotify en el
dispositivo y empieza a reproducir algo para activarlo. Pega un link de
una canción (no una lista) en el bot. La música **no** sale por el bot,
no participa en acciones, regalos o chat y no debe capturarse ni
retransmitirse en OBS o LIVE Studio. Consulta las
[condiciones de reproducción de Spotify](https://developer.spotify.com/documentation/web-api/reference/add-to-queue).
Otros servicios no tienen inicio de sesión ni cola dentro del bot.
Para mostrar su canción actual en el directo, usa **Ahora suena**.

## Voz natural en español de México

Para la instalación portable desde Git o ZIP, ejecuta:

```bash
bash instalar.sh --tiktok --voz-natural
```

Quita `--tiktok` si no usas el conector directo. La primera instalación de voz
descarga cerca de 120 MB extra (Piper y su modelo), no pide cuenta ni claves y
reutiliza el modelo en la siguiente actualización. Incluye una prueba de síntesis
antes de activar la instalación. Después, no necesita Internet para hablar.
En **Chat** verás «Claude (español de México) · voz natural» y puedes escucharla
con **Probar voz**. Si falla la síntesis, te avisa en lugar de cambiar a la voz
básica sin avisar. Si ya elegiste un modelo con `SLB_PIPER_MODEL`, ese modelo
conserva prioridad. Los ajustes de qué plataformas se leen no cambian.

La voz no es Alexa. El [modelo Claude y sus créditos](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_MX/claude/high/MODEL_CARD)
identifican el conjunto de datos de HirCoir (Apache 2.0). Piper es una
herramienta de terceros que el instalador obtiene de PyPI; no incluimos sus
binarios ni el modelo en el ZIP o en el .deb.

## Usar otro modelo Piper o configurar Piper en la versión .deb

Instala [Piper](https://github.com/OHF-Voice/piper1-gpl) en un entorno separado y
descarga una voz de tu elección. Consulta la licencia de esa voz antes de
usarla o redistribuirla. Ejemplo para instalar el motor:

```bash
python3 -m venv ~/.local/share/slb-piper/venv
~/.local/share/slb-piper/venv/bin/python -m pip install piper-tts
export SLB_PIPER="$HOME/.local/share/slb-piper/venv/bin/piper"
export SLB_PIPER_MODEL="$HOME/voces/mi-voz.onnx"
~/.local/bin/streamer-linux-bot
```

Deja `mi-voz.onnx.json` junto al `.onnx`. Si Piper no está configurado o
falla al sintetizar, el bot intenta espeak-ng. Asegúrate de capturar la
salida de tu equipo en el mezclador de OBS/LIVE Studio si quieres que el
audio también se escuche en el directo.

## Mostrar qué está sonando en OBS o LIVE Studio

La beta 22 usa música de **Spotify, YouTube Music, Amazon Music, Apple Music,
Deezer y TIDAL**. **Ahora suena** ya no ofrece la cola local ni detecta otros
reproductores genéricos. Esto no elimina la cola de **Audio autorizado**,
que sigue siendo independiente.

**Spotify de escritorio en Linux:** en **Música → Ahora suena**, selecciona
**Spotify de escritorio (Linux)**, activa la casilla y guarda. Reproduce una
canción en la app de Spotify. El bot lee la pista por
[MPRIS](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html),
sin autorización OAuth adicional. El dispositivo donde se reproduce el audio
debe ser esa app, no otro dispositivo Spotify Connect.

**Servicios web (Brave, Chromium o Chrome de escritorio):**

1. En **Música → Ahora suena**, elige el servicio, activa la casilla y guarda.
2. En el navegador, abre su página **Extensiones** (en Brave,
   `brave://extensions`). Activa el **Modo desarrollador** y usa
   **Cargar descomprimida**/**Cargar sin empaquetar**. Selecciona la carpeta
   que abre **Abrir carpeta de extensión** en el bot (o
   `slbot/music_extension` si instalaste desde un clon y prefieres su ruta).
3. Pulsa **Abrir servicio** y pon una canción. Pulsa **Copiar código** en el
   bot y, en la pestaña de música, abre la extensión **Ahora suena**. Pega el
   código y pulsa **Compartir esta pestaña**. No compartas el código con nadie.
   Si reinicias el bot, cambia su puerto o recargas esa pestaña, vuelve a enlazar.
4. En **Overlays**, elige **Vinilo nocturno** o **Espectro neón** y añade
   **la misma URL de fuente** a OBS o LIVE Studio. No necesitas cambiarla al
   cambiar de servicio.

Si la extensión se enlaza pero no aparece un título, reproduce una pista y
verifica que la pestaña publique título y artista mediante
[Media Session](https://developer.mozilla.org/en-US/docs/Web/API/MediaSession/metadata).
No se adivinan títulos con otras pestañas ni se usan archivos o cuentas
como alternativa. En esta entrega la extensión se prueba con metadatos
simulados; el resultado en un servicio real depende de lo que envíe esa
pestaña. Firefox no está soportado por esta extensión. Usa **Detener**
en la extensión o desactiva la casilla en el bot para dejar de compartir.

Solo se envía título, artista y estado al overlay local. No extrae audio,
descarga canciones, accede a cuentas ni da autorización para retransmitir.
