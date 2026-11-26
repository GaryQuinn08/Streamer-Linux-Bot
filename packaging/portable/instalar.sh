#!/bin/sh
# Instala solo para la cuenta actual. No ejecuta sudo ni instala paquetes APT.
set -eu
umask 077
if [ "$(id -u)" -eq 0 ]; then
    echo "Ejecuta este instalador sin sudo." >&2
    exit 1
fi
headless=0
tiktok=0
kick=0
for arg in "$@"; do
    case "$arg" in
        --servidor) headless=1 ;;
        --kick) kick=1 ;;
        --tiktok) tiktok=1 ;;
        *) echo "Uso: bash instalar.sh [--servidor] [--tiktok] [--kick]" >&2; exit 2 ;;
    esac
done
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
code_dir="$source_dir"
icon="$source_dir/streamer-linux-bot.svg"
if [ -f "$source_dir/../../slbot/__main__.py" ]; then
    code_dir=$(CDPATH='' cd -- "$source_dir/../.." && pwd)
    icon="$code_dir/packaging/debian/streamer-linux-bot.svg"
fi
if [ ! -f "$code_dir/slbot/__main__.py" ]; then
    echo "Extrae el ZIP completo antes de ejecutar instalar.sh." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Se requiere Python 3.11 o superior. Consulta INSTALAR.txt." >&2
    exit 1
fi
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
root="$data_home/streamer-linux-bot-portable"
bindir="${XDG_BIN_HOME:-"$HOME/.local/bin"}"
desktop="$data_home/applications"
mkdir -p "$root" "$bindir"
if [ "$headless" -eq 0 ]; then mkdir -p "$desktop"; fi
publish_command() {
    name=$1
    TARGET="$target/streamer-linux-bot" COMMAND="$bindir/$name" python3 - <<'PUBLISH'
import os
import shlex
import tempfile
from pathlib import Path
path = Path(os.environ["COMMAND"])
marker = "# Administrado por Streamer Linux Bot"
if path.is_symlink() or (path.exists() and marker not in path.read_text(encoding="utf-8", errors="replace")[:256]):
    print(f"No sustituí {path}: ya existe y no lo instaló este script.")
else:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        file.write(f'#!/bin/sh\n{marker}\nexec {shlex.quote(os.environ["TARGET"])} "$@"\n')
        temp = Path(file.name)
    try:
        temp.chmod(0o755)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Comando instalado: {path}")
PUBLISH
}
target=$(mktemp -d "$root/install.XXXXXXXX")
completed=0
trap '[ "$completed" -eq 1 ] || rm -rf -- "$target"' EXIT
trap 'exit 1' HUP INT TERM
cp -R "$code_dir/slbot" "$target/"
install -m 0755 "$source_dir/launcher" "$target/streamer-linux-bot"
install -m 0644 "$icon" "$target/icon.svg"

if ! python3 -m venv "$target/venv"; then
    echo "No pude crear un entorno de Python. En Debian, Ubuntu y Mint instala python3-venv." >&2
    exit 1
fi
requirements="$source_dir/requirements.txt"
if [ "$headless" -eq 1 ]; then requirements="$source_dir/requirements-server.txt"; fi
echo "Descargando dependencias desde PyPI (necesita Internet)…"
"$target/venv/bin/python" -m pip --isolated --disable-pip-version-check install \
    --index-url https://pypi.org/simple --only-binary=:all: -r "$requirements"
if [ "$tiktok" -eq 1 ]; then
    "$target/venv/bin/python" -m pip --isolated --disable-pip-version-check install \
        --index-url https://pypi.org/simple -r "$source_dir/requirements-tiktok.txt"
    "$target/venv/bin/python" - <<'TIKTOK'
import asyncio
from TikTokLive import TikTokLiveClient

async def check():
    client = TikTokLiveClient(unique_id="local_install_check")
    await client.close()  # No se conecta a ningún directo.

asyncio.run(check())
TIKTOK
fi
if [ "$kick" -eq 1 ]; then
    "$target/venv/bin/python" -m pip --isolated --disable-pip-version-check install \
        --index-url https://pypi.org/simple --only-binary=:all: -r "$source_dir/requirements-kick.txt"
fi
if [ "$headless" -eq 1 ]; then
    "$target/streamer-linux-bot" --help >/dev/null
    completed=1
    publish_command streamer-linux-bot-server
    printf '\nPara iniciar sin interfaz:\n  "%s" servidor\n' "$target/streamer-linux-bot"
    exit 0
fi
if ! QT_QPA_PLATFORM=offscreen "$target/venv/bin/python" -c \
    'from PySide6.QtWidgets import QApplication; import aiohttp; app = QApplication([])'; then
    echo "Qt no pudo arrancar. En Debian, Ubuntu y Mint revisa libegl1, libgl1 y libxcb-cursor0." >&2
    exit 1
fi

# El acceso directo apunta a la instalación nueva solo cuando está lista.
DESKTOP_DIR="$desktop" INSTALL_TARGET="$target" python3 - <<'PY'
import os
import tempfile
from pathlib import Path

folder = Path(os.environ["DESKTOP_DIR"])
target = Path(os.environ["INSTALL_TARGET"])
launcher = str(target / "streamer-linux-bot")
if any(ord(c) < 32 for c in launcher):
    raise SystemExit("La ruta de instalación tiene caracteres no admitidos.")
exec_value = "".join(
    "%%" if c == "%" else "\\\\" + c if c in '"`$' else "\\\\\\\\" if c == chr(92) else c
    for c in launcher
)
icon = str(target / "icon.svg").replace(chr(92), chr(92) * 2)
with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as handle:
    handle.write(
        "[Desktop Entry]\nType=Application\nName=Streamer Linux Bot (beta)\n"
        f'Exec="{exec_value}"\nIcon={icon}\nTerminal=false\nCategories=AudioVideo;Video;\n'
    )
Path(handle.name).replace(folder / "streamer-linux-bot-portable.desktop")
PY
completed=1
publish_command streamer-linux-bot
printf '\nYa puedes abrir «Streamer Linux Bot (beta)» en el menú.\n'
printf 'Si no aparece todavía, ejecútalo con:\n  "%s"\n' "$target/streamer-linux-bot"
