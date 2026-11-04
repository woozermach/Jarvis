# -*- coding: utf-8 -*-
"""Перевод сообщений ядра (тосты, уведомления, Telegram) на язык интерфейса.

Код пишет сообщения по-русски, как раньше; здесь шаблон → ключ → перевод из ui/i18n/<lang>.json ("py.<ключ>").
Английский источник — PY ниже (его забирает tools/build_i18n.py в en.json)."""
import json
import logging
import re

from .config import BASE

log = logging.getLogger("jarvis.i18n")

# (русский шаблон, ключ, английский)
PY = [
    ("История разговоров очищена", "hist_cleared", "Conversation history cleared"),
    ("Лимит Gemini Live исчерпан — попробуйте позже", "live_quota", "Gemini Live limit reached — try again later"),
    ("Нужен ключ Gemini — откройте настройки ⚙", "need_key", "A Gemini key is needed — open Settings"),
    ("Обновление: {x}", "upd_err", "Update: {x}"),
    ("Отправил тестовое сообщение в Telegram", "tg_test_sent", "Test message sent to Telegram"),
    ("Перезапуск…", "restarting", "Restarting…"),
    ("Режим не сохранён: {x}", "rt_not_saved", "Routine not saved: {x}"),
    ("Сначала привяжите бота (код в настройках)", "tg_pair_first", "Link the bot first (code in Settings)"),
    ("⭐ Pro активирован: {x}", "pro_on_name", "⭐ Pro activated: {x}"),
    ("⭐ Pro активирован", "pro_on", "⭐ Pro activated"),
    ("Ключ удалён — бесплатная версия", "key_removed", "Key removed — free version"),
    ("Ключ не принят: {x}", "key_rejected", "Key not accepted: {x}"),
    ("⭐ «Вижу экран» — функция Pro (Настройки → Pro)", "watch_pro", "⭐ Seeing your screen is a Pro feature (Settings → Pro)"),
    ("⭐ Это функция Pro — Настройки → Pro", "pro_only", "⭐ This is a Pro feature — Settings → Pro"),
    ("🎧 Discord: микрофон", "discord_mic", "🎧 Discord: microphone"),
    ("🎧 Discord: звук", "discord_sound", "🎧 Discord: sound"),
    ("🎬 Клип: NVIDIA Instant Replay", "clip_nv", "🎬 Clip: NVIDIA Instant Replay"),
    ("🎬 Клип: Xbox Game Bar", "clip_gb", "🎬 Clip: Xbox Game Bar"),
    ("👁 Смотрю на экран…", "looking", "👁 Looking at the screen…"),
    ("📝 Записал", "noted", "📝 Noted"),
    ("📱 Telegram привязан", "tg_linked", "📱 Telegram linked"),
    ("📸 Скриншот сохранён", "shot_saved", "📸 Screenshot saved"),
    ("🔔 Тихий режим выключен", "quiet_off", "🔔 Quiet mode off"),
    ("🔕 Тихий режим до {x}", "quiet_until", "🔕 Quiet mode until {x}"),
    ("🗑 Корзина очищена", "bin_emptied", "🗑 Recycle bin emptied"),
    ("🧠 Запомнил", "remembered", "🧠 Remembered"),
    ("Погода: {x}", "weather_err", "Weather: {x}"),
    ("⏱ Таймер {x}", "timer_set", "⏱ Timer {x}"),
    ("▶ YouTube: {x}", "yt", "▶ YouTube: {x}"),
    ("☀ Яркость {x}%", "brightness", "☀ Brightness {x}%"),
    ("🔊 Громкость {x}%", "volume", "🔊 Volume {x}%"),
    ("⚙ «{x}»: выполнено {y}", "rt_done", "⚙ “{x}”: {y} done"),
    ("⚙ Режим «{x}» сохранён ({y} шагов)", "rt_saved", "⚙ Routine “{x}” saved ({y} steps)"),
    ("⚙ Режим «{x}»", "rt_run", "⚙ Routine “{x}”"),
    ("✓ Задача: {x}", "task_added", "✓ Task: {x}"),
    ("✕ Закрыто: {x}", "closed_app", "✕ Closed: {x}"),
    ("⬆ Доступна новая версия {x} — кнопка вверху", "upd_avail", "⬆ Version {x} is available — button at the top"),
    ("🌐 Ищу: {x}", "searching", "🌐 Searching: {x}"),
    ("🔥 Видеокарта {x}°C", "gpu_hot", "🔥 GPU {x}°C"),
    ("🪫 Батарея {x}%", "bat_crit", "🪫 Battery {x}%"),
    ("🔋 Батарея {x}%", "bat_low", "🔋 Battery {x}%"),
    ("💾 Мало места: {x} ГБ", "disk_low", "💾 Low disk space: {x} GB"),
    ("🎮 Играете {x} ч {y} мин", "game_long", "🎮 Gaming for {x} h {y} min"),
    ("🌙 Уже глубокая ночь", "night", "🌙 It's very late"),
    ("Обновлено до версии {x} ✓", "upd_ok", "Updated to version {x} ✓"),
    ("Настройки сохранены — {x}", "saved_note", "Settings saved — {x}"),
    ("Настройки сохранены", "saved", "Settings saved"),
    ("Ничего не изменилось", "nothing_changed", "Nothing changed"),
    ("часть изменений применится со следующего разговора", "next_conv", "some changes apply from the next conversation"),
    ("Таймер", "k_timer", "Timer"), ("Напоминание", "k_reminder", "Reminder"), ("Будильник", "k_alarm", "Alarm"),
    ("время вышло", "time_up", "time's up"),
    ("Время вышло", "time_up_cap", "Time's up"),
]
# ключи без русского шаблона (используются через ui())
PY_ONLY = {
    "tray_open": "Open {name}", "tray_quit": "Quit", "tg_test_msg": "Connection check: your PC is online.",
    "tg_help": ("I'm {name} — your PC, on the line.\n\nJust write (or send a voice message) what to do: “play music”, “battery level?”, "
                "“set a 20-minute timer”, “what's on my screen?”, “shut down the PC in an hour”, “start the gaming routine”.\n\n"
                "Commands:\n/screen — screenshot\n/status — PC status\n/quiet — quiet mode for an hour\n/update — update {name}\n"
                "/clear — forget this chat\n/help — this help"),
    "tg_linked_msg": "✅ Linked{who}! From now on I answer only you.",
    "tg_hello": "Hi! To link me, send the code from {name}'s settings (Phone section).",
    "tg_other": "This {name} is linked to another account.",
    "tg_cleared": "Chat forgotten.", "tg_quiet": "Quiet mode for an hour.", "tg_latest": "Version {v} is the latest.",
    "tg_updating": "Installing version {v}, back in half a minute…", "tg_kinds": "I understand text, voice messages and photos.",
}

_rx = []
for ru, key, _en in PY:
    pat = re.escape(ru).replace(r"\{x\}", "(?P<x>.+?)").replace(r"\{y\}", "(?P<y>.+?)")
    _rx.append((re.compile("^" + pat + "$", re.S), key))
_cache = {}


def _dict(lang):
    if lang not in _cache:
        try:
            _cache[lang] = json.loads((BASE / "ui" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        except Exception:
            _cache[lang] = {}
    return _cache[lang]


def tr(text, lang):
    """Русское сообщение ядра → язык интерфейса (если шаблон известен), иначе как есть."""
    if not text or lang == "ru":
        return text
    for rx, key in _rx:
        m = rx.match(text)
        if m:
            d = _dict(lang)
            out = d.get("py." + key) or _dict("en").get("py." + key) or next(e for _, k, e in PY if k == key)
            for g, v in m.groupdict().items():
                out = out.replace("{" + g + "}", v)
            return out
    return text


def ui(key, lang, **kw):
    """Строка интерфейса по ключу (для Telegram и уведомлений Windows)."""
    s = _dict(lang).get(key) or _dict("en").get(key) or key
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s
