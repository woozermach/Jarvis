# -*- coding: utf-8 -*-
"""Поиск и запуск установленных программ, сайтов, системных страниц; закрытие процессов; поиск файлов."""
import difflib
import json
import logging
import os
import re
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from .config import IS_WIN, NO_WINDOW
from .util import match_stem, norm, translit
from . import winsys

log = logging.getLogger("jarvis.apps")
try:
    import psutil
except Exception:
    psutil = None

FOLDERS = {
    "загрузк": "Downloads", "скачанн": "Downloads", "документ": "Documents",
    "рабочий стол": "Desktop", "рабочем стол": "Desktop", "изображени": "Pictures",
    "картинк": "Pictures", "фотографи": "Pictures", "видео": "Videos", "музык": "Music",
    "скриншот": "SCREENSHOTS", "папку джарвис": "BASE",
}

SITES = {
    "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com",
    "гугл$": "https://www.google.com", "google$": "https://www.google.com",
    "почт": "https://mail.google.com", "gmail": "https://mail.google.com", "джимейл": "https://mail.google.com",
    "вк$": "https://vk.com", "вконтакт": "https://vk.com",
    "инстаграм": "https://www.instagram.com", "instagram": "https://www.instagram.com",
    "тикток": "https://www.tiktok.com", "tiktok": "https://www.tiktok.com",
    "твич": "https://www.twitch.tv", "twitch": "https://www.twitch.tv",
    "гитхаб": "https://github.com", "github": "https://github.com",
    "чат gpt": "https://chatgpt.com", "чатгпт": "https://chatgpt.com", "chatgpt": "https://chatgpt.com",
    "чат джипити": "https://chatgpt.com", "клод": "https://claude.ai", "claude": "https://claude.ai",
    "джемини": "https://gemini.google.com", "gemini": "https://gemini.google.com",
    "переводчик": "https://translate.google.com", "карт": "https://maps.google.com",
    "файвер": "https://www.fiverr.com", "fiverr": "https://www.fiverr.com",
    "апворк": "https://www.upwork.com", "upwork": "https://www.upwork.com",
    "википеди": "https://ru.wikipedia.org", "нетфликс": "https://www.netflix.com",
    "пинтерест": "https://www.pinterest.com", "реддит": "https://www.reddit.com",
    "юниза": "https://www.uniza.sk", "uniza": "https://www.uniza.sk",
    "гугл диск": "https://drive.google.com", "гугл календар": "https://calendar.google.com",
    "гугл документ": "https://docs.google.com", "гугл таблиц": "https://sheets.google.com",
    "steam store": "https://store.steampowered.com", "магазин стим": "https://store.steampowered.com",
}

BUILTIN = {
    "блокнот": "notepad", "калькулятор": "calc", "проводник": "explorer",
    "диспетчер задач": "taskmgr", "диспетчер": "taskmgr", "командн": "cmd", "консол": "cmd",
    "терминал": "wt", "пейнт": "mspaint", "paint": "mspaint", "панель управления": "control",
    "параметр": "ms-settings:", "настройки$": "ms-settings:", "настройки звука": "ms-settings:sound",
    "настройки блютуз": "ms-settings:bluetooth", "блютуз": "ms-settings:bluetooth", "bluetooth": "ms-settings:bluetooth",
    "wi-fi": "ms-settings:network-wifi", "вайфай": "ms-settings:network-wifi", "вай фай": "ms-settings:network-wifi",
    "настройки экрана": "ms-settings:display", "дисплей": "ms-settings:display",
    "обновлени": "ms-settings:windowsupdate", "настройки питания": "ms-settings:powersleep",
    "приложения и возможности": "ms-settings:appsfeatures", "персонализаци": "ms-settings:personalization",
    "микрофон настройки": "ms-settings:privacy-microphone", "конфиденциальност": "ms-settings:privacy",
    "браузер": "url:https://www.google.com", "магазин": "ms-windows-store:",
    "ножниц": "ms-screenclip:", "камер": "microsoft.windows.camera:", "часы": "ms-clock:",
    "корзин": "shell:RecycleBinFolder",
}

ALIASES = {
    "телеграм": "telegram", "дискорд": "discord", "стим": "steam", "спотифай": "spotify",
    "хром": "google chrome", "гугл хром": "google chrome", "эдж": "microsoft edge",
    "фаерфокс": "firefox", "файрфокс": "firefox", "опер": "opera", "яндекс браузер": "yandex",
    "яндекс": "yandex", "ворд": "word", "эксель": "excel", "повер поинт": "powerpoint", "пауэр поинт": "powerpoint",
    "вс код": "visual studio code", "вскод": "visual studio code", "визуал студио код": "visual studio code",
    "обс": "obs studio", "фотошоп": "photoshop", "иллюстратор": "illustrator",
    "афтер эффект": "after effects", "афтер": "after effects", "премьер": "premiere pro",
    "блендер": "blender", "капкат": "capcut", "давинчи": "davinci resolve", "фигм": "figma",
    "кал оф дьюти": "call of duty", "колл оф дьюти": "call of duty", "калда": "call of duty", "калду": "call of duty",
    "батл нет": "battle.net", "баттл нет": "battle.net", "эпик": "epic games launcher",
    "зум": "zoom", "тимс": "teams", "ватсап": "whatsapp", "вотсап": "whatsapp", "вайбер": "viber",
    "нвидиа": "nvidia app", "майнкрафт": "minecraft", "кс$": "counter-strike 2", "контр страйк": "counter-strike 2",
    "дота": "dota 2", "гта": "grand theft auto", "мовави": "movavi", "алиса": "алиса",
    "евро трак": "euro truck simulator 2", "етс": "euro truck simulator 2", "батлфилд": "battlefield",
    "сатисфактори": "satisfactory", "сатисфакшн": "satisfactory", "курсфордж": "curseforge", "кёрсфордж": "curseforge",
    "разер": "razer", "хорайзон": "horizon", "слайм ранчер": "slime rancher", "хартс оф айрон": "hearts of iron",
    "парадокс": "paradox launcher", "рокстар": "rockstar games launcher", "мозила": "firefox",
}

PROC = {
    "хром": ["chrome.exe"], "гугл хром": ["chrome.exe"],
    "браузер": ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe"],
    "телеграм": ["telegram.exe"], "дискорд": ["discord.exe"], "стим": ["steam.exe"],
    "спотифай": ["spotify.exe"], "блокнот": ["notepad.exe"], "калькулятор": ["calculatorapp.exe", "calc.exe"],
    "ворд": ["winword.exe"], "эксель": ["excel.exe"], "эдж": ["msedge.exe"], "фаерфокс": ["firefox.exe"],
    "опер": ["opera.exe"], "яндекс": ["browser.exe"], "обс": ["obs64.exe"], "фотошоп": ["photoshop.exe"],
    "афтер": ["afterfx.exe"], "премьер": ["adobe premiere pro.exe"], "блендер": ["blender.exe"],
    "вс код": ["code.exe"], "вскод": ["code.exe"], "зум": ["zoom.exe"], "ватсап": ["whatsapp.exe", "whatsapp.root.exe"],
    "пейнт": ["mspaint.exe"], "диспетчер": ["taskmgr.exe"], "капкат": ["capcut.exe"], "эпик": ["epicgameslauncher.exe"],
    "кал оф дьюти": ["cod.exe"], "калда": ["cod.exe"], "проводник": [],
}

PROTECTED = {"system", "svchost", "csrss", "wininit", "winlogon", "lsass", "services", "smss", "dwm", "explorer",
             "python", "pythonw", "py", "pyw", "conhost", "fontdrvhost", "registry", "sihost", "ctfmon", "audiodg",
             "runtimebroker", "searchhost", "startmenuexperiencehost", "shellexperiencehost", "msedgewebview2",
             "claude", "textinputhost", "securityhealthsystray", "lockapp"}

BAD_NAMES = ("uninstall", "удал", "readme", "help", "documentation", "website", "release notes", "license",
             "справка", "сайт", "support", "manual")


class Apps:
    def __init__(self, cfg, base: Path):
        self.cfg = cfg
        self.base = base
        self.index = {}
        self.files = []
        self.ready = threading.Event()
        threading.Thread(target=self._build, daemon=True, name="app-index").start()

    # ── индекс программ ──
    def _build(self):
        try:
            self._build_apps()
        finally:
            self.ready.set()
        self._build_files()

    def _build_apps(self):
        if not IS_WIN:
            return
        idx = {}
        dirs = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                winsys.known_folder("Desktop"), Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
        for d in dirs:
            try:
                for p in d.rglob("*"):
                    if p.suffix.lower() in (".lnk", ".url", ".appref-ms"):
                        nm = p.stem.lower()
                        if not any(b in nm for b in BAD_NAMES):
                            idx.setdefault(nm, ("file", str(p)))
            except Exception as e:
                log.warning("index %s: %s", d, e)
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                                 capture_output=True, timeout=40, creationflags=NO_WINDOW).stdout.decode("utf-8-sig", "ignore").strip()
            items = json.loads(out) if out else []
            if isinstance(items, dict):
                items = [items]
            for it in items:
                nm = str(it.get("Name", "")).lower()
                if nm and not any(b in nm for b in BAD_NAMES):
                    idx.setdefault(nm, ("appid", it.get("AppID", "")))
        except Exception as e:
            log.warning("Get-StartApps: %s", e)
        self.index = idx
        log.info("Программ в индексе: %d", len(idx))

    def _build_files(self):
        roots = [winsys.known_folder(n) for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
        files = []
        skip = {"node_modules", ".git", "__pycache__", "appdata", ".venv", "venv", "my games", "steamapps"}
        for root in roots:
            if not root.exists():
                continue
            base_depth = len(root.parts)
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d.lower() not in skip and not d.startswith(".")]
                if len(Path(dirpath).parts) - base_depth >= 4:
                    dirnames[:] = []
                for f in filenames:
                    files.append(os.path.join(dirpath, f))
                    if len(files) > 60000:
                        break
        self.files = files
        log.info("Файлов в индексе: %d", len(files))

    @staticmethod
    def _score(c, name):
        if c == name:
            return 1.0
        words = re.split(r"[\s\-_\.\(\)®™]+", name)
        if len(c) >= 3 and (c in words or name.startswith(c + " ")):
            return 0.93
        if len(c) >= 4 and c in name:
            return 0.86
        return difflib.SequenceMatcher(None, c, name).ratio()

    def find_installed(self, n):
        self.ready.wait(8)
        cands = []
        a, _ = match_stem(n, ALIASES)
        if a:
            cands.append(a)
        cands.append(n)
        t = translit(n)
        if t != n:
            cands.append(t)
        best = (0.0, None, None)
        for c in cands:
            for name, target in self.index.items():
                s = self._score(c, name)
                if s > best[0]:
                    best = (s, name, target)
        return best if best[0] >= 0.74 else None

    @staticmethod
    def launch(target):
        kind, value = target
        if kind == "file":
            winsys.open_path(value)
        else:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{value}"])

    def folder_path(self, key):
        if key == "BASE":
            return self.base
        if key == "SCREENSHOTS":
            p = winsys.known_folder("Pictures") / "Jarvis"
            p.mkdir(parents=True, exist_ok=True)
            return p
        return winsys.known_folder(key)

    def open(self, target: str):
        """Открывает папку / сайт / системную страницу / программу. Возвращает текст результата или None."""
        n = norm(target)
        n = re.sub(r"^(мне|пожалуйста|папку|приложение|программу|сайт|игру|страницу)\s+", "", n)
        if not n:
            return None
        custom = {norm(k): v for k, v in (self.cfg.get("apps") or {}).items()}
        v, _ = match_stem(n, custom)
        if v:
            webbrowser.open(v) if str(v).startswith("http") else winsys.open_path(v)
            return f"Открыто: {target}"
        options = []
        for table, kind, bonus in ((FOLDERS, "folder", 0.5), (SITES, "site", 0), (BUILTIN, "builtin", 0), (ALIASES, "alias", 0.2)):
            v, k = match_stem(n, table)
            if v:
                options.append((k + bonus, kind, v))
        options.sort(key=lambda o: -o[0])
        for _, kind, v in options:
            if kind == "folder":
                winsys.open_path(str(self.folder_path(v)))
                return f"Открыта папка {target}"
            if kind == "site":
                webbrowser.open(v)
                return f"Открыт сайт {v}"
            if kind == "builtin":
                webbrowser.open(v[4:]) if v.startswith("url:") else winsys.open_path(v)
                return f"Открыто: {target}"
            break  # alias → ищем среди установленных
        found = self.find_installed(n)
        if found:
            self.launch(found[2])
            return f"Запущено: {found[1]}"
        s = n.replace(" точка ", ".").replace(" ", "")
        if re.fullmatch(r"[\w\-]+(\.[\w\-]+)+(/\S*)?", s):
            webbrowser.open(s if s.startswith("http") else "https://" + s)
            return f"Открыт сайт {s}"
        return None

    def close(self, name: str):
        n = norm(name)
        exes, _ = match_stem(n, PROC)
        exes = [e.lower() for e in (exes or [])]
        alias, _ = match_stem(n, ALIASES)
        cands = [c for c in {(alias or "").replace(" ", ""), translit(n).replace(" ", ""), n.replace(" ", "")} if c]
        if psutil is None:
            for e in exes:
                subprocess.run(["taskkill", "/im", e, "/f"], creationflags=NO_WINDOW, capture_output=True)
            return len(exes)
        killed = set()
        for p in psutil.process_iter(["name"]):
            pn = (p.info.get("name") or "").lower()
            base = pn[:-4] if pn.endswith(".exe") else pn
            if not base or base in PROTECTED:
                continue
            hit = pn in exes
            if not hit and not exes:
                hit = any((len(c) >= 4 and base.startswith(c)) or difflib.SequenceMatcher(None, c, base).ratio() >= 0.82
                          for c in cands)
            if hit:
                try:
                    p.terminate()
                    killed.add(base)
                except Exception:
                    pass
        return len(killed)

    def find_file(self, query: str, limit=5):
        q = norm(query)
        qt = translit(q)
        scored = []
        now = time.time()
        for f in self.files:
            stem = Path(f).stem.lower()
            s = 0.0
            for c in (q, qt):
                if not c:
                    continue
                if c == stem:
                    s = max(s, 1.0)
                elif c in stem:
                    s = max(s, 0.85)
                elif len(c) > 3:
                    s = max(s, difflib.SequenceMatcher(None, c, stem).ratio() * 0.9)
            if s >= 0.6:
                try:
                    age_days = (now - os.path.getmtime(f)) / 86400
                except OSError:
                    age_days = 999
                scored.append((s + max(0, 0.1 - age_days / 3650), f))
        scored.sort(reverse=True)
        return [f for _, f in scored[:limit]]
