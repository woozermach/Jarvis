# -*- coding: utf-8 -*-
"""Локальный веб-сервер интерфейса (127.0.0.1) + WebSocket к HUD."""
import json
import logging
import socket

from aiohttp import web, WSMsgType

from .config import BASE

log = logging.getLogger("jarvis.server")
UI = BASE / "ui"


def free_port(preferred):
    for p in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return 0


async def start_server(assistant):
    app = web.Application()

    async def index(_):
        return web.FileResponse(UI / "index.html", headers={"Cache-Control": "no-store"})

    async def ping(_):
        return web.json_response({"jarvis": True})

    async def show(_):
        from .desktop import open_window
        open_window(assistant.port)
        return web.json_response({"ok": True})

    async def host_next(request):
        from . import host
        if not host.ACTIVE or request.query.get("token") != host.TOKEN:
            raise web.HTTPForbidden()
        cmd = await host.next_cmd()
        return web.json_response({"cmd": cmd} if cmd else {})

    async def ws_handler(request):
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4 * 2**20)
        await ws.prepare(request)
        assistant.clients.add(ws)
        await ws.send_str(json.dumps(assistant.snapshot(), ensure_ascii=False))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        await assistant.handle_ui(json.loads(msg.data))
                    except Exception:
                        log.exception("ui msg")
        finally:
            assistant.clients.discard(ws)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ping", ping)
    app.router.add_post("/show", show)
    app.router.add_get("/host/next", host_next)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/ui/", UI, show_index=False)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    port = free_port(int(assistant.cfg.get("port", 8765)))
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return port
