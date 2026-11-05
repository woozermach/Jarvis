# -*- coding: utf-8 -*-
"""Обновления из GitHub (файл VERSION в ветке main): проверка, скачивание, проверка целостности и запуск установщика."""
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
        h = kw.pop("headers", None) or {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-updater"}
        return requests.get(url, headers=h, timeout=kw.pop("timeout", 15), **kw)

    def _changelog(self, text, cur, latest):
        """Разделы CHANGELOG.md «## 2.1.1 …» новее текущей версии и не новее latest."""
        out, keep = [], False
        for line in text.splitlines():
            m = re.match(r"^##\s*v?(\d+(?:\.\d+)*)", line)
            if m:
                v = vtuple(m.group(1))
                keep = vtuple(cur) < v <= vtuple(latest)
                if keep:
                    out.append(f"**{line.lstrip('# ').strip()}**")
                continue
            if keep:
                out.append(line)
        return "\n".join(out).strip()[:4000]

    def check(self):
        """Новая версия = номер в VERSION ветки main больше текущего. Выпуск = просто push в main."""
        cur = current_version()
        info = {"current": cur, "available": False, "checked": time.time(), "repo": self.repo}
        if not self.repo:
            info["error"] = "не задан репозиторий обновлений"
            self.info = info
            return info
        branch = (self.cfg.get("update_branch") or "main").strip()
        raw = f"https://raw.githubusercontent.com/{self.repo}/{branch}"
        api = f"https://api.github.com/repos/{self.repo}/contents"

        def fetch(name):
            # API отвечает сразу (CDN raw.githubusercontent кэширует до 5 мин); лимит API — 60 запросов в час
            r = self._get(f"{api}/{name}?ref={branch}", headers={"Accept": "application/vnd.github.raw+json",
                                                                 "User-Agent": "jarvis-updater"})
            if r.status_code in (403, 429):
                r = self._get(f"{raw}/{name}")
            return r
        try:
            r = fetch("VERSION")
            if r.status_code == 404:
                info["error"] = "в репозитории ещё нет файла VERSION"
            else:
                r.raise_for_status()
                latest = r.text.strip()
                info.update(latest=latest, available=vtuple(latest) > vtuple(cur), branch=branch,
                            url=f"https://github.com/{self.repo}", zip=f"https://codeload.github.com/{self.repo}/zip/refs/heads/{branch}")
                if info["available"]:
                    try:
                        cl = fetch("CHANGELOG.md")
                        if cl.ok:
                            info["notes"] = self._changelog(cl.text, cur, latest)
                    except Exception:
                        pass
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
            if vtuple(ver) <= vtuple(info["current"]):
                raise RuntimeError(f"в скачанных файлах версия {ver} — не новее текущей")
            for py in src.rglob("*.py"):  # битый файл не должен попасть на диск
                compile(py.read_text(encoding="utf-8"), str(py), "exec")
            helper = UPD / "helper.py"
            shutil.copy2(src / "core" / "update_helper.py", helper)
            # pythonw, а не python.exe: консольный python (особенно лаунчер venv) показывал чёрное окно
            vpy = next((p for p in (BASE / ".venv" / "Scripts" / "pythonw.exe", BASE / ".venv" / "Scripts" / "python.exe")
                        if p.exists()), Path(sys.executable))
            py = str(vpy)
            self._progress(f"Устанавливаю {ver} и перезапускаюсь…")
            subprocess.Popen([py, str(helper), str(BASE), str(src), str(self.ctx.port), info["current"], ver],
                             cwd=str(UPD), creationflags=NO_WINDOW)
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
