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


def _set_taskbar_identity(h, app_id, title):
    """Имя и значок в панели задач / меню правой кнопки: «Oswin» вместо «Python».
    Свойства окна System.AppUserModel.* (ID, RelaunchCommand, RelaunchDisplayNameResource, RelaunchIconResource)."""
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.USHORT), ("r2", wintypes.USHORT), ("r3", wintypes.USHORT),
                    ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p)]

    def guid(sv):
        g = GUID()
        ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(sv), ctypes.byref(g))
        return g

    ctypes.windll.ole32.CoInitialize(None)
    store = ctypes.c_void_p()
    iid = guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")  # IID_IPropertyStore
    if ctypes.windll.shell32.SHGetPropertyStoreForWindow(wintypes.HWND(h), ctypes.byref(iid), ctypes.byref(store)) != 0:
        return False
    vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    SetValue = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                  ctypes.POINTER(PROPVARIANT))(vtbl[6])
    Commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
    Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    fmt = guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")  # PKEY_AppUserModel_*
    pyw = BASE / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.exists():
        pyw = Path(sys.executable).with_name("pythonw.exe")
    values = {5: app_id,                                                   # ID
              2: f'"{pyw}" "{BASE / "jarvis.py"}"',                       # RelaunchCommand
              3: f'{BASE / "ui" / "jarvis.ico"},0',                        # RelaunchIconResource
              4: title}                                                    # RelaunchDisplayNameResource
    keep = []
    for pid in (5, 2, 3, 4):  # ID — первым
        buf = ctypes.create_unicode_buffer(values[pid])
        keep.append(buf)
        pv = PROPVARIANT(vt=31, val=ctypes.cast(buf, ctypes.c_void_p))  # VT_LPWSTR
        SetValue(store, ctypes.byref(PROPERTYKEY(fmt, pid)), ctypes.byref(pv))
    Commit(store)
    Release(store)
    return True


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
    try:
        from core.brand import APP_ID
        _set_taskbar_identity(h, f"{APP_ID}.assistant", title)
    except Exception as e:
        log.warning("панель задач: %s", e)
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
