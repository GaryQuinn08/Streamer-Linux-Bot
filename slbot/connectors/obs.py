"""OBS Studio via WebSocket v5. Requests on one client are serialized."""
from __future__ import annotations

import asyncio
import base64
import hashlib
from typing import Any
from uuid import uuid4

import aiohttp
from yarl import URL

from .base import Connector


class _DebianObsClient:
    """Small WebSocket v5 client over aiohttp for the packaged app."""

    def __init__(self, host: str, port: int, password: str) -> None:
        self._url = URL.build(scheme="ws", host=host, port=port)
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._socket: aiohttp.ClientWebSocketResponse | None = None

    async def connect(self) -> str:
        self._session = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(6):
                self._socket = await self._session.ws_connect(self._url, heartbeat=20,
                                                              max_msg_size=1024 * 1024)
                hello = await self._socket.receive_json()
                if hello.get("op") != 0 or hello["d"].get("rpcVersion", 0) < 1:
                    raise ConnectionError("El servidor no anunció el protocolo OBS WebSocket v5")
                identity: dict[str, str | int] = {"rpcVersion": 1, "eventSubscriptions": 0}
                required = hello["d"].get("authentication")
                if required is not None:
                    salt, challenge = required["salt"], required["challenge"]
                    secret = base64.b64encode(hashlib.sha256((self._password + salt).encode()).digest())
                    identity["authentication"] = base64.b64encode(
                        hashlib.sha256(secret + challenge.encode()).digest()
                    ).decode("ascii")
                self._password = ""
                await self._socket.send_json({"op": 1, "d": identity})
                if (await self._socket.receive_json()).get("op") != 2:
                    raise ConnectionError("OBS no aceptó la identificación")
                return str((await self.call("GetVersion"))["obsVersion"])
        except BaseException:
            await self.disconnect()
            raise

    async def call(self, name: str, **data) -> dict:
        socket = self._socket
        if socket is None or socket.closed:
            raise ConnectionError("OBS no está conectado")
        token = uuid4().hex
        request = {"requestType": name, "requestId": token}
        if data:
            request["requestData"] = data
        async with asyncio.timeout(4):
            await socket.send_json({"op": 6, "d": request})
            while True:
                message = await socket.receive_json()
                if message.get("op") != 7 or message["d"].get("requestId") != token:
                    continue
                response = message["d"]
                status = response["requestStatus"]
                if not status["result"]:
                    raise RuntimeError(f"OBS rechazó {name} (código {status.get('code', '?')})")
                return response.get("responseData", {})

    async def disconnect(self) -> None:
        self._password = ""
        socket, session = self._socket, self._session
        self._socket = self._session = None
        try:
            if socket is not None and not socket.closed:
                async with asyncio.timeout(2):
                    await socket.close()
        except (TimeoutError, aiohttp.ClientError):
            pass
        finally:
            if session is not None:
                await session.close()


class ObsConnector(Connector):
    name = "obs"
    kind = "broadcaster"

    def __init__(self, rt) -> None:
        super().__init__(rt)
        self._client: Any = None
        self._lock = asyncio.Lock()

    async def start(self, host: str | None = None, port: int | None = None,
                    password: str | None = None) -> None:
        cfg = self.rt.config.settings["obs"]
        host = str(cfg["host"]) if host is None else host
        port = int(cfg["port"]) if port is None else port
        manual = password is not None
        password = str(cfg.get("password", "")) if password is None else password

        def connect(ReqClient):
            client = ReqClient(host=host, port=port, password=password, timeout=4)
            try:
                version = client.get_version().obs_version
            except Exception:
                client.disconnect()
                raise
            return client, version

        async with self._lock:
            await self._disconnect()
            self.status = "conectando…"
            try:
                try:
                    from obsws_python import ReqClient
                except ModuleNotFoundError as exc:
                    if exc.name != "obsws_python":
                        raise
                    client = _DebianObsClient(host, port, password)
                    version = await client.connect()
                    self._client = client
                else:
                    connecting = asyncio.create_task(asyncio.to_thread(connect, ReqClient))
                    try:
                        self._client, version = await asyncio.shield(connecting)
                    except asyncio.CancelledError:
                        try:
                            client, _ = await connecting
                        except Exception:
                            pass
                        else:
                            await asyncio.to_thread(client.disconnect)
                        raise
            except Exception as exc:
                self.status = "error"
                self.rt.log(f"OBS: no se pudo conectar ({type(exc).__name__}). "
                            "Revisa el servidor WebSocket, la dirección y la contraseña.")
                return
            self.status = f"conectado (OBS {version})"
            self.rt.log(f"OBS {version} conectado en {host}:{port}")
            if manual:
                self.rt.config.settings["obs"] = {"host": host, "port": port, "autoconnect": False}
                try:
                    self.rt.config.save()
                except OSError as exc:
                    self.rt.log(f"OBS está conectado, pero no se guardaron los ajustes: {exc}")

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                if isinstance(client, _DebianObsClient):
                    await client.disconnect()
                else:
                    await asyncio.to_thread(client.disconnect)
            except Exception:
                pass
        self.status = "desconectado"

    async def stop(self) -> None:
        async with self._lock:
            await self._disconnect()

    def _require(self):
        if self._client is None:
            raise RuntimeError("OBS no está conectado")
        return self._client

    async def set_scene(self, scene: str) -> None:
        async with self._lock:
            client = self._require()
            if isinstance(client, _DebianObsClient):
                await client.call("SetCurrentProgramScene", sceneName=scene)
            else:
                await asyncio.to_thread(client.set_current_program_scene, scene)

    async def set_source_visible(self, scene: str, source: str, visible: bool) -> None:
        async with self._lock:
            client = self._require()

            if isinstance(client, _DebianObsClient):
                item = await client.call("GetSceneItemId", sceneName=scene, sourceName=source)
                await client.call("SetSceneItemEnabled", sceneName=scene,
                                  sceneItemId=item["sceneItemId"], sceneItemEnabled=visible)
                return

            def apply() -> None:
                item = client.get_scene_item_id(scene, source)
                client.set_scene_item_enabled(scene, item.scene_item_id, visible)

            await asyncio.to_thread(apply)
