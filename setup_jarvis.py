# -*- coding: utf-8 -*-
"""Установщик J.A.R.V.I.S. v2: Python 3.13 → .venv → библиотеки → модель слова → самопроверка.
Запускается из install.bat любым установленным Python. Лог: data/install.log"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
(BASE / "data").mkdir(exist_ok=True)
LOG = BASE / "data" / "install.log"
VENV = BASE / ".venv"
VPY = VENV / "Scripts" / "python.exe"
logf = open(LOG, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def say(msg):
    print(msg, flush=True)
    logf.write(msg + "\n")
    logf.flush()


def run(cmd, check=True, show=True, timeout=1800):
    say("$ " + " ".join(str(c) for c in cmd))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=BASE,
                         text=True, encoding="utf-8", errors="replace", env=env)
    out = []
    t0 = time.time()
    for line in p.stdout:
        out.append(line)
        logf.write(line)
        logf.flush()
        if show:
            print("   " + line.rstrip()[:160], flush=True)
        if time.time() - t0 > timeout:
            p.kill()
            break
    p.wait()
    if check and p.returncode != 0:
        raise RuntimeError(f"команда завершилась с кодом {p.returncode}")
    return p.returncode, "".join(out)


def find_python():
    """Предпочитаем 3.13 (для неё есть все библиотеки), затем 3.12."""
    cands = []
    if shutil.which("py"):
        for tag in ("3.13", "3.12"):
            try:
                r = subprocess.run(["py", f"-V:{tag}", "-c", "import sys;print(sys.executable)"],
                                   capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and r.stdout.strip():
                    cands.append(r.stdout.strip().splitlines()[-1])
                    break
            except Exception:
                pass
    if sys.version_info[:2] in ((3, 13), (3, 12)):
        cands.append(sys.executable)
    return cands[0] if cands else None


def main():
    say("=== J.A.R.V.I.S. v2 : установка ===")
    say(f"Запущено из Python {sys.version.split()[0]} ({sys.executable})")
    py = find_python()
    if not py and shutil.which("py"):
        say("\nСтавлю Python 3.13 для Джарвиса (через менеджер Python), 1–3 минуты…")
        run(["py", "install", "3.13"], check=False)
        py = find_python()
    if not py:
        say("Python 3.13 поставить не удалось — использую текущий Python (часть функций может не установиться).")
        py = sys.executable
    say(f"\nPython для Джарвиса: {py}")

    if VPY.exists():
        r = subprocess.run([str(VPY), "-c", "import sys;print(sys.version_info[:2])"], capture_output=True, text=True)
        if r.returncode != 0:
            say("Старое окружение повреждено — пересоздаю")
            shutil.rmtree(VENV, ignore_errors=True)
    if not VPY.exists():
        say("\nСоздаю окружение .venv …")
        run([py, "-m", "venv", str(VENV)])

    say("\nОбновляю pip …")
    run([VPY, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "-q"], check=False)
    say("\nУстанавливаю библиотеки (несколько минут) …")
    code, _ = run([VPY, "-m", "pip", "install", "-r", "requirements.txt", "--disable-pip-version-check"], check=False)
    if code != 0:
        say("\nЧасть библиотек не встала — ставлю по одной, чтобы понять какие …")
        for line in (BASE / "requirements.txt").read_text(encoding="utf-8").splitlines():
            pkg = line.strip()
            if pkg and not pkg.startswith("#"):
                c, _ = run([VPY, "-m", "pip", "install", pkg, "--disable-pip-version-check", "-q"], check=False, show=False)
                say(f"   {pkg}: {'OK' if c == 0 else 'ОШИБКА'}")

    say("\nЗагружаю модель слова «Эй, Джарвис» …")
    run([VPY, "-c", "import sys,types;m=types.ModuleType('x');m.train_custom_verifier=None;"
               "sys.modules['openwakeword.custom_verifier_model']=m;"
               "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis']); print('model ok')"],
        check=False)

    say("\nСоздаю ярлык на рабочем столе …")
    try:
        desktop = Path(os.path.expanduser("~")) / "Desktop"
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "[Environment]::GetFolderPath('Desktop')"], capture_output=True, text=True)
        if r.stdout.strip():
            desktop = Path(r.stdout.strip())
        lnk = desktop / "J.A.R.V.I.S..lnk"
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
              f"$s.TargetPath='{VENV / 'Scripts' / 'pythonw.exe'}';$s.Arguments='\"{BASE / 'jarvis.py'}\"';"
              f"$s.WorkingDirectory='{BASE}';$s.IconLocation='{BASE / 'ui' / 'jarvis.ico'}';$s.Description='J.A.R.V.I.S.';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
        say(f"   {lnk}")
    except Exception as e:
        say(f"   не удалось: {e}")

    say("\nСамопроверка …")
    run([VPY, "selftest.py", "--quick"], check=False)
    say("\n=== Готово! Запускайте ярлык J.A.R.V.I.S. на рабочем столе или start.bat ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        say(f"\n[!] Ошибка установки: {e}\nПодробности: {LOG}")
        sys.exit(1)
