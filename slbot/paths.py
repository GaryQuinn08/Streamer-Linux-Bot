"""Rutas de la aplicación (configuración, datos del usuario y recursos incluidos).

Se pueden sobrescribir con las variables SLB_CONFIG_DIR y SLB_DATA_DIR
(útil para pruebas).
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "streamer-linux-bot"

PACKAGE_DIR = Path(__file__).resolve().parent
BUILTIN_OVERLAYS = PACKAGE_DIR / "overlays" / "builtin"
SDK_DIR = PACKAGE_DIR / "overlays" / "sdk"


def _xdg(var: str, fallback: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else fallback


def config_dir() -> Path:
    override = os.environ.get("SLB_CONFIG_DIR")
    path = Path(override) if override else _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    override = os.environ.get("SLB_DATA_DIR")
    path = Path(override) if override else _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_overlays_dir() -> Path:
    path = data_dir() / "overlays"
    path.mkdir(parents=True, exist_ok=True)
    return path
