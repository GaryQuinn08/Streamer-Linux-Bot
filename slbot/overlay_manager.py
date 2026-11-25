"""Gestión de overlays: descubrimiento, validación e importación.

Un overlay es una carpeta con:
    manifest.json   (id, name, description, params...)
    index.html      (punto de entrada que carga OBS como fuente de navegador)
    style.css, script.js, preview.png (opcionales)
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import BUILTIN_OVERLAYS, user_overlays_dir

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
PARAM_TYPES = {"text", "number", "bool", "color", "select"}

MAX_ZIP_FILES = 2000
MAX_ZIP_BYTES = 50 * 1024 * 1024


@dataclass
class OverlayInfo:
    id: str
    name: str
    path: Path
    source: str  # "builtin" | "user"
    description: str = ""
    version: str = ""
    author: str = ""
    params: list[dict[str, Any]] = field(default_factory=list)

    @property
    def preview_path(self) -> Path | None:
        for name in ("preview.png", "preview.svg"):
            candidate = self.path / name
            if candidate.is_file():
                return candidate
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "params": self.params,
        }


def _parse_manifest(folder: Path) -> dict[str, Any]:
    manifest_file = folder / "manifest.json"
    if not manifest_file.is_file():
        raise ValueError("Falta manifest.json")
    if not (folder / "index.html").is_file():
        raise ValueError("Falta index.html")
    try:
        data = json.loads(manifest_file.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("manifest.json debe ser un objeto")

    overlay_id = data.get("id")
    if not isinstance(overlay_id, str) or not ID_RE.match(overlay_id):
        raise ValueError("'id' inválido (usa minúsculas, números, guion y guion bajo)")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("Falta 'name'")

    params = data.get("params", [])
    if not isinstance(params, list):
        raise ValueError("'params' debe ser una lista")
    for p in params:
        if not isinstance(p, dict) or not KEY_RE.match(str(p.get("key", ""))):
            raise ValueError(f"Parámetro con 'key' inválida: {p!r}")
        if p.get("type") not in PARAM_TYPES:
            raise ValueError(f"Parámetro '{p.get('key')}': tipo no soportado ({p.get('type')!r})")
    return data


def _load(folder: Path, source: str) -> OverlayInfo:
    data = _parse_manifest(folder)
    if data["id"] != folder.name:
        raise ValueError(f"El id '{data['id']}' no coincide con la carpeta '{folder.name}'")
    return OverlayInfo(
        id=data["id"],
        name=data["name"],
        path=folder.resolve(),
        source=source,
        description=str(data.get("description", "")),
        version=str(data.get("version", "")),
        author=str(data.get("author", "")),
        params=list(data.get("params", [])),
    )


def list_overlays() -> dict[str, OverlayInfo]:
    """Overlays incluidos y del usuario. Si coinciden en id, gana el integrado."""
    found: dict[str, OverlayInfo] = {}
    for root, source in ((BUILTIN_OVERLAYS, "builtin"), (user_overlays_dir(), "user")):
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            try:
                info = _load(folder, source)
            except ValueError:
                continue  # carpeta que no es un overlay válido
            found.setdefault(info.id, info)
    return found


def find_overlay(overlay_id: str) -> OverlayInfo | None:
    return list_overlays().get(overlay_id)


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_FILES:
        raise ValueError("El zip tiene demasiados archivos")
    total = 0
    for info in infos:
        name = info.filename
        parts = PurePosixPath(name).parts
        if name.startswith("/") or ".." in parts or "\\" in name:
            raise ValueError(f"Ruta no permitida dentro del zip: {name}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"El zip contiene un enlace simbólico: {name}")
        total += info.file_size
        if total > MAX_ZIP_BYTES:
            raise ValueError("El zip descomprimido es demasiado grande")
    zf.extractall(dest)


def _copy_tree_no_links(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True)
    for item in sorted(src.rglob("*")):
        if item.is_symlink():
            continue
        target = dest / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _find_overlay_root(base: Path) -> Path:
    if (base / "manifest.json").is_file():
        return base
    subdirs = [p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]
    if len(subdirs) == 1:
        return subdirs[0]
    raise ValueError("No se encontró un manifest.json en el zip")


def import_overlay(src: Path, overwrite: bool = False) -> OverlayInfo:
    """Importa un overlay desde una carpeta o un .zip a la carpeta del usuario."""
    src = Path(src)
    with tempfile.TemporaryDirectory(prefix="slb-import-") as tmp:
        if src.is_dir():
            root = src
        elif src.is_file() and src.suffix.lower() == ".zip":
            extract_dir = Path(tmp) / "x"
            extract_dir.mkdir()
            with zipfile.ZipFile(src) as zf:
                _safe_extract(zf, extract_dir)
            root = _find_overlay_root(extract_dir)
        else:
            raise ValueError("Elige una carpeta o un archivo .zip")

        data = _parse_manifest(root)
        if (BUILTIN_OVERLAYS / data["id"]).is_dir():
            raise ValueError(f"El id '{data['id']}' está reservado para un overlay integrado")
        dest = user_overlays_dir() / data["id"]
        if dest.exists():
            if not overwrite:
                raise FileExistsError(f"Ya existe un overlay con id '{data['id']}'")
            shutil.rmtree(dest)
        _copy_tree_no_links(root, dest)
    return _load(dest, "user")
