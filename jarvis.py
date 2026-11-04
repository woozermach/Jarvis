# -*- coding: utf-8 -*-
"""J.A.R.V.I.S. v2 — голосовой ИИ-ассистент для Windows.
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
