# -*- coding: utf-8 -*-
"""Telegram-бот: управление Джарвисом с телефона и уведомления.

Безопасность: бот отвечает только одному чату — тому, кто прислал код привязки из настроек Джарвиса.
Работает через long polling (getUpdates), без внешнего сервера и открытых портов."""
import base64
import datetime as dt
import io
import logging
import random
import re
import threading
import time

import requests

log = logging.getLogger("jarvis.tg")

# в переписке эти функции не нужны или опасны без голоса/экрана
EXCLUDE = {"end_conversation", "display", "close_display", "hud_window", "watch_screen"}

TG_NOTE = """
СЕЙЧАС ОСОБЫЙ РЕЖИМ: это переписка в Telegram — пользователь пишет с телефона и, скорее всего, не сидит за ноутбуком.
- Отвечай ТЕКСТОМ, коротко и по делу. Можно короткий список, без сложного markdown (без таблиц и заголовков).
- Все функции выполняются на ноутбуке пользователя. Делай то, что просят, и сообщай результат.
- «Пришли/скинь экран», «что сейчас на компе» — send_screen_photo (фото придёт в чат). Чтобы понять, что на экране, — look_at_screen.
- Выключение/перезагрузку — только после явного «да» в переписке (confirmed=true).
- Не говори, что что-то сделал, если не вызвал функцию."""

HELP = ("Я Джарвис — твой ноутбук на связи.\n\n"
        "Просто пиши (или отправляй голосовые), что сделать: «включи музыку», «сколько заряда», «поставь таймер на 20 минут», "
        "«что сейчас на экране», «выключи комп через час», «запусти игровой режим».\n\n"
        "Команды:\n/screen — снимок экрана\n/status — состояние ноутбука\n/quiet — тихий режим на час\n"
        "/update — обновить Джарвиса\n/clear — забыть переписку\n/help — эта справка")


class TelegramBot:
    def __init__(self, ctx):
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.token = (self.cfg.get("telegram_token") or "").strip()
        self.api = f"https://api.telegram.org/bot{self.token}/"
        self.stop_ev = threading.Event()
        self.thread = None
        self.me = None
        self.error = ""
        self.code = f"{random.randint(100000, 999999)}"
        self.offset = 0
        self.histories = {}
        self.last_ok = 0.0

    # ── жизненный цикл ──
    def start(self):
        self.thread = threading.Thread(target=self._run, name="telegram", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()

    def status(self):
        return {"on": True, "ok": bool(self.me), "bot": (self.me or {}).get("username", ""),
                "bound": bool(self.cfg.get("telegram_chat_id")), "code": self.code, "error": self.error}

    # ── HTTP ──
    def _call(self, method, http_timeout=20, files=None, **params):
        if files:
            r = requests.post(self.api + method, data=params, files=files, timeout=http_timeout)
        else:
            r = requests.post(self.api + method, json=params, timeout=http_timeout)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not j.get("ok"):
            desc = j.get("description") or f"HTTP {r.status_code}"
            if r.status_code == 401:
                desc = "неверный токен бота"
            raise RuntimeError(desc)
        return j["result"]

    def send(self, chat_id, text):
        text = (text or "").replace("**", "").strip() or "Готово."
        for i in range(0, len(text), 3900):
            try:
                self._call("sendMessage", chat_id=chat_id, text=text[i:i + 3900], disable_web_page_preview=True)
            except Exception as e:
                log.warning("sendMessage: %s", e)

    def send_photo(self, chat_id, jpeg, caption=""):
        self._call("sendPhoto", http_timeout=60, files={"photo": ("screen.jpg", jpeg, "image/jpeg")},
                   chat_id=str(chat_id), caption=caption[:1000])

    def notify(self, text):
        chat = self.cfg.get("telegram_chat_id")
        if not chat or not self.me:
            return
        threading.Thread(target=self.send, args=(chat, text), daemon=True).start()

    def _download(self, file_id):
        f = self._call("getFile", file_id=file_id)
        r = requests.get(f"https://api.telegram.org/file/bot{self.token}/{f['file_path']}", timeout=60)
        r.raise_for_status()
        return r.content

    # ── основной цикл ──
    def _run(self):
        while not self.stop_ev.is_set():
            try:
                self.me = self._call("getMe")
                self.error = ""
                log.info("Telegram-бот @%s на связи", self.me.get("username"))
                break
            except Exception as e:
                self.error = str(e)[:150]
                log.warning("Telegram getMe: %s", e)
                self.ctx.on_settings_changed()
                if "токен" in self.error:
                    return
                self.stop_ev.wait(15)
        self.ctx.on_settings_changed()
        # пропускаем то, что пришло, пока Джарвис был выключен (кроме последних 2 минут)
        try:
            old = self._call("getUpdates", offset=-1, timeout=0)
            if old:
                self.offset = old[-1]["update_id"] + (1 if time.time() - old[-1].get("message", {}).get("date", 0) > 120 else 0)
        except Exception:
            pass
        while not self.stop_ev.is_set():
            try:
                ups = self._call("getUpdates", http_timeout=35, offset=self.offset, allowed_updates=["message"], timeout=25)
                self.last_ok = time.time()
                if self.error:
                    self.error = ""
                    self.ctx.on_settings_changed()
            except Exception as e:
                if self.stop_ev.is_set():
                    break
                self.error = str(e)[:150]
                log.warning("getUpdates: %s", e)
                self.stop_ev.wait(5)
                continue
            for u in ups:
                self.offset = u["update_id"] + 1
                if self.stop_ev.is_set():
                    break
                m = u.get("message")
                if m:
                    try:
                        self._handle(m)
                    except Exception as e:
                        log.exception("telegram handle")
                        self.send(m["chat"]["id"], f"Ошибка: {str(e)[:200]}")
        log.info("Telegram-бот остановлен")

    # ── сообщения ──
    def _handle(self, m):
        chat = m["chat"]["id"]
        text = (m.get("text") or m.get("caption") or "").strip()
        bound = int(self.cfg.get("telegram_chat_id") or 0)
        if not bound:
            if m["chat"].get("type") != "private":
                return
            if self.code in re.sub(r"\D", "", text):
                self.cfg["telegram_chat_id"] = chat
                self.cfg.save()
                name = m.get("from", {}).get("first_name", "")
                self.send(chat, f"✅ Привязано{', ' + name if name else ''}! Теперь я отвечаю только тебе.\n\n" + HELP)
                self.ctx.toast("📱 Telegram привязан")
                self.ctx.on_settings_changed()
            else:
                self.send(chat, "Привет! Чтобы привязать меня, отправь код из настроек Джарвиса (вкладка «Телефон»).")
            return
        if chat != bound:
            self.send(chat, "Этот Джарвис привязан к другому аккаунту.")
            return

        cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""
        if cmd in ("/start", "/help"):
            return self.send(chat, HELP)
        if cmd == "/clear":
            self.histories.pop(chat, None)
            return self.send(chat, "Переписку забыл.")
        if cmd == "/quiet":
            self.ctx.tools.t_quiet_mode(60)
            return self.send(chat, "🔕 Тихий режим на час.")
        if cmd == "/screen":
            self._typing(chat, "upload_photo")
            return self.send_photo(chat, self._screen_jpeg(), "Экран сейчас")
        if cmd == "/status":
            return self.send(chat, self._status_text())
        if cmd == "/update":
            i = self.ctx.updater.check()
            self.ctx.push_update()
            if not i.get("available"):
                return self.send(chat, f"Версия {i['current']} — последняя." + (f" ({i['error']})" if i.get("error") else ""))
            self.send(chat, f"⬆ Ставлю версию {i['latest']}, вернусь через полминуты…")
            res = self.ctx.updater.install()
            if res.get("error"):
                self.send(chat, "Не вышло: " + res["error"])
            return

        parts = []
        if m.get("voice") or m.get("audio"):
            v = m.get("voice") or m.get("audio")
            parts.append({"inline_data": {"mime_type": v.get("mime_type", "audio/ogg"),
                                          "data": base64.b64encode(self._download(v["file_id"])).decode()}})
            parts.append({"text": "(голосовое сообщение пользователя — выполни, что он говорит)"})
            shown = "🎤 голосовое"
        elif m.get("photo"):
            ph = m["photo"][-1]
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(self._download(ph["file_id"])).decode()}})
            parts.append({"text": text or "Что на этом фото?"})
            shown = "🖼 фото" + (f": {text}" if text else "")
        elif text:
            parts.append({"text": text})
            shown = text
        else:
            return self.send(chat, "Понимаю текст, голосовые и фото.")
        self.ctx._threadsafe({"t": "msg", "role": "user", "text": "📱 " + shown, "id": f"tg{m['message_id']}", "final": True})
        self._typing(chat)
        reply = self.agent(chat, parts)
        self.ctx.store.add_history("user", "(в Telegram) " + shown)
        self.ctx.store.add_history("jarvis", "(в Telegram) " + reply)
        self.ctx._threadsafe({"t": "msg", "role": "jarvis", "text": "📱 " + reply, "id": f"tgr{m['message_id']}", "final": True})
        self.send(chat, reply)

    def _typing(self, chat, action="typing"):
        try:
            self._call("sendChatAction", chat_id=chat, action=action, http_timeout=5)
        except Exception:
            pass

    def _screen_jpeg(self):
        img = self.ctx.tools._grab(1920)
        b = io.BytesIO()
        img.convert("RGB").save(b, "JPEG", quality=82)
        return b.getvalue()

    def _status_text(self):
        s = self.ctx.tools.t_system_status()
        g = s.get("gpu") or {}
        lines = [f"💻 ЦП {s.get('cpu', '?')}% · ОЗУ {s.get('ram', '?')}% ({s.get('ram_used', '?')}/{s.get('ram_total', '?')} ГБ)"]
        if g:
            lines.append(f"🎮 {g.get('name', 'ГП')}: {g.get('util', 0):.0f}% · {g.get('temp', 0):.0f}°C")
        if "battery" in s:
            lines.append(f"🔋 {s['battery']}% {'(заряжается)' if s.get('plugged') else '(от батареи)'}")
        if "disk_free" in s:
            lines.append(f"💾 свободно {s['disk_free']} ГБ")
        if s.get("active_window"):
            lines.append(f"🪟 {s['active_window']}")
        if s.get("gaming_for"):
            lines.append(f"🕹 играет {s['gaming_for']}")
        if s.get("uptime_text"):
            lines.append(f"⏱ работает {s['uptime_text']}")
        if self.ctx.quiet():
            lines.append(f"🔕 тихий режим до {dt.datetime.fromtimestamp(self.ctx.store.data['quiet_until']):%H:%M}")
        return "\n".join(lines)

    # ── агент: Gemini + инструменты ноутбука ──
    def _decls(self):
        d = [x for x in self.ctx.tools.declarations() if x["name"] not in EXCLUDE]
        d.append({"name": "send_screen_photo", "description": "Отправить пользователю в Telegram фото текущего экрана ноутбука.",
                  "parameters": {"type": "object", "properties": {"caption": {"type": "string", "description": "подпись"}}}})
        return d

    def _system(self):
        from .assistant import build_prompt
        from .util import MONTHS_GEN, WEEKDAYS
        n = dt.datetime.now()
        now = f"{WEEKDAYS[n.weekday()]}, {n.day} {MONTHS_GEN[n.month - 1]} {n.year}, {n:%H:%M}"
        facts = [x["fact"] for x in self.ctx.store.snapshot()["memory"]]
        memory = ("- Что ты знаешь о пользователе:\n" + "\n".join(f"  • {f}" for f in facts[-40:]) + "\n") if facts else ""
        rs = self.ctx.store.snapshot()["routines"]
        routines = ("- Сохранённые режимы: " + ", ".join(f"«{r['name']}»" for r in rs) + "\n") if rs else ""
        return build_prompt(self.cfg, now, memory, "", routines) + TG_NOTE

    def agent(self, chat, parts):
        hist = self.histories.setdefault(chat, [])
        hist.append({"role": "user", "parts": parts})
        decls, system = self._decls(), self._system()
        reply = ""
        try:
            for _ in range(8):
                _, j = self.ctx.gemini.generate(hist, tools=[{"functionDeclarations": decls}], system=system, timeout=60)
                content = ((j.get("candidates") or [{}])[0].get("content") or {})
                out = content.get("parts") or []
                hist.append({"role": "model", "parts": out})
                calls = [p["functionCall"] for p in out if p.get("functionCall")]
                if not calls:
                    reply = self.ctx.gemini.text_of(j)
                    break
                resp = []
                for c in calls:
                    name, args = c.get("name"), c.get("args") or {}
                    log.info("TG TOOL %s %s", name, str(args)[:200])
                    self.ctx._threadsafe({"t": "tool", "name": name, "args": args})
                    if name == "send_screen_photo":
                        try:
                            self.send_photo(chat, self._screen_jpeg(), args.get("caption", ""))
                            res = {"result": "фото экрана отправлено"}
                        except Exception as e:
                            res = {"error": str(e)[:200]}
                    else:
                        res = self.ctx.tools.call(name, args)
                    if not isinstance(res, dict):
                        res = {"result": res}
                    fr = {"name": name, "response": res}
                    if c.get("id"):
                        fr["id"] = c["id"]
                    resp.append({"functionResponse": fr})
                hist.append({"role": "user", "parts": resp})
                self._typing(chat)
            else:
                reply = reply or "Сделал несколько действий подряд, но так и не закончил — уточни, пожалуйста."
        except Exception as e:
            log.warning("tg agent: %s", e)
            if hist and hist[-1].get("role") == "user" and hist[-1].get("parts") is parts:
                hist.pop()
            return f"Не получилось связаться с Gemini: {str(e)[:150]}"
        # тяжёлые вложения в истории больше не нужны
        for p in parts:
            if "inline_data" in p:
                p.clear()
                p["text"] = "[вложение уже обработано]"
        self._trim(hist)
        return reply or "Готово."

    @staticmethod
    def _trim(hist, keep=24):
        if len(hist) <= keep:
            return
        cut = len(hist) - keep
        # начинаем с обычного сообщения пользователя, а не с ответа функции
        while cut < len(hist) and not (hist[cut]["role"] == "user" and any("text" in p for p in hist[cut]["parts"])):
            cut += 1
        del hist[:cut]
