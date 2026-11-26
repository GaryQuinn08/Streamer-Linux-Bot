"""Arranque local y servidor sin Qt, administrable por SSH."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path

from .connectors.simulator import SAMPLE_KINDS, sample_event
from .core.config import Config
from .runtime import Runtime


def port_number(raw: str) -> int:
    try:
        n = int(raw)
    except ValueError:
        n = -1
    if not 1 <= n <= 65535:
        raise argparse.ArgumentTypeError("escribe un puerto entre 1 y 65535")
    return n


async def serve(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    rt = Runtime(config=config, port=args.puerto)
    loop = asyncio.get_running_loop()
    rt.loop = loop
    stop = asyncio.Event()
    installed_signals = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
            installed_signals.append(signum)
        except NotImplementedError:
            pass
    def reload_editor_profile():
        try:
            data = Config.load(config.path, recover=False)
        except (OSError, ValueError) as exc:
            rt.log(f"No se pudo recargar el perfil: {exc}")
            return
        config.triggers, config.actions = data.triggers, data.actions
        config.settings["overlay_presets"] = data.settings.get("overlay_presets", {})
        config.settings["timers"] = data.settings.get("timers", [])
        rt.log("Triggers, acciones, alertas y temporizadores recargados. Refresca las fuentes si cambiaste su apariencia.")

    if hasattr(signal, "SIGHUP") and os.name != "nt":
        loop.add_signal_handler(signal.SIGHUP, reload_editor_profile)
        installed_signals.append(signal.SIGHUP)
    try:
        await rt._startup()
        if rt.port is None:
            print(f"{rt.overlay_port_message} Reinicia con --puerto PUERTO.", flush=True)
            return 2
        print(f"Catálogo: http://127.0.0.1:{rt.port}/", flush=True)
        if args.kick_clave:
            try:
                await rt.connectors["kick"].start(args.kick_puerto, args.kick_canal, args.kick_clave)
            except ImportError:
                print("Falta cryptography. Instala con bash instalar.sh --servidor --kick.", flush=True)
                return 2
            except (OSError, ValueError) as exc:
                print(f"No se pudo iniciar Kick: {exc}", flush=True)
                return 2
        if args.obs:
            await rt.obs.start(password=os.environ.get("SLB_OBS_PASSWORD", ""), remember=False)
        if args.tiktok:
            await rt.connectors["tiktok"].start(args.tiktok, args.canal)
        for name in ("twitch", "youtube"):
            if getattr(args, name):
                await rt.connectors[name].start()
        if args.simular:
            try:
                await asyncio.wait_for(stop.wait(), timeout=args.espera)
            except TimeoutError:
                await rt.bus.publish(sample_event(args.simular))
        if not stop.is_set():
            await stop.wait()
        return 0
    finally:
        await rt._shutdown()
        for signum in installed_signals:
            loop.remove_signal_handler(signum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Streamer Linux Bot: escritorio local o servidor por terminal")
    modes = parser.add_subparsers(dest="mode")
    modes.add_parser("escritorio", help="abre la interfaz gráfica (opción predeterminada)")
    edit = modes.add_parser("configurar", help="editar un perfil sin arrancar el motor ni abrir puertos")
    edit.add_argument("--config", type=Path, help="ruta de un config.json, opcional")
    server = modes.add_parser("servidor", help="inicia sin escritorio ni Qt")
    server.add_argument("--config", type=Path, help="ruta de un config.json, opcional")
    server.add_argument("--puerto", type=port_number, help="puerto de overlays; no cambia el archivo")
    server.add_argument("--tiktok", choices=("directo", "tikfinity"))
    server.add_argument("--canal", default="", help="@usuario para TikTok directo")
    server.add_argument("--twitch", action="store_true")
    server.add_argument("--youtube", action="store_true")
    server.add_argument("--kick-clave", type=Path, help="clave pública PEM actual de Kick")
    server.add_argument("--kick-canal", type=int, help="ID numérico del canal Kick")
    server.add_argument("--kick-puerto", type=port_number, default=8770)
    server.add_argument("--obs", action="store_true", help="conecta al OBS configurado; toma SLB_OBS_PASSWORD")
    server.add_argument("--simular", choices=SAMPLE_KINDS, help="lanza un evento de prueba al arrancar")
    server.add_argument("--espera", default=10, type=int, choices=range(0, 61), metavar="0..60",
                        help="segundos antes del evento simulado (10 por defecto)")
    args = parser.parse_args(argv)
    config_path = getattr(args, "config", None)
    if config_path:
        config_path.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "servidor":
        if args.tiktok == "directo" and not args.canal:
            parser.error("--tiktok directo requiere --canal @usuario")
        if (args.kick_clave is None) != (args.kick_canal is None):
            parser.error("Kick requiere --kick-clave y --kick-canal juntos")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
        try:
            return asyncio.run(serve(args))
        except KeyboardInterrupt:
            return 130
    from .app import main as desktop
    return desktop(["streamer-linux-bot"], editor_only=(args.mode == "configurar"),
                   config=Config.load(config_path) if config_path else None)
