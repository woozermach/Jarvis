# -*- coding: utf-8 -*-
"""Настройки Джарвиса (config.json) и пути."""
import json
import logging
import os
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_PATH = BASE / "config.json"
LOG_PATH = BASE / "jarvis.log"
IS_WIN = sys.platform.startswith("win")
NO_WINDOW = 0x08000000 if IS_WIN else 0

VOICES = {  # голоса Gemini Live (prebuilt)
    "Charon": "Харон — низкий, спокойный (по умолчанию)",
    "Orus": "Орус — уверенный, твёрдый",
    "Fenrir": "Фенрир — энергичный",
    "Iapetus": "Иапет — ясный, ровный",
    "Algenib": "Альгениб — с хрипотцой",
    "Rasalgethi": "Расальгети — информативный",
    "Puck": "Пак — бодрый",
    "Kore": "Кора — женский, твёрдый",
    "Aoede": "Аэда — женский, лёгкий",
    "Leda": "Леда — женский, молодой",
}

PERSONAS = {
    "butler": "Дворецкий — вежливый, с британской иронией, «сэр»",
    "friend": "Друг — неформально, на «ты», с юмором",
    "pro": "Профессионал — строго по делу, минимум слов",
    "tutor": "Репетитор — объясняет пошагово, наводит вопросами",
    "custom": "Свой — только мои инструкции",
}
TOOL_GROUPS = {
    "apps": ("Программы и окна", ["open_app", "close_app", "switch_window", "window_action", "list_windows"]),
    "keyboard": ("Клавиатура и ввод текста", ["press_keys", "type_text", "clipboard"]),
    "mouse": ("Клики мышью по экрану", ["click_on_screen", "scroll"]),
    "vision": ("Зрение (скриншоты, «вижу экран»)", ["look_at_screen", "take_screenshot", "watch_screen"]),
    "internet": ("Интернет и YouTube", ["open_website", "web_search", "search_internet", "youtube"]),
    "media": ("Звук, яркость, музыка", ["media_control", "volume", "brightness"]),
    "files": ("Поиск файлов", ["find_file"]),
    "info": ("Погода, валюты, система", ["get_weather", "exchange_rate", "system_status"]),
    "time": ("Таймеры и напоминания", ["set_timer", "set_reminder", "list_timers", "cancel_timer"]),
    "organizer": ("Задачи, заметки, память", ["tasks", "notes", "memory"]),
    "power": ("Питание и корзина", ["power", "empty_recycle_bin"]),
    "routines": ("Режимы и тихий режим", ["routine_save", "routine_run", "routine_list", "routine_delete", "quiet_mode"]),
    "gaming": ("Игры: клипы и Discord", ["game_clip", "discord"]),
    "update": ("Самообновление", ["jarvis_update"]),
}

DEFAULTS = {
    # ИИ
    "gemini_api_key": "",
    "live_model": "",            # пусто = выбрать автоматически
    "text_model": "",
    "tts_model": "",
    "voice": "Charon",
    "persona": "butler",
    "custom_instructions": "",
    "reply_length": "short",     # short | normal | detailed
    "reply_language": "auto",    # auto | ru | uk | en | sk
    # о пользователе
    "user_name": "",
    "city": "",
    "ui_language": "",           # en de fr es it pl cs sk uk ru; пусто — язык Windows
    "theme": "dark",             # system | light | dark
    "onboarding_done": False,
    "wake_word": "sayro",        # sayro | jarvis
    # активация
    "wake_engine": "auto",       # auto | openwakeword | google | off
    "wake_threshold": 0.5,       # уверенное срабатывание локальной модели
    "wake_verify_threshold": 0.002,  # «похоже» — тогда проверка распознаванием речи
    "hotkey": "ctrl+alt+j",
    "idle_timeout": 14,          # сек тишины до завершения разговора
    "vad_silence_ms": 650,       # пауза, после которой Джарвис начинает отвечать
    "headphones": False,         # в наушниках можно перебивать Джарвиса голосом
    "headphones_auto": True,     # определять гарнитуру по названию устройства
    # звук
    "mic_device": None,
    "speaker_device": None,
    "mic_gain": 1.0,
    "sounds": True,
    # окно и система
    "open_window_on_start": True,
    "autostart": False,
    "autostart_window": False,
    "accent": "#0A84FF",
    "show_system_panel": True,
    "show_weather_panel": True,
    "card_autoclose": 0,         # сек до автозакрытия карточек (0 — не закрывать)
    "confirm_dangerous": True,
    "tools_disabled": [],
    # проактивность
    "proactive": True,           # сам сообщать о важном
    "proactive_voice": True,     # голосом (иначе только уведомлением)
    "proactive_gpu_temp": 87,    # °C — предупредить о перегреве видеокарты
    "proactive_battery": 15,     # % — предупредить о разряде
    "proactive_disk_gb": 10,     # ГБ — мало места на диске
    "proactive_game_hours": 2.0, # ч — напомнить о перерыве в игре (0 — выкл)
    "proactive_night": True,     # мягко напомнить, если играет глубокой ночью
    "morning_briefing": True,    # брифинг при первом разговоре утром
    # игры и экран
    "watch_interval": 2.0,       # сек между кадрами в режиме «вижу экран»
    "watch_idle_timeout": 90,    # сек тишины до конца разговора в этом режиме
    "clip_method": "auto",       # auto | nvidia | gamebar
    "discord_mute_key": "",      # глобальные горячие клавиши Discord
    "discord_deafen_key": "",
    # телефон (Telegram)
    "telegram_enabled": False,
    "telegram_token": "",
    "telegram_chat_id": 0,
    "telegram_notify": True,     # присылать таймеры и предупреждения
    # лицензия Pro
    "license_key": "",
    # обновления
    "update_repo": "woozermach/Jarvis",
    "update_branch": "main",
    "update_auto_check": True,
    "port": 8765,
    "apps": {},
}

# тип и пределы для значений, приходящих из интерфейса
SCHEMA = {
    "voice": ("choice", list(VOICES)), "persona": ("choice", list(PERSONAS)),
    "reply_length": ("choice", ["short", "normal", "detailed"]),
    "reply_language": ("choice", ["auto", "en", "de", "fr", "es", "it", "pl", "cs", "sk", "uk", "ru"]),
    "wake_engine": ("choice", ["auto", "openwakeword", "google", "off"]),
    "ui_language": ("choice", ["en", "de", "fr", "es", "it", "pl", "cs", "sk", "uk", "ru"]),
    "theme": ("choice", ["system", "light", "dark"]), "onboarding_done": ("bool",),
    "wake_word": ("choice", ["sayro", "jarvis"]),
    "custom_instructions": ("str", 4000), "user_name": ("str", 60), "city": ("str", 80), "hotkey": ("str", 40),
    "live_model": ("str", 80), "text_model": ("str", 80), "tts_model": ("str", 80), "accent": ("str", 9),
    "wake_threshold": ("float", 0.1, 0.95), "wake_verify_threshold": ("float", 0.0, 0.3),
    "idle_timeout": ("int", 4, 120), "vad_silence_ms": ("int", 250, 2500), "mic_gain": ("float", 0.3, 6.0),
    "port": ("int", 1024, 65000), "card_autoclose": ("int", 0, 600),
    "headphones": ("bool",), "headphones_auto": ("bool",), "sounds": ("bool",), "open_window_on_start": ("bool",), "autostart": ("bool",),
    "autostart_window": ("bool",), "show_system_panel": ("bool",), "show_weather_panel": ("bool",),
    "confirm_dangerous": ("bool",),
    "mic_device": ("device",), "speaker_device": ("device",),
    "tools_disabled": ("list",), "apps": ("dict",),
    "proactive": ("bool",), "proactive_voice": ("bool",), "proactive_night": ("bool",), "morning_briefing": ("bool",),
    "proactive_gpu_temp": ("int", 60, 105), "proactive_battery": ("int", 0, 60), "proactive_disk_gb": ("int", 0, 200),
    "proactive_game_hours": ("float", 0, 12),
    "watch_interval": ("float", 0.5, 10), "watch_idle_timeout": ("int", 15, 600),
    "clip_method": ("choice", ["auto", "nvidia", "gamebar"]),
    "discord_mute_key": ("str", 40), "discord_deafen_key": ("str", 40),
    "license_key": ("str", 800), "update_repo": ("str", 100), "update_branch": ("str", 60), "update_auto_check": ("bool",),
    "telegram_enabled": ("bool",), "telegram_notify": ("bool",), "telegram_token": ("str", 120), "telegram_chat_id": ("int", 0, 10**15),
}


def coerce(key, value):
    """Приводит значение из интерфейса к нужному типу. Бросает ValueError, если нельзя."""
    sch = SCHEMA.get(key)
    if not sch:
        raise ValueError(f"неизвестная настройка {key}")
    kind = sch[0]
    if kind == "choice":
        if value not in sch[1]:
            raise ValueError(f"{key}: недопустимое значение")
        return value
    if kind == "str":
        return str(value or "")[: sch[1]].strip()
    if kind == "float":
        return max(sch[1], min(sch[2], float(value)))
    if kind == "int":
        return int(max(sch[1], min(sch[2], int(float(value)))))
    if kind == "bool":
        return bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "да", "on")
    if kind == "device":
        return None if value in (None, "", "null") else int(value)
    if kind == "list":
        return [str(x) for x in (value or [])]
    if kind == "dict":
        return {str(k).strip(): str(v).strip() for k, v in (value or {}).items() if str(k).strip() and str(v).strip()}
    return value


def windows_language():
    """Язык интерфейса Windows → один из поддерживаемых (иначе английский)."""
    supported = {"en", "de", "fr", "es", "it", "pl", "cs", "sk", "uk", "ru"}
    try:
        if IS_WIN:
            import ctypes
            import locale
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = (locale.windows_locale.get(lcid) or "en_US").split("_")[0].lower()
        else:
            import locale
            code = (locale.getlocale()[0] or "en").split("_")[0].lower()
        return code if code in supported else "en"
    except Exception:
        return "en"


_lock = threading.Lock()


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        existed = CONFIG_PATH.exists()
        if existed:
            try:
                old = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for k, v in old.items():
                    if k in DEFAULTS:
                        self[k] = v
            except Exception as e:
                logging.getLogger("jarvis").error("config.json повреждён: %s", e)
        if self.get("voice") not in VOICES:  # миграция с v1 (голоса edge-tts)
            self["voice"] = "Charon"
        if not self.get("ui_language"):
            # старые установки (до 3.0) были на русском; новые — язык Windows
            self["ui_language"] = "ru" if existed and self.get("gemini_api_key") else windows_language()
            if existed and self.get("gemini_api_key"):
                self["onboarding_done"] = True
        if (self.get("accent") or "").lower() == "#4fe3ff":
            self["accent"] = DEFAULTS["accent"]
        if self.get("update_repo") in ("woozermach/jarvis-assistant", ""):  # первое имя репозитория
            self["update_repo"] = DEFAULTS["update_repo"]
        if not self.get("gemini_api_key") and os.environ.get("GEMINI_API_KEY"):
            self["gemini_api_key"] = os.environ["GEMINI_API_KEY"]
        self.save()

    def save(self):
        with _lock:
            try:
                CONFIG_PATH.write_text(json.dumps(dict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logging.getLogger("jarvis").error("Не удалось сохранить config.json: %s", e)

    def public(self):
        d = dict(self)
        k = d.get("gemini_api_key", "")
        d["gemini_api_key"] = (k[:4] + "…" + k[-4:]) if len(k) > 10 else ("" if not k else "…")
        d["has_key"] = bool(k)
        t = d.get("telegram_token", "")
        d["telegram_token"] = (t[:5] + "…" + t[-3:]) if len(t) > 10 else ""
        d["has_tg_token"] = bool(t)
        lk = d.get("license_key", "")
        d["license_key"] = (lk[:8] + "…" + lk[-4:]) if len(lk) > 14 else ("…" if lk else "")
        return d


def setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return
    from logging.handlers import RotatingFileHandler
    h = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(h)
    root.setLevel(logging.INFO)
    if sys.stdout and "--console" in sys.argv:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(sh)
    for noisy in ("aiohttp.access", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
