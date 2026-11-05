# -*- coding: utf-8 -*-
"""Окно интерфейса — настоящее окно приложения на WebView2 (движок Edge, встроенный в Windows) через pywebview.
Отдельный процесс: pythonw core/window.py <url>. Ядро находит окно по заголовку (brand.WINDOW_TITLE), поэтому
трей, горячая клавиша и «показать/скрыть» работают как раньше. Если WebView2 или pywebview недоступны —
открывается прежнее окно Edge (--app)."""
import ctypes
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

(BASE / "data").mkdir(exist_ok=True)
logging.basicConfig(filename=str(BASE / "data" / "window.log"), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s window: %(message)s")
log = logging.getLogger("window")
IS_WIN = sys.platform.startswith("win")


def _cfg():
    try:
        return json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _dark(theme):
    if theme in ("dark", "light"):
        return theme == "dark"
    try:  # «как в системе»
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return True


def _find_hwnd(title, pid):
    """Окно с нашим заголовком, принадлежащее этому процессу."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value.startswith(title):
                found.append(h)
        return True
    u.EnumWindows(PROC(cb), 0)
    return found[0] if found else None


def _style_native(title, dark):
    """Иконка Oswin вместо иконки Python, тёмный заголовок, размер под экран."""
    u = ctypes.windll.user32
    h = None
    for _ in range(100):
        h = _find_hwnd(title, os.getpid())
        if h:
            break
        time.sleep(0.1)
    if not h:
        log.warning("окно не найдено для оформления")
        return
    ico = str(BASE / "ui" / "jarvis.ico")
    try:
        for kind, size in ((0, 16), (1, 256)):  # ICON_SMALL, ICON_BIG
            hi = u.LoadImageW(None, ico, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if hi:
                u.SendMessageW(h, 0x0080, kind, hi)  # WM_SETICON
    except Exception as e:
        log.warning("иконка: %s", e)
    try:  # DWMWA_USE_IMMERSIVE_DARK_MODE (20), на старых сборках Windows 10 — 19
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(h, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass
    try:  # 72 % × 80 % рабочей области монитора, по центру (в реальных пикселях)
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        mon = u.MonitorFromWindow(h, 2)  # MONITOR_DEFAULTTONEAREST
        if u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            wa = mi.rcWork
            ww, wh = wa.right - wa.left, wa.bottom - wa.top
            w, hh = int(ww * 0.72), int(wh * 0.80)
            u.SetWindowPos(h, None, wa.left + (ww - w) // 2, wa.top + (wh - hh) // 2, w, hh, 0x0004 | 0x0010)
    except Exception as e:
        log.warning("размер окна: %s", e)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    from core.brand import WINDOW_TITLE, APP_ID
    if IS_WIN:
        try:  # своя группа в панели задач (не вместе с другими программами на Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.assistant")
        except Exception:
            pass
    cfg = _cfg()
    dark = _dark(cfg.get("theme", "dark"))
    try:
        import webview
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_DOWNLOADS"] = True
        win = webview.create_window(WINDOW_TITLE, url, width=1280, height=820, min_size=(860, 560),
                                    background_color="#07080c" if dark else "#f5f5f7", text_select=True)
        if IS_WIN:
            win.events.shown += lambda: threading.Thread(target=_style_native, args=(WINDOW_TITLE, dark),
                                                         daemon=True).start()
        store = BASE / "data" / "webview"
        store.mkdir(parents=True, exist_ok=True)
        log.info("WebView2: %s", url)
        webview.start(gui="edgechromium" if IS_WIN else None, private_mode=False, storage_path=str(store))
    except Exception as e:
        log.warning("WebView2 недоступен (%s) — открываю окно Edge", e)
        from core.desktop import open_edge
        open_edge(url)


if __name__ == "__main__":
    main()
