# -*- coding: utf-8 -*-
"""Связь с оболочкой Oswin.exe (папка shell/, Rust).

Оболочка — главный процесс приложения: она запускает ядро (pythonw jarvis.py) дочерним процессом с переменной
OSWIN_HOST_TOKEN, показывает окно интерфейса (WebView2) и перезапускает ядро, если оно попросит (код выхода 3)
или упадёт. Ядро пишет порт в data/host.json, а команды окну («show») отдаёт через долгий опрос GET /host/next.
Без оболочки (ручная установка, старый ярлык) ACTIVE = False и всё работает как раньше."""
import asyncio
import json
import os

from .config import BASE

TOKEN = os.environ.get("OSWIN_HOST_TOKEN", "")
ACTIVE = bool(TOKEN)
RESTART_CODE = 3  # «перезапусти меня» для оболочки

_loop = None
_q = None


def attach(loop, port):
    """Вызывается ядром после запуска веб-сервера."""
    global _loop, _q
    if not ACTIVE:
        return
    _loop, _q = loop, asyncio.Queue()
    d = BASE / "data"
    d.mkdir(exist_ok=True)
    tmp = d / "host.json.tmp"
    tmp.write_text(json.dumps({"port": port, "token": TOKEN, "pid": os.getpid()}), encoding="utf-8")
    os.replace(tmp, d / "host.json")


def request(cmd):
    """Команда оболочке (из любого потока)."""
    if _loop and _q is not None:
        _loop.call_soon_threadsafe(_q.put_nowait, cmd)


async def next_cmd(timeout=25):
    if _q is None:
        await asyncio.sleep(timeout)
        return None
    try:
        return await asyncio.wait_for(_q.get(), timeout)
    except asyncio.TimeoutError:
        return None


def restart():
    os._exit(RESTART_CODE)
