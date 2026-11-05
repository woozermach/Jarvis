# -*- coding: utf-8 -*-
"""Oswin (бывший J.A.R.V.I.S. / Sayro) — голосовой ИИ-ассистент для Windows.
Запуск: start.bat (или .venv\\Scripts\\pythonw.exe jarvis.py). Отладка: start_debug.bat"""
import asyncio
import json
import logging
import os
import sys
import urllib.request

from core.config import Config, setup_logging


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1) as r:
            if json.loads(r.read()).get("jarvis"):
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/show", data=b"", method="POST"), timeout=2)
                return True
    except Exception:
        pass
    return False


def main():
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    setup_logging()
    log = logging.getLogger("jarvis")
    if sys.platform.startswith("win"):
        try:  # реальные пиксели экрана (для скриншотов и кликов)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    cfg = Config()
    from core.config import BASE
    for junk in ("dev_check.bat", "cleanup_dev.py", "cleanup_and_restart.bat"):  # остатки разработки
        try:
            (BASE / junk).unlink()
        except OSError:
            pass
    if already_running(int(cfg.get("port", 8765))):
        return
    try:  # автозапуск под прежним именем (Sayro / J.A.R.V.I.S.) → ярлык с новым именем
        from core.desktop import _startup_dir, set_autostart
        from core.brand import NAME, LEGACY_NAMES
        if sys.platform.startswith("win") and not (_startup_dir() / f"{NAME}.lnk").exists() \
                and any((_startup_dir() / f"{n}.lnk").exists() for n in LEGACY_NAMES):
            set_autostart(True)
        if sys.platform.startswith("win"):  # ярлыки «Sayro» в «Пуске» и на рабочем столе → новое имя
            from core.winsys import known_folder
            for folder in ("Programs", "Desktop"):
                d = known_folder(folder)
                old = d / "Sayro.lnk"
                if old.exists() and not (d / f"{NAME}.lnk").exists():
                    raw = old.read_bytes()
                    if b"jarvis.py" in raw or "jarvis.py".encode("utf-16-le") in raw:  # только наш ярлык
                        old.rename(d / f"{NAME}.lnk")
    except Exception as e:
        log.warning("ярлыки: %s", e)
    from core.assistant import Assistant
    a = Assistant()
    try:
        auto = "--autostart" in sys.argv
        show = "--no-window" not in sys.argv and (not auto or cfg.get("autostart_window"))
        asyncio.run(a.run(open_window=show))
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("Фатальная ошибка")
        raise
    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
