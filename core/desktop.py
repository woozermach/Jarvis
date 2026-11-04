# -*- coding: utf-8 -*-
"""Окно (Edge в режиме приложения), значок в трее, глобальная горячая клавиша, уведомления."""
import ctypes
import logging
import os
import subprocess
import threading
import webbrowser
from pathlib import Path

from .config import BASE, IS_WIN, NO_WINDOW

log = logging.getLogger("jarvis.desktop")
_proc = None


def _edge_path():
    for root in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LocalAppData")):
        if root:
            p = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if p.exists():
                return str(p)
    return None


def open_window(port):
    global _proc
    url = f"http://127.0.0.1:{port}/"
    if IS_WIN and _find_hwnd():  # окно уже открыто (например, после перезапуска) — просто показать
        focus_window(port)
        return
    edge = _edge_path() if IS_WIN else None
    if edge:
        prof = BASE / "data" / "edge_profile"
        prof.mkdir(parents=True, exist_ok=True)
        try:
            _proc = subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={prof}", "--window-size=1440,900",
                                      "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
                                      "--autoplay-policy=no-user-gesture-required", "--disable-background-timer-throttling"],
                                     creationflags=NO_WINDOW)
            return
        except Exception as e:
            log.warning("Edge: %s", e)
    webbrowser.open(url)


def _find_hwnd():
    if not IS_WIN:
        return None
    from ctypes import wintypes
    u = ctypes.windll.user32
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value.startswith("J.A.R.V.I.S"):
                found.append(h)
        return True
    u.EnumWindows(PROC(cb), 0)
    return found[0] if found else None


def set_window_visible(visible):
    h = _find_hwnd()
    if h:
        ctypes.windll.user32.ShowWindow(h, 5 if visible else 0)  # SW_SHOW / SW_HIDE


def minimize_window():
    h = _find_hwnd()
    if h:
        ctypes.windll.user32.ShowWindow(h, 6)  # SW_MINIMIZE


def focus_window(port):
    h = _find_hwnd()
    if h:
        u = ctypes.windll.user32
        u.ShowWindow(h, 9)
        u.keybd_event(0x12, 0, 0, 0)
        u.SetForegroundWindow(h)
        u.keybd_event(0x12, 0, 2, 0)
    else:
        open_window(port)


def notify(title, text):
    """Всплывающее уведомление Windows (через PowerShell, без зависимостей)."""
    if not IS_WIN:
        return
    t = title.replace("'", "''")
    m = text.replace("'", "''")
    script = ("[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
              "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
              f"$x.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{t}'))|Out-Null;"
              f"$x.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{m}'))|Out-Null;"
              "$n=[Windows.UI.Notifications.ToastNotification]::new($x);"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script], creationflags=NO_WINDOW)
    except Exception:
        pass


# ── горячая клавиша ──
MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
_hk = {"tid": None}
VK_NAMES = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
            "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "`": 0xC0}
for _i in range(1, 25):
    VK_NAMES[f"f{_i}"] = 0x6F + _i


def parse_hotkey(combo):
    mods, vk = 0x4000, None  # MOD_NOREPEAT
    for k in (combo or "").lower().replace(" ", "").split("+"):
        if k in MODS:
            mods |= MODS[k]
        elif k in VK_NAMES:
            vk = VK_NAMES[k]
        elif len(k) == 1 and k.isalnum():
            vk = ord(k.upper())
    return mods, vk


def start_hotkey(assistant):
    if not IS_WIN:
        return
    stop_hotkey()
    mods, vk = parse_hotkey(assistant.cfg.get("hotkey") or "ctrl+alt+j")
    if vk is None:
        return

    def run():
        from ctypes import wintypes
        u = ctypes.windll.user32
        _hk["tid"] = ctypes.windll.kernel32.GetCurrentThreadId()
        if not u.RegisterHotKey(None, 1, mods, vk):
            log.warning("Горячая клавиша %s занята другой программой", assistant.cfg.get("hotkey"))
            assistant.hotkey_ok = False
            return
        assistant.hotkey_ok = True
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                assistant.loop.call_soon_threadsafe(lambda: __import__("asyncio").create_task(assistant.activate("hotkey")))
        u.UnregisterHotKey(None, 1)
    threading.Thread(target=run, daemon=True, name="hotkey").start()


def stop_hotkey():
    if IS_WIN and _hk.get("tid"):
        ctypes.windll.user32.PostThreadMessageW(_hk["tid"], 0x0012, 0, 0)  # WM_QUIT
        _hk["tid"] = None


# ── автозапуск с Windows ──
def _startup_dir():
    from .winsys import known_folder, KNOWN_FOLDERS
    KNOWN_FOLDERS.setdefault("Startup", "{B97D20BB-F46A-4C97-BA10-5E3608430854}")
    return known_folder("Startup")


def set_autostart(enabled: bool):
    if not IS_WIN:
        return False
    lnk = _startup_dir() / "J.A.R.V.I.S..lnk"
    if not enabled:
        try:
            lnk.unlink()
        except FileNotFoundError:
            pass
        return True
    pyw = BASE / ".venv" / "Scripts" / "pythonw.exe"
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          f"$s.TargetPath='{pyw}';$s.Arguments='\"{BASE / 'jarvis.py'}\" --autostart';"
          f"$s.WorkingDirectory='{BASE}';$s.IconLocation='{BASE / 'ui' / 'jarvis.ico'}';$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    return lnk.exists()


def autostart_enabled():
    try:
        return (_startup_dir() / "J.A.R.V.I.S..lnk").exists()
    except Exception:
        return False


def restart_jarvis():
    """Перезапуск: новый процесс стартует через 2 с, текущий завершается."""
    pyw = BASE / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.exists():
        import sys
        pyw = Path(sys.executable)
    subprocess.Popen(f'cmd /c timeout /t 2 /nobreak >nul & start "" "{pyw}" "{BASE / "jarvis.py"}"',
                     shell=True, creationflags=NO_WINDOW | 0x00000008)
    os._exit(0)


# ── трей ──
def _icon_image():
    from PIL import Image, ImageDraw
    s = 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, s - 4, s - 4), outline=(80, 220, 255, 255), width=5)
    d.ellipse((20, 20, s - 20, s - 20), fill=(120, 235, 255, 255))
    return img


def start_tray(assistant):
    try:
        import pystray
    except Exception as e:
        log.info("pystray недоступен: %s", e)
        return

    def show(icon=None, item=None):
        focus_window(assistant.port)

    def toggle_mic(icon, item):
        assistant.mic_enabled = not assistant.mic_enabled
        assistant.loop.call_soon_threadsafe(assistant.broadcast, {"t": "mic", "on": assistant.mic_enabled})

    def quit_(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Открыть Джарвиса", show, default=True),
        pystray.MenuItem("Микрофон", toggle_mic, checked=lambda item: assistant.mic_enabled),
        pystray.MenuItem("Выход", quit_),
    )
    icon = pystray.Icon("jarvis", _icon_image(), "J.A.R.V.I.S.", menu)
    threading.Thread(target=icon.run, daemon=True, name="tray").start()
