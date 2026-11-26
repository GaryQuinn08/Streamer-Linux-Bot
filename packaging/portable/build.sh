#!/bin/sh
set -eu
src=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
dest=${1:-"$src/dist"}
mkdir -p "$dest"
python3 - "$src" "$dest" <<'PY'
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

src, dest = map(Path, sys.argv[1:])
prefix = "Streamer-Linux-Bot-0.2.0-beta22-portable/"
path = dest / "Streamer-Linux-Bot-0.2.0-beta22-portable.zip"
with ZipFile(path, "w", ZIP_DEFLATED) as zip:
    for name in ("instalar.sh", "launcher", "requirements.txt", "requirements-server.txt", "requirements-tiktok.txt", "requirements-kick.txt", "INSTALAR.txt"):
        zip.write(src / "packaging/portable" / name, prefix + name)
    zip.write(src / "packaging/debian/streamer-linux-bot.svg", prefix + "streamer-linux-bot.svg")
    for file in sorted((src / "slbot").rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix not in (".pyc", ".pyo"):
            zip.write(file, prefix + file.relative_to(src).as_posix())
print(path)
PY
