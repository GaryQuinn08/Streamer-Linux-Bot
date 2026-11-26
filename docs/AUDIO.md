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
YouTube Music, Apple Music y Amazon Music no tienen vinculación de cuenta ni
cola dentro del bot. Pueden aportar el título a **Ahora suena** si su reproductor
expone metadatos en Linux.

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

Abre **Música → Ahora suena**. Empieza desactivado. Elige **Buscar reproductores**
si quieres mostrar un reproductor externo que esté abierto, o selecciona la
**Cola de audio de Streamer Linux Bot (mpv)**. Marca **Mostrar el tema del
reproductor elegido en mis overlays** y guarda. En **Overlays** copia el enlace
de **Ahora suena · Vinilo nocturno** o **Ahora suena · Espectro neón** a tu fuente de navegador.

En Linux, la búsqueda usa [MPRIS](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html)
en la misma sesión gráfica mediante [busctl](https://www.freedesktop.org/software/systemd/man/latest/busctl.html).
Puede detectar Spotify de escritorio, un navegador con YouTube Music, Apple
Music o Amazon Music, u otros reproductores si publican título y artista mediante
MPRIS. Si no aparecen, inicia una pista y vuelve a buscar; el bot no accede a las
cuentas ni puede forzar que un reproductor publique esos datos. Si el navegador
cambia el nombre de su instancia al reiniciar, vuelve a seleccionarlo.

La función no descarga ni envía audio al directo y no sustituye la autorización
para transmitirlo. Solo muestra título, artista y estado; no publica carátulas,
enlaces ni rutas. La cola del bot muestra el nombre de archivo sin extensión
(o «Audio autorizado» para los enlaces). Si eliges un navegador, podría mostrar
títulos de otros videos o pestañas privadas: mejor usa un reproductor dedicado.
Desmarca la opción y guarda para retirar la información del overlay. Un bot
ejecutado en otro servidor no lee tu sesión gráfica de Linux.
