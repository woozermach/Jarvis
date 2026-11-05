# -*- coding: utf-8 -*-
"""Перезапуск Джарвиса: завершает запущенные копии и запускает заново."""
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    import psutil
except Exception:
    psutil = None
me = {os.getpid(), os.getppid()}
killed = 0
if psutil:
    for p in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            c = p.info["cmdline"] or []
            if p.pid in me or len(c) < 2 or not any(x in Path(c[0]).name.lower() for x in ("python", "oswin")) or Path(c[1]).name.lower() != "jarvis.py":
                continue
            script = Path(c[1]) if Path(c[1]).is_absolute() else Path(p.info.get("cwd") or "") / c[1]
            if script.resolve() == (BASE / "jarvis.py").resolve():
                p.kill()
                killed += 1
        except Exception:
            pass
time.sleep(1.5)
pyw = next((p for p in (BASE / ".venv" / "Scripts" / "Oswin.exe", BASE / ".venv" / "Scripts" / "pythonw.exe") if p.exists()))
args = [str(pyw), str(BASE / "jarvis.py")] + (["--no-window"] if "--quiet" in sys.argv else [])
subprocess.Popen(args, cwd=str(BASE), creationflags=0x08000000)
print(f"остановлено процессов: {killed}; Джарвис запущен заново")
