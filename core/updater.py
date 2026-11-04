# -*- coding: utf-8 -*-
"""Обновления через GitHub Releases: проверка, скачивание, проверка целостности и запуск установщика."""
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests

from .config import BASE, DATA_DIR

log = logging.getLogger("jarvis.update")
UPD = DATA_DIR / "update"
DETACHED, NO_WINDOW = 0x00000008, 0x08000000


def current_version():
    try:
        return (BASE / "VERSION").read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)


class Updater:
    def __init__(self, ctx):
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.info = {"current": current_version(), "available": False, "checked": 0}
        self.busy = False

    @property
    def repo(self):
        return (self.cfg.get("update_repo") or "").strip().strip("/")

    def _get(self, url, **kw):
        h = {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-updater"}
        return requests.get(url, headers=h, timeout=kw.pop("timeout", 15), **kw)

    def check(self):
        cur = current_version()
        info = {"current": cur, "available": False, "checked": time.time(), "repo": self.repo}
        if not self.repo:
            info["error"] = "не задан репозиторий обновлений"
            self.info = info
            return info
        try:
            r = self._get(f"https://api.github.com/repos/{self.repo}/releases/latest")
            if r.status_code == 404:
                info["error"] = "в репозитории ещё нет выпусков"
            elif r.status_code == 403:
                info["error"] = "GitHub временно ограничил проверки, попробую позже"
            else:
                r.raise_for_status()
                j = r.json()
                latest = (j.get("tag_name") or "").lstrip("vV")
                info.update(latest=latest, notes=(j.get("body") or "").strip()[:4000], url=j.get("html_url", ""),
                            published=j.get("published_at", "")[:10], zip=j.get("zipball_url", ""),
                            available=vtuple(latest) > vtuple(cur))
                asset = next((a for a in j.get("assets", []) if a.get("name", "").lower().endswith(".zip")), None)
                if asset:
                    info["zip"] = asset["browser_download_url"]
        except Exception as e:
            info["error"] = f"нет связи с GitHub: {str(e)[:120]}"
        self.info = info
        log.info("проверка обновлений: %s", {k: v for k, v in info.items() if k != "notes"})
        return info

    def _progress(self, text):
        log.info("update: %s", text)
        self.ctx._threadsafe({"t": "update_progress", "text": text})

    def install(self):
        """Скачивает и проверяет выпуск, запускает установщик и завершает текущий процесс. Вызывать в потоке."""
        if self.busy:
            return {"error": "обновление уже идёт"}
        info = self.check()
        if not info.get("available"):
            return {"error": info.get("error") or f"уже последняя версия {info['current']}"}
        self.busy = True
        try:
            self._progress(f"Скачиваю версию {info['latest']}…")
            r = self._get(info["zip"], timeout=120)
            r.raise_for_status()
            new_root = UPD / "new"
            shutil.rmtree(new_root, ignore_errors=True)
            new_root.mkdir(parents=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall(new_root)
            subs = [p for p in new_root.iterdir() if p.is_dir()]
            src = subs[0] if len(subs) == 1 and not (new_root / "jarvis.py").exists() else new_root
            self._progress("Проверяю файлы…")
            for need in ("jarvis.py", "core/assistant.py", "ui/index.html", "VERSION"):
                if not (src / need).exists():
                    raise RuntimeError(f"в выпуске нет {need}")
            ver = (src / "VERSION").read_text(encoding="utf-8").strip()
            if vtuple(ver) != vtuple(info["latest"]):
                raise RuntimeError(f"версия в файлах ({ver}) не совпадает с выпуском ({info['latest']})")
            for py in src.rglob("*.py"):  # битый файл не должен попасть на диск
                compile(py.read_text(encoding="utf-8"), str(py), "exec")
            helper = UPD / "helper.py"
            shutil.copy2(src / "core" / "update_helper.py", helper)
            vpy = BASE / ".venv" / "Scripts" / "python.exe"
            py = str(vpy if vpy.exists() else Path(sys.executable))
            self._progress(f"Устанавливаю {ver} и перезапускаюсь…")
            subprocess.Popen([py, str(helper), str(BASE), str(src), str(self.ctx.port), info["current"], ver],
                             cwd=str(UPD), creationflags=DETACHED | NO_WINDOW)
            self.ctx.later(1.5, lambda: __import__("os")._exit(0))
            return {"ok": True, "installing": ver}
        except Exception as e:
            self.busy = False
            log.exception("update")
            self._progress(f"Не удалось обновиться: {str(e)[:150]}")
            return {"error": str(e)[:200]}

    @staticmethod
    def pop_result():
        p = UPD / "result.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            d = None
        p.unlink(missing_ok=True)
        return d
