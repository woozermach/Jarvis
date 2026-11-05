# -*- coding: utf-8 -*-
"""Инструменты Джарвиса: описания для Gemini + реализация.
Каждая функция возвращает строку или dict — это уходит модели как результат вызова."""
import ast
import datetime as dt
import io
import logging
import operator
import os
import re
import time
import urllib.parse
import webbrowser

import requests

from . import winsys
from .config import IS_WIN
from .util import MONTHS_GEN, WEEKDAYS, duration_words, norm
from .websearch import youtube_first

log = logging.getLogger("jarvis.tools")

WEATHER_CODES = {
    0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "туман с изморозью",
    51: "лёгкая морось", 53: "морось", 55: "сильная морось", 56: "ледяная морось", 57: "ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь", 66: "ледяной дождь", 67: "ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снегопад", 77: "снежная крупа",
    80: "небольшой ливень", 81: "ливень", 82: "сильный ливень", 85: "снегопад", 86: "сильный снегопад",
    95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}
WEATHER_ICON = {0: "sun", 1: "sun", 2: "cloud-sun", 3: "cloud", 45: "fog", 48: "fog"}
for c in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
    WEATHER_ICON[c] = "rain"
for c in (71, 73, 75, 77, 85, 86):
    WEATHER_ICON[c] = "snow"
for c in (95, 96, 99):
    WEATHER_ICON[c] = "storm"

CURRENCY = {"евро": "EUR", "доллар": "USD", "гривн": "UAH", "рубл": "RUB", "злот": "PLN", "чешск": "CZK",
            "фунт": "GBP", "франк": "CHF", "юан": "CNY", "иен": "JPY", "йен": "JPY", "форинт": "HUF", "лир": "TRY"}


def S(desc, **kw):
    return {"type": "string", "description": desc, **kw}


def I(desc):
    return {"type": "integer", "description": desc}


def B(desc):
    return {"type": "boolean", "description": desc}


def OBJ(props, req=()):
    return {"type": "object", "properties": props, "required": list(req)}


def ARR(items, desc=""):
    return {"type": "array", "items": items, "description": desc}


# эти функции нельзя вкладывать в режимы (рекурсия, завершение разговора, опасное)
NOT_IN_ROUTINE = {"routine_save", "routine_run", "routine_delete", "routine_list", "end_conversation", "power",
                  "empty_recycle_bin", "set_preference", "watch_screen"}


class Toolbox:
    def __init__(self, ctx):
        self.ctx = ctx  # Assistant
        self.cfg = ctx.cfg
        self.apps = ctx.apps
        self.store = ctx.store
        self.gemini = ctx.gemini
        self._weather_cache = {}

    # ════════════════════════ описания для модели ════════════════════════
    def disabled(self):
        from .config import TOOL_GROUPS
        off = set()
        for g in self.cfg.get("tools_disabled") or []:
            off |= set(TOOL_GROUPS.get(g, ("", []))[1])
        return off

    def declarations(self):
        off = self.disabled()
        return [d for d in self._declarations() if d["name"] not in off]

    def _declarations(self):
        return [
            {"name": "open_app", "description": "Открыть программу, игру, системную настройку Windows, папку или сайт по названию "
                                                "(«телеграм», «стим», «калда», «настройки блютуз», «загрузки», «ютуб»).",
             "parameters": OBJ({"name": S("название как сказал пользователь")}, ["name"])},
            {"name": "close_app", "description": "Закрыть (завершить) запущенную программу.",
             "parameters": OBJ({"name": S("название программы")}, ["name"])},
            {"name": "switch_window", "description": "Переключиться на уже открытое окно по части заголовка.",
             "parameters": OBJ({"title": S("часть заголовка окна или название программы")}, ["title"])},
            {"name": "window_action", "description": "Действие с окнами.",
             "parameters": OBJ({"action": S("что сделать", enum=["show_desktop", "maximize", "minimize", "close_active",
                                                                  "next_window", "snap_left", "snap_right", "task_view", "fullscreen"])}, ["action"])},
            {"name": "list_windows", "description": "Список открытых окон."},
            {"name": "press_keys", "description": "Нажать сочетание клавиш в активном окне, например ctrl+s, ctrl+shift+t, alt+tab, f5, win+shift+s.",
             "parameters": OBJ({"keys": S("сочетание через +"), "times": I("сколько раз, по умолчанию 1")}, ["keys"])},
            {"name": "type_text", "description": "Напечатать текст в активное окно (поле ввода, документ, чат).",
             "parameters": OBJ({"text": S("текст"), "press_enter": B("нажать Enter после")}, ["text"])},
            {"name": "clipboard", "description": "Прочитать или записать буфер обмена.",
             "parameters": OBJ({"action": S("read или write", enum=["read", "write"]), "text": S("текст для записи")}, ["action"])},
            {"name": "open_website", "description": "Открыть сайт по адресу или названию.",
             "parameters": OBJ({"site": S("домен или название")}, ["site"])},
            {"name": "web_search", "description": "Открыть страницу поиска Google в браузере (когда пользователь хочет посмотреть сам).",
             "parameters": OBJ({"query": S("запрос")}, ["query"])},
            {"name": "search_internet", "description": "Найти в интернете актуальную информацию и вернуть ответ: новости, курсы, "
                                                       "результаты матчей, цены, расписания, факты после 2025 года. Используй для любых вопросов о текущих событиях.",
             "parameters": OBJ({"query": S("поисковый запрос")}, ["query"])},
            {"name": "youtube", "description": "Включить видео или музыку на YouTube (play — сразу первое видео) или открыть поиск (search).",
             "parameters": OBJ({"query": S("что найти"), "mode": S("play или search", enum=["play", "search"])}, ["query"])},
            {"name": "media_control", "description": "Управление воспроизведением музыки/видео в любом плеере.",
             "parameters": OBJ({"action": S("действие", enum=["play_pause", "next", "previous", "stop"])}, ["action"])},
            {"name": "volume", "description": "Громкость системы: узнать, установить, прибавить/убавить, выключить/включить звук.",
             "parameters": OBJ({"action": S("действие", enum=["get", "set", "up", "down", "mute", "unmute"]),
                                "level": I("уровень 0–100 для set или шаг для up/down")}, ["action"])},
            {"name": "brightness", "description": "Яркость экрана ноутбука: узнать или установить 0–100.",
             "parameters": OBJ({"level": I("новый уровень; не указывай, чтобы узнать текущий")})},
            {"name": "take_screenshot", "description": "Сохранить скриншот экрана в файл."},
            {"name": "click_on_screen", "description": "Нажать мышью на элемент интерфейса, который видно на экране: кнопку, ссылку, "
                                                       "вкладку, пункт меню, иконку, поле ввода. Опиши элемент словами, как он выглядит или подписан.",
             "parameters": OBJ({"target": S("что нажать, например «кнопка Играть в Steam» или «поле поиска»"),
                                "button": S("кнопка мыши", enum=["left", "right"]), "double": B("двойной клик"),
                                "confirmed": B("пользователь подтвердил (для кнопок покупки/оплаты/удаления)")}, ["target"])},
            {"name": "scroll", "description": "Прокрутить колесом мыши в активном окне.",
             "parameters": OBJ({"direction": S("up или down", enum=["up", "down"]), "amount": I("сколько щелчков, по умолчанию 5")}, ["direction"])},
            {"name": "look_at_screen", "description": "Посмотреть на экран пользователя и ответить на вопрос о том, что там видно "
                                                     "(ошибка, текст, код, игра, окно). Используй, когда спрашивают «что на экране», «помоги с этим», «прочитай».",
             "parameters": OBJ({"question": S("что нужно понять на экране")}, ["question"])},
            {"name": "find_file", "description": "Найти файл в папках пользователя (рабочий стол, документы, загрузки, изображения, видео, музыка) и при желании открыть.",
             "parameters": OBJ({"query": S("часть имени файла"), "open": B("открыть лучший результат")}, ["query"])},
            {"name": "get_weather", "description": "Погода: сейчас и прогноз на несколько дней.",
             "parameters": OBJ({"city": S("город; пусто — город пользователя"), "days": I("дней прогноза 1–7")})},
            {"name": "exchange_rate", "description": "Курс валют и конвертация (ISO-коды: EUR, USD, UAH, RUB, PLN, CZK, GBP…).",
             "parameters": OBJ({"base": S("из какой валюты"), "target": S("в какую"), "amount": {"type": "number", "description": "сумма"}}, ["base", "target"])},
            {"name": "system_status", "description": "Состояние ноутбука: процессор, видеокарта и её температура, память, диск, батарея, сеть, "
                                                     "время работы, самые тяжёлые программы."},
            {"name": "set_timer", "description": "Таймер или напоминание через заданное время.",
             "parameters": OBJ({"seconds": I("через сколько секунд"), "label": S("о чём напомнить")}, ["seconds"])},
            {"name": "set_reminder", "description": "Напоминание или будильник на конкретное время/дату.",
             "parameters": OBJ({"when": S("локальное время ISO, например 2026-11-04T07:30 или просто 07:30"),
                                "label": S("о чём напомнить"), "alarm": B("это будильник (громкий сигнал)")}, ["when"])},
            {"name": "list_timers", "description": "Список активных таймеров и напоминаний."},
            {"name": "cancel_timer", "description": "Отменить таймер/напоминание по слову из названия (или все: all=true).",
             "parameters": OBJ({"label": S("часть названия"), "all": B("отменить все")})},
            {"name": "tasks", "description": "Список дел: добавить, показать, отметить выполненным, удалить, очистить выполненные.",
             "parameters": OBJ({"action": S("действие", enum=["add", "list", "done", "undo", "delete", "clear_done"]),
                                "text": S("текст задачи или его часть")}, ["action"])},
            {"name": "notes", "description": "Заметки: записать или прочитать последние.",
             "parameters": OBJ({"action": S("add или list", enum=["add", "list"]), "text": S("текст заметки")}, ["action"])},
            {"name": "memory", "description": "Долговременная память о пользователе. remember — когда просят запомнить факт "
                                              "(имя, предпочтения, расписание); forget — забыть; list — что помнишь.",
             "parameters": OBJ({"action": S("действие", enum=["remember", "forget", "list"]), "fact": S("факт")}, ["action"])},
            {"name": "display", "description": "Показать на экране HUD карточку с длинным содержимым (рецепт, список, код, таблица, "
                                               "план, перевод). Голосом при этом скажи только суть.",
             "parameters": OBJ({"title": S("заголовок"), "content": S("содержимое, можно markdown")}, ["title", "content"])},
            {"name": "close_display", "description": "Закрыть всплывающее окно на экране Джарвиса: карточку с результатами поиска или "
                                                     "display, окно напоминания, настройки. Вызывай, когда пользователь говорит «закрой», «убери», "
                                                     "«понял», «спасибо, закрой», а карточка открыта. НЕ путай с window_action.",
             "parameters": OBJ({"what": S("что закрыть", enum=["card", "alert", "settings", "all"])})},
            {"name": "hud_window", "description": "Окно самого Джарвиса: показать (развернуть поверх) или свернуть.",
             "parameters": OBJ({"action": S("show или minimize", enum=["show", "minimize"])}, ["action"])},
            {"name": "calculate", "description": "Точно посчитать математическое выражение (+ - * / ** % sqrt sin cos log и т.п.).",
             "parameters": OBJ({"expression": S("выражение на Python, например (125*0.2)+sqrt(16)")}, ["expression"])},
            {"name": "now", "description": "Точные текущие дата и время."},
            {"name": "power", "description": "Питание: lock, sleep, shutdown, restart, cancel_shutdown. Для shutdown/restart сначала спроси "
                                             "пользователя и вызывай с confirmed=true только после явного «да».",
             "parameters": OBJ({"action": S("действие", enum=["lock", "sleep", "shutdown", "restart", "cancel_shutdown"]),
                                "confirmed": B("пользователь подтвердил")}, ["action"])},
            {"name": "empty_recycle_bin", "description": "Очистить корзину. Сначала спроси подтверждение, вызывай с confirmed=true.",
             "parameters": OBJ({"confirmed": B("пользователь подтвердил")}, ["confirmed"])},
            {"name": "set_preference", "description": "Изменить настройку Джарвиса: user_name (как обращаться), city (город для погоды), "
                                                      "voice (голос: Charon, Orus, Fenrir, Iapetus, Algenib, Puck, Kore, Aoede, Leda), headphones (true/false).",
             "parameters": OBJ({"key": S("настройка", enum=["user_name", "city", "voice", "headphones"]), "value": S("значение")}, ["key", "value"])},
            {"name": "routine_save", "description": "Создать или перезаписать РЕЖИМ — именованный набор действий, который потом "
                                                    "запускается одной фразой («включи игровой режим»). Переведи слова пользователя в шаги-вызовы других функций, "
                                                    "ровно то, что он перечислил. Паузы между шагами Джарвис делает сам; шаг wait добавляй, только если "
                                                    "пользователь сам попросил подождать.",
             "parameters": OBJ({"name": S("название режима, например «Игровой»"),
                                "description": S("кратко, что делает режим"),
                                "steps": ARR(OBJ({"tool": S("имя функции, например open_app, volume, quiet_mode, youtube, wait"),
                                                  "args_json": S("аргументы этой функции в виде JSON-строки, например {\"name\": \"steam\"}")},
                                                 ["tool"]), "шаги по порядку")}, ["name", "steps"])},
            {"name": "routine_run", "description": "Запустить сохранённый режим по названию («включи режим учёбы», «игровой режим»).",
             "parameters": OBJ({"name": S("название режима")}, ["name"])},
            {"name": "routine_list", "description": "Список сохранённых режимов и их шагов."},
            {"name": "routine_delete", "description": "Удалить режим по названию.",
             "parameters": OBJ({"name": S("название режима")}, ["name"])},
            {"name": "quiet_mode", "description": "Тихий режим: Джарвис не заговаривает сам (предупреждения только значком). "
                                                  "minutes — на сколько минут; off=true — выключить тихий режим.",
             "parameters": OBJ({"minutes": I("на сколько минут, по умолчанию 60"), "off": B("выключить")})},
            {"name": "watch_screen", "description": "Режим «вижу экран»: постоянно получать кадры экрана во время разговора, чтобы "
                                                    "комментировать игру, помогать с задачей, кодом или текстом в реальном времени. "
                                                    "Включай, когда просят «смотри на экран», «следи за игрой», «помогай, я решаю задачу». "
                                                    "После включения кадры приходят сами — отвечай по ним.",
             "parameters": OBJ({"on": B("true — включить, false — выключить")}, ["on"])},
            {"name": "game_clip", "description": "Сохранить клип последних моментов игры (NVIDIA Instant Replay или Xbox Game Bar), "
                                                 "когда говорят «сохрани момент», «клипни», «запиши это»."},
            {"name": "discord", "description": "Discord: выключить/включить микрофон (mute) или звук (deafen).",
             "parameters": OBJ({"action": S("mute или deafen", enum=["mute", "deafen"])}, ["action"])},
            {"name": "jarvis_update", "description": "Обновления самого Джарвиса: check — проверить, есть ли новая версия (и что в ней нового); "
                                                   "install — установить (Джарвис перезапустится на ~20 секунд). Перед install спроси подтверждение.",
             "parameters": OBJ({"action": S("check или install", enum=["check", "install"]), "confirmed": B("пользователь подтвердил установку")}, ["action"])},
            {"name": "end_conversation", "description": "Завершить разговор и вернуться в режим ожидания, когда пользователь прощается или говорит, что больше ничего не нужно."},
        ]

    # ════════════════════════ диспетчер ════════════════════════
    def call(self, name, args):
        if name in self.disabled():
            return {"error": "эта возможность отключена в настройках Джарвиса"}
        from .license import PRO_TOOLS
        if name in PRO_TOOLS and not getattr(self.ctx, "pro", True):
            self.ctx.toast("⭐ Это функция Pro — Настройки → Pro")
            return {"error": "pro_only", "say": "Это возможность Pro-версии. Коротко скажи, что её можно включить в настройках, "
                                                "раздел Pro, и не пытайся сделать то же другими функциями."}
        fn = getattr(self, "t_" + (name or ""), None)
        if fn is None:
            return {"error": f"нет функции {name}"}
        try:
            res = fn(**(args or {}))
            return res if res not in (None, "") else {"result": "готово"}
        except TypeError as e:
            log.exception("args %s", name)
            return {"error": f"неверные параметры: {e}"}
        except Exception as e:
            log.exception("tool %s", name)
            return {"error": str(e)[:300]}

    # ════════════════════════ программы и окна ════════════════════════
    def t_open_app(self, name):
        r = self.apps.open(name)
        if r:
            self.ctx.toast("▶ " + r)
            return r
        return {"error": f"не нашёл «{name}». Можно добавить путь в config.json → apps, или уточни название."}

    def t_close_app(self, name):
        n = self.apps.close(name)
        if n:
            self.ctx.toast(f"✕ Закрыто: {name}")
            return f"закрыто процессов: {n}"
        return {"error": f"не нашёл запущенного «{name}»"}

    def t_switch_window(self, title):
        t = winsys.focus_window(title)
        return f"переключено на «{t}»" if t else {"error": "такого окна не нашёл", "windows": [w for _, w in winsys.list_windows()][:15]}

    def t_list_windows(self):
        return {"windows": [w for _, w in winsys.list_windows()][:25]}

    def t_window_action(self, action):
        combos = {"show_desktop": "win+d", "maximize": "win+up", "minimize": "win+down", "close_active": "alt+f4",
                  "next_window": "alt+tab", "snap_left": "win+left", "snap_right": "win+right", "task_view": "win+tab",
                  "fullscreen": "f11"}
        if action not in combos:
            return {"error": "неизвестное действие"}
        if action == "close_active":
            title = winsys.foreground_title()
            from .brand import is_own_window
            if is_own_window(title):
                return {"error": "активно окно самого Джарвиса — не закрываю"}
        winsys.hotkey(combos[action])
        return "готово"

    def t_press_keys(self, keys, times=1):
        k = keys.lower().replace(" ", "")
        if k in ("ctrl+alt+delete", "ctrl+alt+del"):
            return {"error": "это сочетание нельзя нажать программно"}
        for _ in range(max(1, min(20, int(times or 1)))):
            winsys.hotkey(k)
            time.sleep(0.05)
        return f"нажато {keys}"

    def t_type_text(self, text, press_enter=False):
        winsys.type_text(text)
        if press_enter:
            time.sleep(0.15)
            winsys.hotkey("enter")
        return f"напечатано {len(text)} символов в «{winsys.foreground_title()[:60]}»"

    def t_clipboard(self, action, text=""):
        if action == "write":
            winsys.clipboard_set(text)
            return "скопировано в буфер"
        t = winsys.clipboard_get()
        return {"clipboard": t[:6000] if t else "(буфер пуст или там не текст)"}

    # ════════════════════════ интернет ════════════════════════
    def t_open_website(self, site):
        r = self.apps.open(site)
        if r and "сайт" in r:
            return r
        s = norm(site).replace(" точка ", ".").replace(" ", "")
        if "." in s:
            webbrowser.open(s if s.startswith("http") else "https://" + s)
            return f"открыт {s}"
        return self.t_web_search(site)

    def t_web_search(self, query):
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
        self.ctx.toast(f"🔎 {query}")
        return "открыт поиск Google"

    def t_search_internet(self, query):
        self.ctx.toast(f"🌐 Ищу: {query}")
        res = self.gemini.search(query)
        if res.get("sources"):
            res["note"] = "результаты показаны карточкой на экране; закрыть — close_display"
            self.ctx.ui_card("Поиск: " + query, res["answer"] + "\n\n" +
                             "\n".join(f"- [{s['title']}]({s['url']})" for s in res["sources"]), kind="search")
        return res

    def t_youtube(self, query, mode="play"):
        if mode == "search":
            webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query))
            return "открыт поиск YouTube"
        vid, title = youtube_first(query)
        if vid:
            webbrowser.open(f"https://www.youtube.com/watch?v={vid}")
            self.ctx.toast(f"▶ YouTube: {title or query}")
            return f"включено видео: {title or query}"
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query))
        return "не удалось определить первое видео, открыл поиск"

    # ════════════════════════ звук, экран ════════════════════════
    def t_media_control(self, action):
        key = {"play_pause": "media_play_pause", "next": "media_next", "previous": "media_prev", "stop": "media_stop"}[action]
        winsys.tap(winsys.VK[key])
        return "готово"

    def t_volume(self, action, level=None):
        if action == "get":
            v, m = winsys.get_volume()
            return {"volume": v, "muted": m} if v is not None else {"error": "не удалось узнать громкость"}
        if action == "set":
            v = winsys.set_volume(int(level if level is not None else 50))
            self.ctx.toast(f"🔊 Громкость {v}%")
            return {"volume": v}
        if action in ("up", "down"):
            step = int(level or 10)
            v = winsys.change_volume(step if action == "up" else -step)
            self.ctx.toast(f"🔊 Громкость {v}%" if v is not None else "🔊")
            return {"volume": v}
        m = winsys.set_mute(action == "mute")
        return {"muted": m if m is not None else action == "mute"}

    def t_brightness(self, level=None):
        if level is None:
            return {"brightness": winsys.get_brightness()}
        v = winsys.set_brightness(int(level))
        self.ctx.toast(f"☀ Яркость {v}%")
        return {"brightness": v}

    def _grab(self, max_side=None):
        from PIL import ImageGrab
        self.ctx.hide_window_for_capture(True)
        try:
            time.sleep(0.25)
            img = ImageGrab.grab(all_screens=False)
        finally:
            self.ctx.hide_window_for_capture(False)
        if max_side:
            img.thumbnail((max_side, max_side))
        return img

    def t_take_screenshot(self):
        img = self._grab()
        folder = self.apps.folder_path("SCREENSHOTS")
        path = folder / f"screenshot_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.png"
        img.save(path)
        self.ctx.toast("📸 Скриншот сохранён")
        return f"сохранено: {path}"

    def t_look_at_screen(self, question="Что на экране?"):
        img = self._grab(1600)
        b = io.BytesIO()
        img.convert("RGB").save(b, "JPEG", quality=82)
        self.ctx.toast("👁 Смотрю на экран…")
        return {"what_i_see": self.gemini.vision(b.getvalue(), question)}

    DANGER_WORDS = ("купить", "оплат", "заплат", "удалить", "удали", "delete", "buy", "pay", "purchase", "перевест",
                    "отправить деньги", "подтвердить покупку", "оформить заказ")

    def _locate(self, img, target, hint=""):
        """Спрашивает зрение Gemini, где элемент. Возвращает (box[ymin,xmin,ymax,xmax] 0–1000, label) или (None, why)."""
        import base64
        import json as _json
        b = io.BytesIO()
        img.convert("RGB").save(b, "JPEG", quality=88)
        prompt = (f"Это скриншот экрана Windows{hint}. Найди элемент интерфейса: «{target}». "
                  "Верни ТОЛЬКО JSON-массив: [{\"box_2d\": [ymin, xmin, ymax, xmax], \"label\": \"что это\"}] — "
                  "рамка элемента в координатах 0–1000. Если элементов несколько — самый подходящий первым. "
                  "Если элемента точно нет — []. Учитывай панель задач внизу и иконки в трее.")
        _, j = self.gemini.generate([{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}, {"text": prompt}]}],
            gen_cfg={"responseMimeType": "application/json", "temperature": 0.1}, timeout=30)
        raw = self.gemini.text_of(j)
        m = re.search(r"\[.*\]", raw, re.S)
        try:
            data = _json.loads(m.group(0) if m else raw)
        except Exception:
            return None, "непонятный ответ: " + raw[:120]
        if isinstance(data, dict):
            data = [data]
        for d in data:
            box = d.get("box_2d") or d.get("box")
            if box and len(box) == 4:
                return [float(v) for v in box], d.get("label", target)
        return None, "элемент не найден"

    def locate_on_screen(self, target):
        """Два прохода: грубо по всему экрану, затем уточнение по увеличенному фрагменту. Возвращает (x, y, label) в пикселях."""
        img = self._grab()
        W, H = img.size
        small = img.copy()
        small.thumbnail((1920, 1920))
        box, label = self._locate(small, target)
        if not box:
            return None, label
        y0, x0, y1, x1 = box
        cx, cy = (x0 + x1) / 2 / 1000 * W, (y0 + y1) / 2 / 1000 * H
        bw, bh = max(1, (x1 - x0) / 1000 * W), max(1, (y1 - y0) / 1000 * H)
        # уточнение: фрагмент в ~4 раза больше элемента (не меньше 360 px)
        rw, rh = max(360, bw * 4), max(360, bh * 4)
        L, T = int(max(0, cx - rw / 2)), int(max(0, cy - rh / 2))
        R, B = int(min(W, L + rw)), int(min(H, T + rh))
        crop = img.crop((L, T, R, B))
        try:
            box2, label2 = self._locate(crop, target, hint=" (увеличенный фрагмент)")
        except Exception:
            box2 = None
        if box2:
            y0, x0, y1, x1 = box2
            fx = L + (x0 + x1) / 2 / 1000 * (R - L)
            fy = T + (y0 + y1) / 2 / 1000 * (B - T)
            if abs(fx - cx) < rw and abs(fy - cy) < rh:
                cx, cy, label = fx, fy, label2 or label
        return (int(cx), int(cy), label), (W, H)

    def t_click_on_screen(self, target, button="left", double=False, confirmed=False):
        if self.cfg.get("confirm_dangerous", True) and not confirmed and any(w in target.lower() for w in self.DANGER_WORDS):
            return {"need_confirmation": True, "say": "Это может быть покупка/удаление — спроси пользователя и вызови снова с confirmed=true."}
        res, extra = self.locate_on_screen(target)
        if not res:
            return {"error": f"не вижу на экране «{target}»", "why": extra}
        px, py, label = res
        if getattr(self, "dry_run", False):
            return {"would_click": label, "at": [px, py], "screen": list(extra)}
        winsys.click(px, py, button or "left", bool(double))
        self.ctx.toast(f"🖱 {label or target}")
        return {"clicked": label or target, "at": [px, py]}

    def t_scroll(self, direction, amount=5):
        n = max(1, min(30, int(amount or 5)))
        winsys.scroll(n if direction == "up" else -n)
        return "прокручено"

    # ════════════════════════ режимы ════════════════════════
    def _parse_steps(self, steps):
        import json as _json
        names = {d["name"] for d in self._declarations()} | {"wait"}
        out, bad = [], []
        for st in steps or []:
            if isinstance(st, str):
                st = {"tool": st}
            tool = (st.get("tool") or "").strip()
            raw = st.get("args_json") if "args_json" in st else st.get("args", {})
            if isinstance(raw, str):
                try:
                    args = _json.loads(raw) if raw.strip() else {}
                except Exception:
                    bad.append(f"{tool}: аргументы не JSON")
                    continue
            else:
                args = raw or {}
            if tool not in names:
                bad.append(f"нет функции {tool}")
                continue
            if tool in NOT_IN_ROUTINE:
                bad.append(f"{tool} нельзя добавлять в режим")
                continue
            out.append({"tool": tool, "args": args if isinstance(args, dict) else {}})
        return out, bad

    @staticmethod
    def describe_step(st):
        a = st.get("args") or {}
        names = {"open_app": "открыть", "close_app": "закрыть", "volume": "громкость", "brightness": "яркость",
                 "youtube": "YouTube", "open_website": "сайт", "quiet_mode": "тихий режим", "media_control": "медиа",
                 "wait": "пауза", "window_action": "окна", "set_timer": "таймер", "press_keys": "клавиши",
                 "type_text": "напечатать", "discord": "Discord", "watch_screen": "вижу экран", "get_weather": "погода",
                 "tasks": "задачи", "display": "показать", "search_internet": "поиск", "switch_window": "окно"}
        vals = ", ".join(str(v) for v in a.values() if v not in (None, "", False))
        return names.get(st["tool"], st["tool"]) + (f": {vals}" if vals else "")

    def t_routine_save(self, name, steps, description=""):
        parsed, bad = self._parse_steps(steps)
        if not parsed:
            return {"error": "нет допустимых шагов", "problems": bad}
        r = self.store.save_routine(name, parsed, description)
        self.ctx.toast(f"⚙ Режим «{r['name']}» сохранён ({len(parsed)} шагов)")
        return {"saved": r["name"], "steps": [self.describe_step(x) for x in parsed], "skipped": bad,
                "how_to_run": f"скажите «включи режим {r['name']}»"}

    def t_routine_list(self):
        rs = self.store.snapshot()["routines"]
        if not rs:
            return "режимов пока нет — можно создать голосом: «создай игровой режим: открой стим, громкость 40, тихий режим»"
        return {"routines": [{"name": r["name"], "description": r.get("description", ""),
                              "steps": [self.describe_step(x) for x in r["steps"]]} for r in rs]}

    def t_routine_delete(self, name):
        r = self.store.delete_routine(name)
        return f"режим «{r['name']}» удалён" if r else {"error": "нет такого режима", "have": [x["name"] for x in self.store.snapshot()["routines"]]}

    def t_routine_run(self, name):
        r = self.store.find_routine(name)
        if not r:
            return {"error": f"нет режима «{name}»", "have": [x["name"] for x in self.store.snapshot()["routines"]]}
        self.ctx.toast(f"⚙ Режим «{r['name']}»")
        done, errors = [], []
        t0 = time.time()
        for st in r["steps"]:
            if time.time() - t0 > 110:
                errors.append("режим выполнялся слишком долго, остальные шаги пропущены")
                break
            if st["tool"] == "wait":
                time.sleep(max(0.0, min(30.0, float((st.get("args") or {}).get("seconds", 1)))))
                continue
            res = self.call(st["tool"], dict(st.get("args") or {}))
            d = self.describe_step(st)
            if isinstance(res, dict) and res.get("error"):
                errors.append(f"{d} — {res['error']}")
            else:
                done.append(d)
            if st["tool"] in ("open_app", "open_website", "youtube"):
                time.sleep(1.2)  # даём окну открыться, чтобы следующие клавиши/клики попали куда надо
            else:
                time.sleep(0.2)
        return {"routine": r["name"], "done": done, "errors": errors}

    def t_quiet_mode(self, minutes=60, off=False):
        if off:
            self.store.set_meta("quiet_until", 0)
            self.ctx.toast("🔔 Тихий режим выключен")
            return "тихий режим выключен"
        m = max(1, min(24 * 60, int(minutes or 60)))
        until = time.time() + m * 60
        self.store.set_meta("quiet_until", until)
        self.ctx.toast(f"🔕 Тихий режим до {dt.datetime.fromtimestamp(until):%H:%M}")
        return {"quiet_until": dt.datetime.fromtimestamp(until).strftime("%H:%M"), "note": "будильники и таймеры всё равно сработают"}

    # ════════════════════════ экран и игры ════════════════════════
    def t_watch_screen(self, on=True):
        return self.ctx.set_watch(bool(on))

    def t_game_clip(self):
        method = self.cfg.get("clip_method", "auto")
        nv = winsys.process_running("NVIDIA Overlay.exe", "NVIDIA app.exe", "nvsphelper64.exe")
        if method == "nvidia" or (method == "auto" and nv):
            winsys.hotkey("alt+f10")
            self.ctx.toast("🎬 Клип: NVIDIA Instant Replay")
            return {"ok": True, "via": "NVIDIA (Alt+F10)",
                    "note": "сработает, если в NVIDIA app включён «Мгновенный повтор»; клип в папке Видео"}
        winsys.hotkey("win+alt+g")
        self.ctx.toast("🎬 Клип: Xbox Game Bar")
        return {"ok": True, "via": "Xbox Game Bar (Win+Alt+G)",
                "note": "сохраняет последние 30 секунд, если в Game Bar включена фоновая запись; клип в Видео\\Клипы"}

    def t_discord(self, action):
        key = (self.cfg.get("discord_mute_key" if action == "mute" else "discord_deafen_key") or "").strip()
        if not key:
            return {"error": "не задана горячая клавиша Discord",
                    "how": "В Discord: Настройки → Горячие клавиши → добавить «Вкл./выкл. микрофон» (и «звук»), например "
                           "Ctrl+Shift+F9 / Ctrl+Shift+F10. Затем впишите их в настройках Джарвиса → Игры."}
        winsys.hotkey(key.lower().replace(" ", ""))
        self.ctx.toast("🎧 Discord: " + ("микрофон" if action == "mute" else "звук"))
        return f"нажато {key} (переключено)"

    # ════════════════════════ обновления ════════════════════════
    def t_jarvis_update(self, action="check", confirmed=False):
        up = self.ctx.updater
        if action == "install":
            if not confirmed:
                return {"need_confirmation": True, "say": "Спроси, обновиться ли сейчас (перезапуск ~20 с), и вызови с confirmed=true."}
            self.ctx.later(4.0, up.install)  # даём договорить «обновляюсь»
            return "начинаю обновление через пару секунд: скажи пользователю, что вернёшься через полминуты"
        i = up.check()
        self.ctx.push_update()
        if i.get("error"):
            return {"current": i["current"], "error": i["error"]}
        return {"current": i["current"], "latest": i.get("latest"), "available": i["available"], "whats_new": i.get("notes", "")[:1500]}

    # ════════════════════════ файлы ════════════════════════
    def t_find_file(self, query, open=True):
        found = self.apps.find_file(query)
        if not found:
            return {"error": "ничего не нашёл", "hint": "индекс файлов ещё строится" if not self.apps.files else ""}
        if open:
            winsys.open_path(found[0])
            self.ctx.toast(f"📄 {os.path.basename(found[0])}")
        return {"found": found, "opened": found[0] if open else None}

    # ════════════════════════ погода, валюты ════════════════════════
    @staticmethod
    def _city_variants(city):
        c = city.strip()
        out = [c]
        if len(c) > 3:
            if c.endswith(("е", "и")):
                out += [c[:-1] + "а", c[:-1], c[:-1] + "ь", c[:-1] + "я"]
            elif c.endswith("у"):
                out += [c[:-1] + "а"]
        return out

    def _geocode(self, city):
        """Ищет город; при одинаковых названиях выбирает ближайший к городу пользователя (или крупный в Европе)."""
        import math
        home = getattr(self, "_home", None)
        if home is None and city.strip().lower() != (self.cfg.get("city") or "").strip().lower():
            self._home = home = (self._geocode(self.cfg.get("city")) if self.cfg.get("city") else None) or {}
        for v in self._city_variants(city):
            r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": v, "count": 10, "language": self.cfg.get("ui_language") or "en"}, timeout=10)
            res = (r.json() or {}).get("results") or []
            if not res:
                continue

            def score(c):
                sc = math.log10((c.get("population") or 0) + 10)
                if home and home.get("latitude") is not None:
                    d = math.hypot(c["latitude"] - home["latitude"], (c["longitude"] - home["longitude"]) * 0.7)
                    sc -= d / 8  # каждые ~900 км «стоят» как десятикратная разница населения
                    if c.get("country_code") == home.get("country_code"):
                        sc += 1.5
                elif 34 < c.get("latitude", 0) < 72 and -25 < c.get("longitude", 0) < 45:
                    sc += 2  # Европа
                if (c.get("name") or "").lower() == v.lower():
                    sc += 1
                return sc
            return max(res, key=score)
        return None

    def weather_data(self, city=None, days=4):
        city = (city or self.cfg.get("city") or "").strip()
        if not city:
            raise ValueError("город не задан")
        key = (city.lower(), days)
        hit = self._weather_cache.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        loc = self._geocode(city)
        if not loc:
            raise ValueError(f"не нашёл город {city}")
        j = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto",
            "forecast_days": max(1, min(7, int(days))), "wind_speed_unit": "ms",
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        }, timeout=10).json()
        cur, day = j["current"], j["daily"]
        data = {
            "city": loc.get("name", city), "country": loc.get("country", ""),
            "now": {"temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]), "code": int(cur["weather_code"]),
                    "desc": WEATHER_CODES.get(int(cur["weather_code"]), ""), "icon": WEATHER_ICON.get(int(cur["weather_code"]), "cloud"),
                    "wind": round(cur["wind_speed_10m"]), "humidity": cur.get("relative_humidity_2m"), "is_day": cur.get("is_day", 1)},
            "days": [{"date": day["time"][i], "max": round(day["temperature_2m_max"][i]), "min": round(day["temperature_2m_min"][i]),
                      "code": int(day["weather_code"][i]),
                      "rain": day["precipitation_probability_max"][i], "desc": WEATHER_CODES.get(int(day["weather_code"][i]), ""),
                      "icon": WEATHER_ICON.get(int(day["weather_code"][i]), "cloud")} for i in range(len(day["time"]))],
            "sunrise": day["sunrise"][0][-5:], "sunset": day["sunset"][0][-5:],
        }
        self._weather_cache[key] = (time.time(), data)
        return data

    def t_get_weather(self, city="", days=1):
        n = max(1, min(7, int(days or 1)))
        home = not city or norm(city) == norm(self.cfg.get("city", ""))
        # карточка «Сегодня» всегда показывает 4 дня — даже если модель спросила только про сегодня
        d = self.weather_data(city or None, max(n, 4) if home else n)
        if home:
            self.ctx.push_weather(d)
            d = dict(d, days=(d.get("days") or [])[:n])
        return d

    def t_exchange_rate(self, base, target, amount=1):
        def code(x):
            x = (x or "").strip()
            if len(x) == 3 and x.isalpha():
                return x.upper()
            for k, v in CURRENCY.items():
                if k in x.lower():
                    return v
            return x.upper()[:3]
        b, t = code(base), code(target)
        j = requests.get(f"https://open.er-api.com/v6/latest/{b}", timeout=10).json()
        if j.get("result") != "success" or t not in j.get("rates", {}):
            return {"error": f"нет курса {b}→{t}"}
        rate = j["rates"][t]
        amt = float(amount or 1)
        return {"base": b, "target": t, "rate": round(rate, 4), "amount": amt, "converted": round(amt * rate, 2),
                "updated": j.get("time_last_update_utc", "")[:16]}

    # ════════════════════════ система ════════════════════════
    def t_system_status(self):
        s = self.ctx.stats.snapshot()
        s["top_memory_apps_mb"] = self.ctx.stats.top_processes(5)
        s["active_window"] = winsys.foreground_title()[:80]
        s["active_process"] = winsys.foreground_process()
        g = getattr(self.ctx, "game_since", 0)
        if g:
            s["gaming_for"] = duration_words(int(time.time() - g) // 60 * 60)
        if "uptime" in s:
            s["uptime_text"] = duration_words(s["uptime"] // 60 * 60)
        s.pop("ts", None)
        for k in ("down", "up"):
            if k in s:
                s[k + "_kbps"] = round(s.pop(k) / 1024)
        return s

    # ════════════════════════ таймеры ════════════════════════
    def t_set_timer(self, seconds, label=""):
        seconds = int(float(seconds))
        if seconds <= 0:
            return {"error": "время должно быть больше нуля"}
        t = self.store.add_timer(time.time() + seconds, label, "timer")
        self.ctx.toast(f"⏱ Таймер {duration_words(seconds)}" + (f": {label}" if label else ""))
        return {"ok": True, "id": t["id"], "fires_at": dt.datetime.fromtimestamp(t["due"]).strftime("%H:%M:%S")}

    def t_set_reminder(self, when, label="", alarm=False):
        now = dt.datetime.now()
        w = when.strip().replace(" ", "T")
        if re.fullmatch(r"\d{1,2}[:.]\d{2}", w):
            h, m = map(int, re.split(r"[:.]", w))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += dt.timedelta(days=1)
        else:
            target = dt.datetime.fromisoformat(w)
            if target.tzinfo:
                target = target.astimezone().replace(tzinfo=None)
        if target <= now:
            return {"error": "это время уже прошло"}
        t = self.store.add_timer(target.timestamp(), label, "alarm" if alarm else "reminder")
        txt = f"{target.day} {MONTHS_GEN[target.month - 1]} в {target:%H:%M}"
        self.ctx.toast(("⏰ Будильник " if alarm else "🔔 Напоминание ") + txt)
        return {"ok": True, "id": t["id"], "at": txt, "note": "сработает, только если Джарвис запущен, а ноутбук не спит"}

    def t_list_timers(self):
        out = []
        for t in self.store.snapshot()["timers"]:
            left = int(t["due"] - time.time())
            out.append({"label": t["label"] or t["kind"], "kind": t["kind"],
                        "at": dt.datetime.fromtimestamp(t["due"]).strftime("%d.%m %H:%M:%S"),
                        "left": duration_words(max(0, left))})
        return {"timers": out} if out else "активных таймеров нет"

    def t_cancel_timer(self, label="", all=False):
        if all:
            n = 0
            while self.store.snapshot()["timers"]:
                n += self.store.cancel_timer()
            return f"отменено: {n}"
        n = self.store.cancel_timer(label=label or None)
        return f"отменено: {n}" if n else {"error": "такого таймера нет"}

    # ════════════════════════ задачи, заметки, память ════════════════════════
    def t_tasks(self, action, text=""):
        if action == "add":
            self.store.add_task(text)
            self.ctx.toast(f"✓ Задача: {text}")
        elif action in ("done", "undo"):
            if not self.store.set_task(text=text, done=(action == "done")):
                return {"error": "не нашёл такую задачу"}
        elif action == "delete":
            if not self.store.set_task(text=text, delete=True):
                return {"error": "не нашёл такую задачу"}
        elif action == "clear_done":
            self.store.clear_done()
        tasks = self.store.snapshot()["tasks"]
        return {"tasks": [{"text": t["text"], "done": t["done"]} for t in tasks]}

    def t_notes(self, action, text=""):
        if action == "add":
            self.store.add_note(text)
            self.ctx.toast("📝 Записал")
            return "записано"
        notes = self.store.snapshot()["notes"][-8:]
        return {"notes": [{"text": n["text"], "date": dt.datetime.fromtimestamp(n["created"]).strftime("%d.%m %H:%M")} for n in notes]}

    def t_memory(self, action, fact=""):
        if action == "remember":
            self.store.remember(fact)
            self.ctx.toast("🧠 Запомнил")
            return "запомнено навсегда"
        if action == "forget":
            n = self.store.forget(fact)
            return f"забыто записей: {n}"
        return {"facts": [m["fact"] for m in self.store.snapshot()["memory"]]}

    def t_display(self, title, content):
        self.ctx.ui_card(title, content)
        return "показано на экране карточкой; закрыть её — close_display"

    def t_close_display(self, what="all"):
        self.ctx.ui_close(what or "all")
        return "закрыто"

    def t_hud_window(self, action):
        from . import desktop
        if action == "show":
            desktop.focus_window(self.ctx.port)
            return "окно Джарвиса показано"
        desktop.minimize_window()
        return "окно Джарвиса свёрнуто"

    # ════════════════════════ прочее ════════════════════════
    _OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
            ast.USub: operator.neg, ast.UAdd: operator.pos}

    def t_calculate(self, expression):
        import math
        funcs = {k: getattr(math, k) for k in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "floor",
                                               "ceil", "factorial", "radians", "degrees", "asin", "acos", "atan")}
        funcs.update(abs=abs, round=round, pi=math.pi, e=math.e)
        expr = expression.replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", ".")

        def ev(n):
            if isinstance(n, ast.Expression):
                return ev(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.BinOp) and type(n.op) in self._OPS:
                if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 1000:
                    raise ValueError("слишком большая степень")
                return self._OPS[type(n.op)](ev(n.left), ev(n.right))
            if isinstance(n, ast.UnaryOp) and type(n.op) in self._OPS:
                return self._OPS[type(n.op)](ev(n.operand))
            if isinstance(n, ast.Name) and n.id in funcs and not callable(funcs[n.id]):
                return funcs[n.id]
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs:
                return funcs[n.func.id](*[ev(a) for a in n.args])
            raise ValueError("недопустимое выражение")
        v = ev(ast.parse(expr, mode="eval"))
        if isinstance(v, float):
            v = round(v, 10)
        return {"result": v}

    def t_now(self):
        n = dt.datetime.now()
        return f"{WEEKDAYS[n.weekday()]}, {n.day} {MONTHS_GEN[n.month - 1]} {n.year}, {n:%H:%M:%S}"

    def t_power(self, action, confirmed=False):
        if not IS_WIN:
            return {"error": "только Windows"}
        if action in ("shutdown", "restart") and not confirmed:
            return {"need_confirmation": True, "say": "Спроси пользователя, точно ли выполнить, и вызови снова с confirmed=true."}
        if action == "lock":
            self.ctx.later(2.0, winsys.lock)
            return "блокирую через 2 секунды"
        if action == "sleep":
            self.ctx.later(3.5, winsys.sleep_pc)
            return "сплю через 3 секунды"
        if action in ("shutdown", "restart"):
            winsys.shutdown(restart=(action == "restart"), delay=20)
            self.ctx.ui_shutdown(20, action)
            return "через 20 секунд. На экране есть кнопка «Отмена», или скажи «отмени выключение»."
        if action == "cancel_shutdown":
            winsys.cancel_shutdown()
            self.ctx.ui_shutdown(0, "cancel")
            return "выключение отменено"
        return {"error": "неизвестное действие"}

    def t_empty_recycle_bin(self, confirmed=False):
        if not confirmed:
            return {"need_confirmation": True}
        ok = winsys.empty_recycle_bin()
        self.ctx.toast("🗑 Корзина очищена")
        return "корзина очищена" if ok else "корзина уже пуста"

    def t_set_preference(self, key, value):
        if key == "headphones":
            value = str(value).lower() in ("true", "1", "да", "yes", "on")
        if key == "voice":
            from .config import VOICES
            m = [v for v in VOICES if v.lower() == str(value).lower()]
            if not m:
                return {"error": "нет такого голоса", "voices": list(VOICES)}
            value = m[0]
        self.cfg[key] = value
        self.cfg.save()
        self.ctx.on_settings_changed()
        return f"{key} = {value}" + (" (новый голос включится со следующей фразы-сессии)" if key == "voice" else "")

    def t_end_conversation(self):
        self.ctx.request_end()
        return "разговор завершится после ответа"
