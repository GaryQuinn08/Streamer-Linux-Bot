"""Inicio de sesión asistido por el navegador; sin almacenar tokens."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

from ..paths import config_dir

TWITCH_PORT = 17845
TWITCH_REDIRECT = f"http://localhost:{TWITCH_PORT}/oauth/twitch"
SPOTIFY_PORT = 17846
SPOTIFY_REDIRECT = f"http://127.0.0.1:{SPOTIFY_PORT}/oauth/spotify"
SPOTIFY_SCOPE = "user-modify-playback-state"
TWITCH_SCOPES = "user:read:chat moderator:read:followers channel:read:subscriptions bits:read channel:read:redemptions"
TWITCH_WRITE_SCOPE = "user:write:chat"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
OpenBrowser = Callable[[str], Awaitable[bool]]


class SignInError(ValueError):
    """Texto apto para mostrar al usuario; nunca incluye credenciales."""


@dataclass(frozen=True)
class Client:
    platform: str
    client_id: str
    secret: str = field(repr=False, default="")


def deployment_setting(platform: str, profile: Path | None = None) -> str:
    """Valores aprovisionados por el proyecto, no pedidos durante el login."""
    names = {"twitch": ("SLB_TWITCH_CLIENT_ID", "twitch_client_id"),
             "youtube": ("SLB_GOOGLE_CLIENT_JSON", "google_client_file"),
             "spotify": ("SLB_SPOTIFY_CLIENT_ID", "spotify_client_id")}
    env, key = names[platform]
    value = os.environ.get(env, "").strip()
    if value:
        try:
            return str(Path(value).expanduser()) if platform == "youtube" else value
        except RuntimeError:
            return ""
    path = (profile or config_dir()) / "oauth-clients.json"
    try:
        with path.open("rb") as f:
            raw = f.read(16385)
        if len(raw) > 16384:
            return ""
        cfg = json.loads(raw)
        value = cfg.get(key, "") if isinstance(cfg, dict) else ""
    except (OSError, ValueError, RecursionError):
        return ""
    if not isinstance(value, str) or not value.strip():
        return ""
    if platform == "youtube":
        try:
            return str(path.parent / Path(value.strip()).expanduser())
        except RuntimeError:
            return ""
    return value.strip()


async def browser_client(platform: str, setting: str) -> Client:
    if platform == "twitch":
        if not re.fullmatch(r"[a-zA-Z0-9]{10,100}", setting):
            raise SignInError("Escribe el Client ID de una aplicación pública de Twitch.")
        return Client(platform, setting)
    if platform == "spotify":
        if not re.fullmatch(r"[a-zA-Z0-9]{10,100}", setting):
            raise SignInError("La instalación no tiene un Client ID válido de Spotify.")
        return Client(platform, setting)
    if platform != "youtube":
        raise SignInError("No hay inicio de sesión para esta plataforma.")
    return await asyncio.to_thread(read_google_client, Path(setting))


def read_google_client(path: Path) -> Client:
    try:
        with path.open("rb") as source:
            data = source.read(65537)
        if len(data) > 65536:
            raise ValueError()
        installed = json.loads(data)["installed"]
        ident, secret = installed["client_id"], installed.get("client_secret", "")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com", ident):
            raise ValueError()
        if not isinstance(secret, str) or len(secret) > 4096:
            raise ValueError()
    except (ValueError, TypeError, AttributeError, OSError, KeyError, RecursionError):
        raise SignInError("Selecciona el JSON de un cliente OAuth de tipo Aplicación de escritorio de Google.") from None
    return Client("youtube", ident, secret)


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")


async def sign_in(client: Client, open_browser: OpenBrowser, *, twitch_write: bool = False) -> str:
    twitch = client.platform == "twitch"
    spotify = client.platform == "spotify"
    provider = "Twitch" if twitch else "Spotify" if spotify else "Google"
    if twitch:
        auth_url, token_url = "https://id.twitch.tv/oauth2/authorize", "https://id.twitch.tv/oauth2/token"
        path, host, port, scope = "/oauth/twitch", "localhost", TWITCH_PORT, TWITCH_SCOPES
        if twitch_write:
            scope += f" {TWITCH_WRITE_SCOPE}"
    elif spotify:
        auth_url, token_url = "https://accounts.spotify.com/authorize", "https://accounts.spotify.com/api/token"
        path, host, port, scope = "/oauth/spotify", "127.0.0.1", SPOTIFY_PORT, SPOTIFY_SCOPE
    elif client.platform == "youtube":
        auth_url, token_url = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token"
        path, host, port, scope = "/oauth/google", "127.0.0.1", 0, GOOGLE_SCOPE
    else:
        raise SignInError("Proveedor de inicio de sesión no compatible.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    callback = asyncio.get_running_loop().create_future()
    expected_host = ""

    async def receive(request):
        if request.host != expected_host:
            raise web.HTTPForbidden()
        sent_state = request.query.getall("state", [])
        if len(sent_state) != 1 or not hmac.compare_digest(sent_state[0].encode(), state.encode()):
            raise web.HTTPBadRequest(text="Esta solicitud no pertenece a un inicio de sesión activo.")
        if callback.done():
            raise web.HTTPGone()
        codes = request.query.getall("code", [])
        if request.query.get("error") or len(codes) != 1 or not 1 <= len(codes[0]) <= 4096:
            callback.set_result(None)
            message = "No se autorizó la conexión. Puedes volver a intentarlo desde el bot."
        else:
            callback.set_result(codes[0])
            message = "Respuesta recibida. Ya puedes cerrar esta pestaña y volver a Streamer Linux Bot."
        return web.Response(text=message, headers={
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
        })

    app = web.Application()
    app.router.add_get(path, receive, allow_head=False)
    runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
    try:
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", port).start()
        except OSError:
            raise SignInError(f"No se pudo abrir el puerto local {port or 'para el inicio de sesión'}. "
                              "Cierra otra sesión del bot si está usando ese puerto.") from None
        expected_host = f"{host}:{runner.addresses[0][1]}"
        redirect = f"http://{expected_host}{path}"
        params = {"client_id": client.client_id, "redirect_uri": redirect,
                  "response_type": "code", "scope": scope, "state": state,
                  "code_challenge": _challenge(verifier), "code_challenge_method": "S256"}
        if client.platform == "youtube":
            params["prompt"] = "select_account"
        if not await open_browser(f"{auth_url}?{urlencode(params)}"):
            raise SignInError("No se pudo abrir el navegador predeterminado.")
        try:
            code = await asyncio.wait_for(callback, 240)
        except TimeoutError:
            raise SignInError("Se agotó el tiempo para autorizar en el navegador. Intenta otra vez.") from None
        if not code:
            raise SignInError(f"No se autorizó la conexión con {provider}.")
    finally:
        if not callback.done():
            callback.cancel()
        await runner.cleanup()

    payload = {"client_id": client.client_id, "code": code, "code_verifier": verifier,
               "redirect_uri": redirect, "grant_type": "authorization_code"}
    if client.platform == "youtube" and client.secret:
        payload["client_secret"] = client.secret
    return await _exchange(token_url, payload, provider)


async def _exchange(token_url: str, payload: dict, provider: str) -> str:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.post(token_url, data=payload, allow_redirects=False) as response:
            if response.status != 200:
                raise SignInError(f"{provider} rechazó la autorización (HTTP {response.status}). "
                                  "Revisa el registro del cliente y vuelve a intentar.")
            result = await response.json()
    token = result.get("access_token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise SignInError(f"{provider} no devolvió una sesión válida.")
    return token


async def twitch_session_identity(session, token: str, client: str) -> tuple[str, tuple[str, ...]]:
    async with session.get("https://id.twitch.tv/oauth2/validate",
                           headers={"Authorization": f"OAuth {token}"}, allow_redirects=False) as reply:
        if reply.status == 401:
            raise SignInError("La sesión de Twitch expiró o se revocó. Inicia sesión otra vez.")
        reply.raise_for_status()
        data = await reply.json()
    owner = data.get("user_id")
    if data.get("client_id") != client or not isinstance(owner, str) or not owner.isdecimal():
        raise SignInError("Twitch no confirmó la cuenta para ese Client ID.")
    scopes = data.get("scopes")
    return owner, tuple(item for item in scopes if isinstance(item, str)) if isinstance(scopes, list) else ()


async def youtube_active_broadcast(session, headers: dict[str, str]):
    async with session.get("https://www.googleapis.com/youtube/v3/liveBroadcasts",
                           params={"part": "snippet", "broadcastStatus": "active",
                                   "broadcastType": "all", "maxResults": "50"},
                           headers=headers, allow_redirects=False) as response:
        response.raise_for_status()
        data = await response.json()
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("YouTube no devolvió una lista de directos válida.")
    rows = [(str(snippet.get("actualStartTime", "")), str(row.get("id") or ""),
             str(snippet.get("liveChatId") or ""), str(snippet.get("title") or ""))
            for row in data.get("items", []) if isinstance(row, dict)
            and isinstance(snippet := row.get("snippet"), dict)]
    return max(rows, key=lambda row: (bool(row[2]), row[0])) if rows else None


async def youtube_live_chat(session, headers: dict[str, str]) -> str:
    stream = await youtube_active_broadcast(session, headers)
    if not stream or not stream[2]:
        raise SignInError("Sesión autorizada, pero no hay un directo activo con chat en esa cuenta de YouTube.")
    return stream[2]
