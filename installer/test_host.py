# -*- coding: utf-8 -*-
"""Проверка оболочки Oswin.exe в CI: окно, перезапуск ядра по команде, выход.
python installer/test_host.py <папка установки>"""
import asyncio
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import aiohttp
import psutil

D = Path(sys.argv[1])
LOG = D / "data" / "host.log"


def fail(msg):
    print("FAIL:", msg)
    print("--- host.log ---")
    print(LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else "(нет)")
    jl = D / "jarvis.log"
    if jl.exists():
        print("--- jarvis.log (хвост) ---")
        print("\n".join(jl.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))
    sys.exit(1)


def windows_of(pid):
    u = ctypes.windll.user32
    out = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            out.append(b.value)
        return True
    u.EnumWindows(PROC(cb), 0)
    return out


def wait(cond, sec, what):
    t = time.time()
    while time.time() - t < sec:
        if cond():
            return
        time.sleep(0.5)
    fail(what)


def port():
    try:
        return json.loads((D / "data" / "host.json").read_text(encoding="utf-8"))["port"]
    except Exception:
        return None


async def send(msg):
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(f"http://127.0.0.1:{port()}/ws") as ws:
            await ws.receive(timeout=10)  # снимок состояния
            await ws.send_str(json.dumps(msg))
            await asyncio.sleep(1)


exe = D / "Oswin.exe"
host = subprocess.Popen([str(exe)], cwd=str(D))
print("Oswin.exe pid", host.pid)
wait(lambda: "Oswin" in windows_of(host.pid), 90, "окно «Oswin» оболочки не появилось")
print("окно ok:", windows_of(host.pid))
kids = psutil.Process(host.pid).children()
print("дочерние:", [(k.pid, k.name()) for k in kids])
if not kids:
    fail("у Oswin.exe нет дочернего ядра")

# вторая копия не запускает второе ядро, а показывает окно первой
second = subprocess.run([str(exe)], cwd=str(D), timeout=30)
print("вторая копия вышла с кодом", second.returncode)
if host.poll() is not None:
    fail("первая копия завершилась после запуска второй")

before = LOG.read_text(encoding="utf-8").count("ядро запущено")
asyncio.run(send({"t": "restart"}))
wait(lambda: LOG.read_text(encoding="utf-8").count("ядро запущено") > before and port(), 60, "ядро не перезапустилось")
wait(lambda: "Oswin" in windows_of(host.pid), 60, "после перезапуска нет окна")
print("перезапуск ok")

time.sleep(5)
asyncio.run(send({"t": "quit"}))
try:
    host.wait(30)
except subprocess.TimeoutExpired:
    fail("Oswin.exe не завершился после выхода")
time.sleep(2)
left = [p.info for p in psutil.process_iter(["pid", "name", "exe"]) if str(D).lower() in str(p.info.get("exe") or "").lower()]
if left:
    fail(f"остались процессы: {left}")
print(LOG.read_text(encoding="utf-8"))
print("host ok")
