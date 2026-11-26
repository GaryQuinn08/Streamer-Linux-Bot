# Audio

En Linux Mint, Ubuntu o Debian:

```bash
sudo apt install mpv espeak-ng
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
Las cuatro usan la misma voz local: espeak-ng en español, o Piper si ya lo
configuraste. No se suben los mensajes a un servicio de voz.

**Probar voz** reproduce una frase de prueba sin conectar cuentas ni activar la
lectura automática. **Detener y vaciar cola** interrumpe la voz del lector y
descarta lo pendiente, pero no impide que se lean los mensajes nuevos. Para
dejar de leer, desmarca la lectura automática y guarda. La opción **Simular
mensaje** sirve para la vista del chat, no dispara la voz automática.

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
No hay conexión con Apple Music o YouTube Music en esta versión.

## Piper (opcional)

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
