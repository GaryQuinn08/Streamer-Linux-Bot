# Audio

En Linux Mint, Ubuntu o Debian:

```bash
sudo apt install mpv espeak-ng
```

- **Triggers → Regla rápida:** usa Elegir para seleccionar un archivo de
  sonido que se reproduzca al llegar un regalo. Deja en blanco para omitirlo.
- **Inicio → Música local:** agrega archivos de audio y usa **Detener y
  vaciar** si quieres cancelar la reproducción y lo que queda en cola.
  **Acciones → Encolar canción local** pone un archivo elegido por ti en
  la cola. No consume URL, no busca canciones por nombre ni usa Spotify,
  Apple Music, Amazon Music o YouTube Music.
- **Acciones → Leer texto (TTS):** lee texto configurado o, si eliges
  `{text}`, el contenido enviado por los espectadores. Para emitir texto
  de terceros, pon filtros y tiempo de espera para evitar abuso. La salida
  predeterminada usa espeak-ng en español.

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
