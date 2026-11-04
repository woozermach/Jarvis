# -*- coding: utf-8 -*-
"""Windows: клавиши, громкость, яркость, буфер обмена, окна, питание, системные папки, статистика."""
import ctypes
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from .config import IS_WIN, NO_WINDOW

log = logging.getLogger("jarvis.win")

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

# ───────────────────────── клавиатура ─────────────────────────
VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "printscreen": 0x2C, "capslock": 0x14,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
}
for i in range(1, 13):
    VK[f"f{i}"] = 0x6F + i
EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}


def _vk_of(name: str):
    name = name.strip().lower()
    if name in VK:
        return VK[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    raise ValueError(f"неизвестная клавиша: {name}")


def tap(vk: int, times: int = 1, delay: float = 0.006):
    if not IS_WIN:
        return
    u = ctypes.windll.user32
    ext = 1 if vk in EXTENDED else 0
    for _ in range(max(0, int(times))):
        u.keybd_event(vk, 0, ext, 0)
        u.keybd_event(vk, 0, ext | 2, 0)
        time.sleep(delay)


def hotkey(combo: str):
    """Нажать сочетание вида 'ctrl+shift+esc' или 'win+d'."""
    if not IS_WIN:
        return
    keys = [_vk_of(k) for k in combo.replace(" ", "").split("+") if k]
    u = ctypes.windll.user32
    for vk in keys:
        u.keybd_event(vk, 0, 1 if vk in EXTENDED else 0, 0)
        time.sleep(0.02)
    for vk in reversed(keys):
        u.keybd_event(vk, 0, (1 if vk in EXTENDED else 0) | 2, 0)
        time.sleep(0.01)


# ───────────────────────── громкость (pycaw, запасной вариант — клавиши) ─────────────────────────
def _endpoint():
    import comtypes  # noqa
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetSpeakers()
    ev = getattr(dev, "EndpointVolume", None)
    if ev is not None:
        return ev
    from comtypes import CLSCTX_ALL
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))


def get_volume():
    try:
        ev = _endpoint()
        return int(round(ev.GetMasterVolumeLevelScalar() * 100)), bool(ev.GetMute())
    except Exception as e:
        log.debug("get_volume: %s", e)
        return None, None


def set_volume(level: int):
    level = max(0, min(100, int(level)))
    try:
        ev = _endpoint()
        ev.SetMasterVolumeLevelScalar(level / 100.0, None)
        if level > 0:
            ev.SetMute(0, None)
        return level
    except Exception as e:
        log.info("pycaw недоступен (%s) — громкость клавишами", e)
        tap(VK["volume_down"], 50)
        tap(VK["volume_up"], round(level / 2))
        return level


def change_volume(delta: int):
    cur, _ = get_volume()
    if cur is None:
        tap(VK["volume_up"] if delta > 0 else VK["volume_down"], max(1, round(abs(delta) / 2)))
        return None
    return set_volume(cur + int(delta))


def set_mute(mute):
    """mute: True/False/None(переключить). Возвращает новое состояние."""
    try:
        ev = _endpoint()
        new = (not ev.GetMute()) if mute is None else bool(mute)
        ev.SetMute(1 if new else 0, None)
        return new
    except Exception:
        tap(VK["volume_mute"])
        return None


# ───────────────────────── яркость ─────────────────────────
def _ps(script: str, timeout=20):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
                       capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    return r.stdout.decode("utf-8", "ignore").strip(), r.stderr.decode("utf-8", "ignore").strip()


def get_brightness():
    out, _ = _ps("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select -First 1).CurrentBrightness")
    return int(out) if out.isdigit() else None


def set_brightness(level: int):
    level = max(0, min(100, int(level)))
    out, err = _ps(f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select -First 1)"
                   f" | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={level}}} | Out-Null; 'ok'")
    if "ok" not in out:
        raise RuntimeError(err or "дисплей не поддерживает управление яркостью")
    return level


# ───────────────────────── буфер обмена ─────────────────────────
def _clip_api():
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u.OpenClipboard.argtypes = [wintypes.HWND]; u.OpenClipboard.restype = wintypes.BOOL
    u.GetClipboardData.argtypes = [wintypes.UINT]; u.GetClipboardData.restype = wintypes.HANDLE
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]; u.SetClipboardData.restype = wintypes.HANDLE
    u.EmptyClipboard.restype = wintypes.BOOL; u.CloseClipboard.restype = wintypes.BOOL
    k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]; k.GlobalAlloc.restype = wintypes.HGLOBAL
    k.GlobalLock.argtypes = [wintypes.HGLOBAL]; k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]; k.GlobalUnlock.restype = wintypes.BOOL
    return u, k


def _open_clip(u):
    for _ in range(20):
        if u.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def clipboard_get() -> str:
    if not IS_WIN:
        return ""
    u, k = _clip_api()
    if not _open_clip(u):
        raise RuntimeError("буфер обмена занят")
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_set(text: str):
    if not IS_WIN:
        return
    u, k = _clip_api()
    data = (text or "").encode("utf-16-le") + b"\x00\x00"
    h = k.GlobalAlloc(0x0002, len(data))
    p = k.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k.GlobalUnlock(h)
    if not _open_clip(u):
        raise RuntimeError("буфер обмена занят")
    try:
        u.EmptyClipboard()
        u.SetClipboardData(13, h)
    finally:
        u.CloseClipboard()


def type_text(text: str):
    """Вставляет текст в активное окно через буфер (работает с кириллицей), потом возвращает старый буфер."""
    try:
        old = clipboard_get()
    except Exception:
        old = None
    clipboard_set(text)
    time.sleep(0.05)
    hotkey("ctrl+v")
    if old is not None:
        def restore():
            time.sleep(0.6)
            try:
                clipboard_set(old)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()


# ───────────────────────── мышь ─────────────────────────
def click(x, y, button="left", double=False):
    if not IS_WIN:
        return
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    down, up = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}.get(button, (0x0002, 0x0004))
    for _ in range(2 if double else 1):
        u.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        u.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)


def scroll(amount: int):
    """amount > 0 — вверх, < 0 — вниз (в «щелчках» колеса)."""
    if IS_WIN:
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(amount) * 120, 0)


def screen_size():
    if not IS_WIN:
        return 1920, 1080
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


# ───────────────────────── окна ─────────────────────────
def foreground_title() -> str:
    if not IS_WIN:
        return ""
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    return buf.value


def foreground_process() -> str:
    """Имя процесса активного окна (например «eurotrucks2.exe»)."""
    if not IS_WIN or not psutil:
        return ""
    try:
        u = ctypes.windll.user32
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
        return psutil.Process(pid.value).name() if pid.value else ""
    except Exception:
        return ""


def is_fullscreen() -> bool:
    """Активное окно занимает весь экран (игра, видео в полноэкранном режиме)."""
    if not IS_WIN:
        return False
    try:
        from ctypes import wintypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h or h in (u.GetDesktopWindow(), u.GetShellWindow()):
            return False
        r = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        w, hh = screen_size()
        return r.left <= 0 and r.top <= 0 and r.right >= w and r.bottom >= hh
    except Exception:
        return False


def process_running(*names) -> bool:
    if not psutil:
        return False
    low = {n.lower() for n in names}
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() in low:
                return True
        except Exception:
            pass
    return False


def list_windows():
    if not IS_WIN:
        return []
    from ctypes import wintypes
    u = ctypes.windll.user32
    out = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                t = b.value.strip()
                if t and t not in ("Program Manager", "Параметры", "Microsoft Text Input Application"):
                    out.append((h, t))
        return True
    u.EnumWindows(PROC(cb), 0)
    return out


def focus_window(query: str):
    import difflib
    q = query.lower()
    best, score = None, 0.0
    for h, t in list_windows():
        tl = t.lower()
        s = 1.0 if q in tl else difflib.SequenceMatcher(None, q, tl).ratio()
        if s > score:
            best, score = (h, t), s
    if not best or score < 0.45:
        return None
    u = ctypes.windll.user32
    h = best[0]
    if u.IsIconic(h):
        u.ShowWindow(h, 9)  # SW_RESTORE
    # трюк с Alt, чтобы Windows разрешила сменить фокус
    u.keybd_event(0x12, 0, 0, 0)
    u.SetForegroundWindow(h)
    u.keybd_event(0x12, 0, 2, 0)
    return best[1]


# ───────────────────────── питание и прочее ─────────────────────────
def lock():
    ctypes.windll.user32.LockWorkStation()


def sleep_pc():
    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NO_WINDOW)


def shutdown(restart=False, delay=20):
    subprocess.run(["shutdown", "/r" if restart else "/s", "/t", str(int(delay))], creationflags=NO_WINDOW)


def cancel_shutdown():
    subprocess.run(["shutdown", "/a"], creationflags=NO_WINDOW, capture_output=True)


def empty_recycle_bin():
    r = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    return r in (0, -2147418113)  # S_OK или «корзина уже пуста»


def open_path(target: str):
    if IS_WIN:
        os.startfile(target)  # noqa
    else:
        subprocess.Popen(["xdg-open", target])


KNOWN_FOLDERS = {
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


def known_folder(name: str) -> Path:
    if IS_WIN and name in KNOWN_FOLDERS:
        try:
            class GUID(ctypes.Structure):
                _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                            ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
            g = GUID()
            ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(KNOWN_FOLDERS[name]), ctypes.byref(g))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                v = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return Path(v)
        except Exception as e:
            log.warning("known_folder %s: %s", name, e)
    return Path.home() / name


# ───────────────────────── статистика системы ─────────────────────────
class Stats:
    def __init__(self):
        self._net = None
        self._gpu = {}
        self._gpu_ts = 0
        if psutil:
            psutil.cpu_percent(None)

    def gpu(self):
        if time.time() - self._gpu_ts < 2.5:
            return self._gpu
        self._gpu_ts = time.time()
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4,
                               creationflags=NO_WINDOW)
            line = r.stdout.strip().splitlines()[0]
            name, util, temp, mu, mt = [x.strip() for x in line.split(",")]
            self._gpu = {"name": name.replace("NVIDIA GeForce ", ""), "util": float(util), "temp": float(temp),
                         "mem_used": float(mu), "mem_total": float(mt)}
        except Exception:
            self._gpu = {}
        return self._gpu

    def snapshot(self):
        d = {"ts": time.time()}
        if psutil:
            d["cpu"] = psutil.cpu_percent(None)
            vm = psutil.virtual_memory()
            d["ram"] = vm.percent
            d["ram_used"] = round(vm.used / 2**30, 1)
            d["ram_total"] = round(vm.total / 2**30, 1)
            try:
                du = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if IS_WIN else "/")
                d["disk_free"] = round(du.free / 2**30)
                d["disk"] = du.percent
            except Exception:
                pass
            b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            if b:
                d["battery"] = round(b.percent)
                d["plugged"] = bool(b.power_plugged)
            n = psutil.net_io_counters()
            now = time.time()
            if self._net:
                dt = max(0.1, now - self._net[0])
                d["down"] = max(0, (n.bytes_recv - self._net[1]) / dt)
                d["up"] = max(0, (n.bytes_sent - self._net[2]) / dt)
            self._net = (now, n.bytes_recv, n.bytes_sent)
            d["uptime"] = int(now - psutil.boot_time())
        g = self.gpu()
        if g:
            d["gpu"] = g
        return d

    @staticmethod
    def top_processes(n=5):
        if not psutil:
            return []
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                procs.append((p.info["memory_info"].rss, p.info["name"]))
            except Exception:
                pass
        procs.sort(reverse=True)
        agg = {}
        for rss, name in procs:
            agg[name] = agg.get(name, 0) + rss
        return [(k, round(v / 2**20)) for k, v in sorted(agg.items(), key=lambda x: -x[1])[:n]]
