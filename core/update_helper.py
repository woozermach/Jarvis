# -*- coding: utf-8 -*-
"""Установщик обновления. Запускается ОТДЕЛЬНЫМ процессом из копии в data/update/ (только стандартная библиотека).

python helper.py <BASE> <NEW_DIR> <PORT> <OLD_VERSION> <NEW_VERSION>

1) ждёт, пока старый Джарвис закроется; 2) копирует текущую версию в data/backup/v<old>;
3) ставит новые файлы (config.json, data/, .venv/ не трогает); 4) при новых пакетах — pip install;
5) запускает Джарвиса и ждёт ответа /ping до 60 с; если не ответил — возвращает прежнюю версию."""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROTECTED = {"config.json", "data", ".venv", "py", "jarvis.log", "CLAUDE.local.md", "__pycache__", ".git"}
CODE_DIRS = ("core", "ui")
DETACHED, NO_WINDOW = 0x00000008, 0x08000000

BASE, NEW, PORT, OLD_V, NEW_V = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
UPD = BASE / "data" / "update"
LOG = UPD / "helper.log"


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + msg + "\n")


def alive():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ping", timeout=1.5) as r:
            return bool(json.loads(r.read()).get("jarvis"))
    except Exception:
        return False


def protected(rel: Path):
    return rel.parts[0] in PROTECTED or rel.name.startswith("jarvis.log")


def files_of(root: Path):
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not protected(rel) and "__pycache__" not in rel.parts:
            out.append(rel)
    return out


def copy_tree(src: Path, dst: Path):
    for rel in files_of(src):
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try:
                shutil.copy2(src / rel, t)
                break
            except PermissionError:
                time.sleep(1)
        else:
            raise PermissionError(f"файл занят: {rel}")


def prune(target: Path, keep: set):
    """Удаляет из core/ и ui/ файлы, которых нет в устанавливаемой версии (старые модули)."""
    for d in CODE_DIRS:
        for p in (target / d).rglob("*") if (target / d).exists() else []:
            rel = p.relative_to(target)
            if p.is_file() and rel not in keep and "__pycache__" not in rel.parts:
                try:
                    p.unlink()
                except OSError:
                    pass


def start():
    if (BASE / "Oswin.exe").exists():  # оболочка на Rust (3.3+) сама запустит ядро и окно
        subprocess.Popen([str(BASE / "Oswin.exe")], cwd=str(BASE), creationflags=NO_WINDOW)
        return
    s = BASE / ".venv" / "Scripts"
    pyw = next((p for p in (s / "Oswin.exe", s / "pythonw.exe") if p.exists()), Path(sys.executable))
    subprocess.Popen([str(pyw), str(BASE / "jarvis.py")], cwd=str(BASE), creationflags=NO_WINDOW)


def wait_up(sec):
    t = time.time()
    while time.time() - t < sec:
        if alive():
            return True
        time.sleep(1)
    return False


def is_jarvis_proc(info):
    """Только python-процесс, запущенный именно с jarvis.py из папки Джарвиса (не редактор, не консоль)."""
    c = info.get("cmdline") or []
    if len(c) < 2 or "python" not in Path(c[0]).name.lower():
        return False
    script = Path(c[1])
    if script.name.lower() != "jarvis.py":
        return False
    if not script.is_absolute():
        script = Path(info.get("cwd") or "") / script
    try:
        return script.resolve() == (BASE / "jarvis.py").resolve()
    except OSError:
        return False


def kill_jarvis():
    try:
        import psutil
        me = {os.getpid(), os.getppid()}
        for p in psutil.process_iter(["pid", "cmdline", "cwd"]):
            try:
                if p.pid not in me and is_jarvis_proc(p.info):
                    log(f"останавливаю процесс {p.pid}")
                    p.kill()
            except Exception:
                pass
    except Exception as e:
        log(f"kill: {e}")


def result(ok, **kw):
    (UPD / "result.json").write_text(json.dumps(dict(ok=ok, old=OLD_V, new=NEW_V, ts=time.time(), **kw), ensure_ascii=False),
                                     encoding="utf-8")


def main():
    log(f"=== обновление {OLD_V} → {NEW_V}")
    t = time.time()
    while alive() and time.time() - t < 25:
        time.sleep(0.5)
    if alive():
        kill_jarvis()
    time.sleep(1.5)

    backup = BASE / "data" / "backup" / f"v{OLD_V}"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    copy_tree(BASE, backup)
    log(f"копия старой версии: {backup}")
    # храним только две последние копии
    olds = sorted((BASE / "data" / "backup").iterdir(), key=lambda p: p.stat().st_mtime)
    for p in olds[:-2]:
        shutil.rmtree(p, ignore_errors=True)

    old_req = (BASE / "requirements.txt").read_text(encoding="utf-8") if (BASE / "requirements.txt").exists() else ""
    try:
        new_files = set(files_of(NEW))
        copy_tree(NEW, BASE)
        prune(BASE, new_files)
        log(f"установлено файлов: {len(new_files)}")
        new_req = (BASE / "requirements.txt").read_text(encoding="utf-8") if (BASE / "requirements.txt").exists() else ""
        if new_req.strip() != old_req.strip():
            vpy = BASE / ".venv" / "Scripts" / "python.exe"
            log("новые пакеты — pip install")
            r = subprocess.run([str(vpy), "-m", "pip", "install", "-r", str(BASE / "requirements.txt"),
                                "--disable-pip-version-check", "-q"], capture_output=True, text=True, timeout=900,
                               creationflags=NO_WINDOW)
            log(f"pip: код {r.returncode} {r.stderr[-400:]}")
        start()
        if wait_up(60):
            log("новая версия запустилась ✓")
            result(True)
            shutil.rmtree(NEW.parent if NEW.parent.name == "new" else NEW, ignore_errors=True)
            return
        raise RuntimeError("новая версия не ответила за 60 секунд")
    except Exception as e:
        log(f"ОШИБКА: {e!r} — откатываю")
        kill_jarvis()
        time.sleep(1.5)
        copy_tree(backup, BASE)
        prune(BASE, set(files_of(backup)))
        start()
        ok = wait_up(60)
        log("прежняя версия восстановлена" + (" ✓" if ok else ", но не отвечает!"))
        result(False, error=str(e)[:300], restored=ok)


if __name__ == "__main__":
    UPD.mkdir(parents=True, exist_ok=True)
    try:
        main()
    except Exception as e:
        log(f"фатально: {e!r}")
        try:
            result(False, error=f"установщик упал: {e}"[:300], restored=False)
            start()
        except Exception:
            pass
