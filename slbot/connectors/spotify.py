"""Spotify Connect: cola privada controlada manualmente, nunca por eventos."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit

import aiohttp

from .base import Connector
from .oauth import SignInError, browser_client, sign_in

_TRACK_ID = re.compile(r"[A-Za-z0-9]{22}\Z")
_TRACK_PATH = re.compile(r"/(?:intl-[a-zA-Z]{2}(?:-[a-zA-Z]{2})?/)?track/([a-zA-Z0-9]{22})/?\Z")
_QUEUE_ENDPOINT = "https://api.spotify.com/v1/me/player/queue"


def spotify_track_uri(value: str) -> str:
    """Solo temas de Spotify; no abre enlaces ni manda datos de entrada a otros sitios."""
    raw = value.strip()
    track_id = ""
    if raw.startswith("spotify:track:") and len(raw) < 100:
        track_id = raw.removeprefix("spotify:track:")
    elif len(raw) <= 2048:
        try:
            url = urlsplit(raw)
            if (url.scheme == "https" and url.netloc.lower() == "open.spotify.com"
                    and not url.username):
                match = _TRACK_PATH.fullmatch(url.path)
                if match:
                    track_id = match[1]
        except ValueError:
            pass
    if not _TRACK_ID.fullmatch(track_id):
        raise ValueError("Pega el enlace o URI de una canción de Spotify, no de una playlist.")
    return f"spotify:track:{track_id}"


class SpotifyConnector(Connector):
    name = "spotify"
    kind = "music"

    def __init__(self, rt):
        super().__init__(rt)
        self._task: asyncio.Task | None = None
        self._access_token: str | None = None
        self._queue_lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def connected(self) -> bool:
        return self._access_token is not None

    async def start(self, *, browser=None, setting: str = "") -> None:
        if self.busy or self.connected:
            return
        if not browser or not setting:
            self.status = "Spotify no está habilitado en esta instalación."
            return
        self.status = "Autoriza en el navegador…"
        self._task = asyncio.create_task(self._authorize(browser, setting))

    async def _authorize(self, browser, setting):
        try:
            client = await browser_client("spotify", setting)
            self._access_token = await sign_in(client, browser)
            self.status = "Conectado · escucha privada"
        except SignInError as exc:
            self.status = str(exc)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            self.status = "Spotify no respondió. Intenta conectar otra vez."

    async def stop(self) -> None:
        if self.busy:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self._access_token = None
        self.status = "Desconectado"

    async def enqueue(self, raw: str) -> None:
        """Agrega una pista al reproductor activo de Spotify, no al audio del bot."""
        uri = spotify_track_uri(raw)
        async with self._queue_lock:
            token = self._access_token
            if not token:
                raise ValueError("Conecta Spotify desde Música antes de agregar una canción.")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    async with session.post(
                        _QUEUE_ENDPOINT, params={"uri": uri},
                        headers={"Authorization": f"Bearer {token}"},
                        allow_redirects=False,
                    ) as response:
                        status = response.status
            except (aiohttp.ClientError, TimeoutError):
                raise RuntimeError("Spotify no confirmó la operación. Revisa su cola antes de volver a enviarla.") from None
            if status == 204:
                return
            if status == 401:
                if self._access_token is token:
                    self._access_token = None
                    self.status = "La sesión de Spotify expiró."
                raise ValueError("La sesión de Spotify expiró. Conecta tu cuenta otra vez.")
            if status == 403:
                raise ValueError("Spotify no permitió encolar. Revisa que tengas Premium, un dispositivo activo y acceso de prueba.")
            if status == 404:
                raise ValueError("No hay un reproductor activo. Abre Spotify y reproduce una canción en tu dispositivo.")
            if status == 429:
                raise RuntimeError("Spotify limitó temporalmente las solicitudes. Inténtalo más tarde.")
            raise RuntimeError(f"Spotify no aceptó la canción (HTTP {status}).")
