# -*- coding: utf-8 -*-
"""Оркестратор: слово активации → Live-сессия → голос/инструменты → интерфейс."""
import asyncio
import datetime as dt
import io
import json
import logging
import threading
import time
import uuid
import wave

import aiohttp
import numpy as np

from .apps import Apps
from .audio import AudioIO, list_devices
from .config import BASE, VOICES, Config
from .gemini import Gemini
from .live import LiveError, LiveSession
from .store import Store
from .tools import Toolbox
from .util import MONTHS_GEN, WEEKDAYS
from .wake import Wake
from .winsys import Stats

log = logging.getLogger("jarvis")

CHARACTER = {
    "butler": ("Personality: a refined AI butler — impeccably polite, composed and witty, with light dry British humour; "
               "confident and competent, never fussy. Address the user as “{user}”, formally."),
    "friend": "Personality: friendly, lively and funny, talks casually like a good friend who is great with computers. Call the user “{user}”.",
    "pro": "Personality: a reserved professional. Only the essentials, no jokes, no filler. Address the user as “{user}”.",
    "tutor": ("Personality: a patient tutor. Call the user “{user}”, informally. Explain step by step in simple words; do not give the "
              "final answer straight away — first a hint or a guiding question, then the next step. Check understanding "
              "(“does that make sense?”). Praise correct steps, calmly go through mistakes. If you can see the screen (a task, "
              "code, text), refer to what is there and point to where to look. If asked for “just the answer”, give it."),
    "custom": "",
}
LENGTH = {
    "short": "Answer naturally and BRIEFLY: usually 1–2 sentences. Go into detail only when asked.",
    "normal": "Answer naturally, usually 2–4 sentences; a bit more when the topic is complex.",
    "detailed": "Answer thoroughly and in depth, but without filler.",
}
LANG = {"auto": "Always reply in the language the user speaks or writes in.",
        "ru": "Always reply in Russian.", "uk": "Always reply in Ukrainian.", "en": "Always reply in English.",
        "sk": "Always reply in Slovak.", "cs": "Always reply in Czech.", "de": "Always reply in German.",
        "fr": "Always reply in French.", "es": "Always reply in Spanish.", "it": "Always reply in Italian.",
        "pl": "Always reply in Polish."}

PROMPT = """You are {name}, a personal AI assistant built into the user's Windows PC. You can hear, speak, see the screen and act on the computer.
{character}

How to speak:
- This is a voice conversation. {length}
- {lang} Say numbers, units and times the way people say them aloud.
- No lists, markdown or links in speech. Long content (a recipe, plan, code, table, translation) — show it with display and say only the gist.
- Do not start with “Sure!” and do not repeat the question. Get straight to the point.

How to act:
- When asked to do something on the computer, CALL the function right away — do not ask unnecessary questions or explain how to do it manually.
  Never say you did something unless you called the function. After the result, confirm briefly.
- Several actions in a row — call several functions one after another (e.g. open an app → look at the screen → click).
- Fresh facts (news, rates, scores, prices, “who is currently…”, anything after 2025) — use search_internet / get_weather / exchange_rate.
  While searching you may say “one moment”.
- Questions about what is on the screen, errors, “help me with this”, “read this” — look_at_screen.
- To press a button/link/menu item in an app — click_on_screen with a clear description of the element.
- Routines: “create a routine X: …” — routine_save (translate the user's words into steps yourself); “start routine X” — routine_run.
  “Do not disturb”, “quiet”, “I'm in class/in a game” — quiet_mode. Timers and alarms still ring in quiet mode.
- “Watch my screen”, “follow my game”, “help me, I'm solving a task” — watch_screen on=true; screen frames will then arrive
  by themselves, comment on them. If you are receiving screen frames (video), the mode is already on: look at them and do not
  call look_at_screen. “Stop watching” — watch_screen on=false.
- “Update yourself”, “any updates?” — jarvis_update (install only after an explicit “yes”).
- “Save that moment”, “clip it” — game_clip. “Mute me on Discord” — discord mute.
- If a card is open on your window (after display or search_internet) and the user says “close”, “got it”, “thanks” —
  call close_display. “Minimize yourself” — hud_window minimize, “show yourself” — hud_window show.
{danger}- When the user says goodbye or “thanks, that's all” — answer briefly and call end_conversation.
- Messages in square brackets [SYSTEM: …] or [СИСТЕМА: …] are service events (timer, reminder, overheating, battery, long
  gaming session). Tell the user about them briefly and naturally, in the user's language, without saying “system”.
- If you did not hear clearly, ask again in one word. Background noise and other people's conversations are not for you — ignore them.
{custom}
Context:
- Now: {now}. User's city: {city}.
{routines}{briefing}{memory}{history}"""


def build_prompt(cfg, now, memory="", history="", routines="", briefing="", pro=True):
    from .brand import name as brand_name
    user = cfg.get("user_name") or ("сэр" if cfg.get("ui_language") == "ru" else "sir")
    persona = cfg.get("persona", "butler")
    from .license import PRO_PERSONAS
    if not pro and persona in PRO_PERSONAS:
        persona = "butler"
    character = CHARACTER.get(persona, CHARACTER["butler"]).format(user=user)
    if persona == "custom" and not cfg.get("custom_instructions"):
        character = CHARACTER["butler"].format(user=user)
    danger = ("- Shutdown, restart, emptying the recycle bin, clicking “buy/pay/delete/send” buttons — first a short confirmation "
              "question, then the action with confirmed=true.\n") if cfg.get("confirm_dangerous", True) else \
             "- Dangerous actions (shutdown, restart, recycle bin) — do them right away with confirmed=true, without asking.\n"
    custom = ""
    if (cfg.get("custom_instructions") or "").strip():
        custom = "\nThe user's own instructions (follow them first):\n" + cfg["custom_instructions"].strip() + "\n"
    if not pro:
        custom += ("\nThis is the free version. Routines, quiet mode, screen watching, the tutor, the Telegram bot and proactive alerts "
                   "are Pro features: if asked for them, briefly say they can be unlocked in Settings → Pro.\n")
    return PROMPT.format(name=brand_name(cfg.get("ui_language") or "en"), character=character,
                         length=LENGTH.get(cfg.get("reply_length"), LENGTH["short"]),
                         lang=LANG.get(cfg.get("reply_language"), LANG["auto"]), danger=danger, custom=custom,
                         now=now, city=cfg.get("city", ""), memory=memory, history=history,
                         routines=routines, briefing=briefing)


class _Compat:  # для selftest: PERSONA.format(...)
    @staticmethod
    def format(user="сэр", now="", city="", memory="", history=""):
        return build_prompt({"user_name": user, "city": city}, now, memory, history)


PERSONA = _Compat()


class Assistant:
    def __init__(self):
        self.cfg = Config()
        self.store = Store()
        self.gemini = Gemini(self.cfg)
        self.apps = Apps(self.cfg, BASE)
        self.stats = Stats()
        self.audio = AudioIO(self.cfg)
        self.wake = None
        self.tools = Toolbox(self)
        self.loop = None
        self.http = None
        self.clients = set()
        self.state = "boot"
        self.state_detail = ""
        self.session = None
        self.session_lock = None
        self.mic_q = None
        self.capturing = False
        self.mic_enabled = True
        self.last_activity = 0.0
        self.drop_audio = False
        self.end_requested = False
        self.user_buf = ""
        self.jarvis_buf = ""
        self.user_msg_id = None
        self.jarvis_msg_id = None
        self.pending_tools = 0
        self.live_ok = None
        self.live_error = ""
        self.models_ready = None
        self.window = None
        self._hidden_for_capture = False
        self.weather = None
        self.card_open = False
        self.boot_ts = time.time()
        self.watch_on = False
        self.last_stats = {}
        self.game_since = 0.0
        self._gpu_hot = 0
        self._busy_gpu = []
        self._said = {}          # ключ предупреждения → когда говорили
        self._pending_say = []   # предупреждения, отложенные до конца реплики
        self.telegram = None
        from .updater import Updater
        self.updater = Updater(self)
        from .license import License
        self.license = License(self.cfg)
        self._briefing_due = False
        self._watch_task = None

    # ════════════════════════ запуск ════════════════════════
    async def run(self, open_window=True):
        self.loop = asyncio.get_running_loop()
        self.session_lock = asyncio.Lock()
        self.models_ready = asyncio.Event()
        self.mic_q = asyncio.Queue(maxsize=400)
        self.http = aiohttp.ClientSession()
        self.store.listeners.append(lambda: self.loop.call_soon_threadsafe(self._push_store))

        from .server import start_server
        self.port = await start_server(self)

        self.audio.start()
        self.wake = Wake(self.cfg, self._on_wake_thread)
        self.audio.consumers.append(self._on_frame)
        asyncio.create_task(self._init_models())
        asyncio.create_task(self._push_when_indexed())
        for coro in (self._levels_loop(), self._stats_loop(), self._weather_loop(), self._timers_loop(), self._idle_loop(),
                     self._proactive_loop(), self._update_loop(), self._license_loop()):
            asyncio.create_task(coro)
        self.restart_telegram()
        from .desktop import start_hotkey, start_tray, open_window as ow
        start_hotkey(self)
        start_tray(self)
        if open_window and self.cfg.get("open_window_on_start", True):
            ow(self.port)
        self.set_state("idle" if self.cfg.get("gemini_api_key") else "nokey")
        log.info("Джарвис запущен на порту %s", self.port)
        while True:
            await asyncio.sleep(3600)

    async def _push_when_indexed(self):
        for _ in range(120):
            await asyncio.sleep(2)
            if self.apps.ready.is_set() and self.apps.files:
                break
        self.push_settings()

    async def _init_models(self):
        if not self.cfg.get("gemini_api_key"):
            self.models_ready.set()
            return
        try:
            await asyncio.to_thread(self.gemini.refresh_models)
            self.live_ok = bool(self.gemini.live_models)
        except PermissionError as e:
            self.live_error = str(e)
            self.set_state("nokey", str(e))
        except Exception as e:
            self.live_error = f"нет связи с Gemini: {e}"
            log.warning(self.live_error)
        self.models_ready.set()
        self.push_settings()

    # ════════════════════════ аудио-поток (вызывается из потока звука) ════════════════════════
    def headphones(self):
        return bool(self.cfg.get("headphones")) or (self.cfg.get("headphones_auto", True) and self.audio.spk_is_headset)

    def _gated(self):
        return (not self.headphones()) and self.audio.recently_played(0.35)

    def _on_frame(self, fr, level):
        voice = self.audio.is_voice(level)
        listen_wake = self.mic_enabled and self.wake and (
            self.session is None or (self.state == "speaking" and not self.headphones()))
        if self.wake:
            self.wake.enabled = bool(listen_wake)
            self.wake.feed(fr, level, voice)
        if self.capturing and self.mic_enabled:
            gated = self._gated()
            data = (np.zeros_like(fr) if gated else fr).tobytes()
            if voice and not gated:
                self.last_activity = time.time()
            try:
                self.loop.call_soon_threadsafe(self._mic_put, data)
            except RuntimeError:
                pass

    def _mic_put(self, data):
        if self.mic_q.full():
            try:
                self.mic_q.get_nowait()
            except Exception:
                pass
        self.mic_q.put_nowait(data)

    def _on_wake_thread(self, rest=None):
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.activate("wake", rest)))

    # ════════════════════════ состояние / интерфейс ════════════════════════
    def set_state(self, state, detail=""):
        self.state, self.state_detail = state, detail
        self.broadcast({"t": "state", "state": state, "detail": detail})

    def broadcast(self, msg):
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            if ws.closed:
                self.clients.discard(ws)
                continue
            asyncio.ensure_future(self._send_ws(ws, data)) if self.loop and self.loop.is_running() else None

    @staticmethod
    async def _send_ws(ws, data):
        try:
            await ws.send_str(data)
        except Exception:
            pass

    def _threadsafe(self, msg):
        if self.loop:
            self.loop.call_soon_threadsafe(self.broadcast, msg)

    @property
    def lang(self):
        return self.cfg.get("ui_language") or "en"

    def tr(self, text):
        from .i18n import tr
        return tr(text, self.lang)

    def toast(self, text):
        self._threadsafe({"t": "toast", "text": self.tr(text)})

    def ui_card(self, title, content, kind="info"):
        self.card_open = True
        self._threadsafe({"t": "card", "title": title, "content": content, "kind": kind,
                          "autoclose": int(self.cfg.get("card_autoclose", 0) or 0)})

    def ui_close(self, what="all"):
        if what in ("card", "all"):
            self.card_open = False
        self._threadsafe({"t": "close", "what": what})

    def ui_shutdown(self, seconds, action):
        self._threadsafe({"t": "shutdown", "seconds": seconds, "action": action})

    def push_weather(self, d):
        self.weather = d
        self._threadsafe({"t": "weather", "data": d})

    def _push_store(self):
        self.broadcast({"t": "store", "data": self.store.snapshot()})

    def push_settings(self):
        self.broadcast({"t": "settings", "data": self.settings_payload()})

    def settings_payload(self):
        from .brand import name as brand_name
        from .config import PERSONAS, TOOL_GROUPS
        from .desktop import autostart_enabled
        return {"brand": brand_name(self.lang), "config": self.cfg.public(), "voices": VOICES, "devices": list_devices(),
                "personas": PERSONAS, "tool_groups": {k: v[0] for k, v in TOOL_GROUPS.items()},
                "autostart_real": autostart_enabled(), "hotkey_ok": getattr(self, "hotkey_ok", True),
                "apps_indexed": len(self.apps.index), "files_indexed": len(self.apps.files),
                "all_text_models": self.gemini.text_models,
                "live_models": self.gemini.live_models, "live_model": self.gemini.pick_live(),
                "text_models": self.gemini.text_models[:5],
                "wake": {"engine": self.wake.engine if self.wake else "off", "status": self.wake.status if self.wake else ""},
                "mic": {"ok": self.audio.mic_ok, "name": self.audio.mic_name},
                "speaker": {"ok": self.audio.spk_ok, "name": self.audio.spk_name, "headset": self.audio.spk_is_headset},
                "live_error": self.live_error, "port": getattr(self, "port", 0),
                "telegram": self.tg_status(), "quiet_until": self.store.data.get("quiet_until", 0),
                "watch": self.watch_on, "gaming_since": self.game_since, "update": self.updater.info,
                "license": self.license.info()}

    def snapshot(self):
        from .updater import current_version
        return {"t": "snapshot", "version": current_version(), "state": self.state, "detail": self.state_detail, "store": self.store.snapshot(),
                "weather": self.weather, "settings": self.settings_payload(),
                "history": self.store.recent_history(max_age=24 * 3600, n=30), "boot": time.time() - self.boot_ts}

    def on_settings_changed(self):
        self.loop.call_soon_threadsafe(self.push_settings)

    def hide_window_for_capture(self, hide):
        self._threadsafe({"t": "capture", "hide": hide})
        from .desktop import set_window_visible
        set_window_visible(not hide)

    def later(self, delay, fn):
        threading.Timer(delay, fn).start()

    def request_end(self):
        self.end_requested = True

    def _msg(self, role, text, mid, final=False):
        self.broadcast({"t": "msg", "role": role, "text": text, "id": mid, "final": final})

    # ════════════════════════ сессия ════════════════════════
    def build_setup(self, briefing=True):
        n = dt.datetime.now()
        now = f"{WEEKDAYS[n.weekday()]}, {n.day} {MONTHS_GEN[n.month - 1]} {n.year}, {n:%H:%M}"
        facts = [m["fact"] for m in self.store.snapshot()["memory"]]
        memory = ("- What you know about the user (they asked you to remember):\n" + "\n".join(f"  • {f}" for f in facts[-40:]) + "\n") if facts else ""
        hist = self.store.recent_history()
        history = ("- Recent conversation (for context):\n" + "\n".join(
            f"  {'User' if h['r'] == 'user' else 'You'}: {h['t']}" for h in hist) + "\n") if hist else ""
        rs = self.store.snapshot()["routines"]
        routines = ("- Saved routines: " + "; ".join(
            f"«{r['name']}» ({', '.join(self.tools.describe_step(x) for x in r['steps'][:6])})" for r in rs) + "\n") if rs else ""
        briefing = self._briefing_block(n) if briefing and self.pro else ""
        prompt = build_prompt(self.cfg, now, memory, history, routines, briefing, pro=self.pro)
        return {
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.cfg.get("voice", "Charon")}}}},
            "systemInstruction": {"parts": [{"text": prompt}]},
            "tools": [{"functionDeclarations": self.tools.declarations()}],
            "inputAudioTranscription": {}, "outputAudioTranscription": {},
            "realtimeInputConfig": {"automaticActivityDetection": {"silenceDurationMs": int(self.cfg.get("vad_silence_ms", 650)), "prefixPaddingMs": 200}},
            "contextWindowCompression": {"slidingWindow": {}},
        }

    async def activate(self, source="wake", rest=None):
        """Слово активации / горячая клавиша / клик по реактору. rest — команда, сказанная сразу после «Джарвис»."""
        if self.state in ("nokey",):
            self.toast("Нужен ключ Gemini — откройте настройки ⚙")
            return
        if self.session and self.session.alive:
            if self.state == "speaking" or self.audio.playing:
                # перебили Джарвиса
                self.audio.clear()
                self.drop_audio = True
                self.last_activity = time.time()
                self.set_state("listening")
                self.audio.chime("tick")
                if rest:
                    await self._send_user_text(rest)
            elif source == "hotkey":
                await self.end_session("hotkey")
            return
        ok = await self.start_session(chime=True)
        if ok and rest:
            await self._send_user_text(rest)

    async def _send_user_text(self, text):
        mid = uuid.uuid4().hex[:8]
        self._msg("user", text, mid, True)
        self.store.add_history("user", text)
        if self.session:
            await self.session.send_text(text)
            self.set_state("thinking")

    async def start_session(self, chime=True, initial_text=None, silent_fail=False, briefing=True):
        async with self.session_lock:
            if self.session and self.session.alive:
                if initial_text:
                    await self.session.send_text(initial_text)
                return True
            if not self.cfg.get("gemini_api_key"):
                self.set_state("nokey")
                return False
            self.set_state("connecting")
            if chime:
                self.audio.chime("on")
            # подготовка микрофона: начинаем копить кадры сразу (+ небольшой «хвост» до активации)
            while not self.mic_q.empty():
                self.mic_q.get_nowait()
            for fr in list(self.audio.preroll)[-4:]:
                self._mic_put(fr.tobytes())
            self.capturing = True
            self.drop_audio = False
            self.end_requested = False
            self.last_activity = time.time()
            if not self.models_ready.is_set():
                try:
                    await asyncio.wait_for(self.models_ready.wait(), 8)
                except asyncio.TimeoutError:
                    pass
            models = [self.gemini.pick_live()] + [m for m in self.gemini.live_models if m != self.gemini.pick_live()]
            setup = self.build_setup(briefing)
            err = ""
            for model in models[:3]:
                sess = LiveSession(self.cfg["gemini_api_key"].strip(), model, setup, self._on_live_event, self.http)
                try:
                    await sess.connect()
                    self.session = sess
                    self.live_ok, self.live_error = True, ""
                    break
                except (LiveError, aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                    err = str(e)
                    log.warning("Live %s не подключился: %s", model, err)
            if not self.session or not self.session.alive:
                self.capturing = False
                self.live_error = err or "Live API недоступен"
                self.set_state("error", "Нет связи с Gemini Live: " + self.live_error[:120])
                if not silent_fail:
                    self.audio.chime("off")
                asyncio.create_task(self._reset_error_state())
                return False
            asyncio.create_task(self._mic_sender(self.session))
            if briefing and self._briefing_due:
                self.store.set_meta("last_briefing", dt.date.today().isoformat())
                self._briefing_due = False
            self.set_state("listening")
            if initial_text:
                await self.session.send_text(initial_text)
            return True

    async def _reset_error_state(self):
        await asyncio.sleep(6)
        if self.state == "error":
            self.set_state("idle")

    async def _mic_sender(self, sess):
        while sess.alive:
            try:
                data = await asyncio.wait_for(self.mic_q.get(), 1.0)
            except asyncio.TimeoutError:
                continue
            # склеиваем накопленные кадры, чтобы не отправлять сотни мелких сообщений
            chunks = [data]
            while not self.mic_q.empty() and len(chunks) < 12:
                chunks.append(self.mic_q.get_nowait())
            if not await sess.send_audio(b"".join(chunks)):
                break

    async def end_session(self, reason=""):
        sess = self.session
        self.session = None
        self.capturing = False
        if self.watch_on:
            self.set_watch(False)
        self._finalize_msgs()
        if sess:
            await sess.close()
            log.info("Сессия завершена: %s", reason)
        if self.state not in ("nokey", "error"):
            self.set_state("idle")
        self.audio.chime("off")

    def _finalize_msgs(self):
        if self.user_buf.strip():
            self.store.add_history("user", self.user_buf)
            self._msg("user", self.user_buf.strip(), self.user_msg_id, True)
        if self.jarvis_buf.strip():
            self.store.add_history("jarvis", self.jarvis_buf)
            self._msg("jarvis", self.jarvis_buf.strip(), self.jarvis_msg_id, True)
        self.user_buf = self.jarvis_buf = ""
        self.user_msg_id = self.jarvis_msg_id = None

    async def _on_live_event(self, kind, data):
        sess_alive = self.session is not None
        if kind == "audio":
            if self.drop_audio:
                return
            self.audio.play(data)
            self.last_activity = time.time()
            if self.state != "speaking":
                self.set_state("speaking")
        elif kind == "in_text":
            if self.jarvis_buf.strip():
                # новый вопрос — закрываем прошлый ответ
                self.store.add_history("jarvis", self.jarvis_buf)
                self._msg("jarvis", self.jarvis_buf.strip(), self.jarvis_msg_id, True)
                self.jarvis_buf, self.jarvis_msg_id = "", None
            self.user_msg_id = self.user_msg_id or uuid.uuid4().hex[:8]
            self.user_buf += data
            self.last_activity = time.time()
            self._msg("user", self.user_buf.strip(), self.user_msg_id)
            if self.state == "listening":
                self.set_state("thinking")
        elif kind == "out_text":
            if self.user_buf.strip():
                self.store.add_history("user", self.user_buf)
                self._msg("user", self.user_buf.strip(), self.user_msg_id, True)
                self.user_buf, self.user_msg_id = "", None
            self.jarvis_msg_id = self.jarvis_msg_id or uuid.uuid4().hex[:8]
            self.jarvis_buf += data
            self._msg("jarvis", self.jarvis_buf.strip(), self.jarvis_msg_id)
        elif kind == "interrupted":
            self.audio.clear()
            self.drop_audio = False
            self.set_state("listening")
        elif kind == "turn_complete":
            self.drop_audio = False
            if self.jarvis_buf.strip():
                self.store.add_history("jarvis", self.jarvis_buf)
                self._msg("jarvis", self.jarvis_buf.strip(), self.jarvis_msg_id, True)
                self.jarvis_buf, self.jarvis_msg_id = "", None
            self.last_activity = time.time()
            asyncio.create_task(self._after_turn())
        elif kind == "tool_call":
            self.last_activity = time.time()
            asyncio.create_task(self._run_tools(data))
        elif kind == "go_away":
            log.info("goAway: переподключаюсь")
            asyncio.create_task(self._reconnect())
        elif kind == "closed":
            if sess_alive and self.session is not None and not self.session.alive:
                log.warning("Live закрылась сама: %s", data)
                if "1011" in str(data) or "quota" in str(data).lower():
                    self.toast("Лимит Gemini Live исчерпан — попробуйте позже")
                self.session = None
                self.capturing = False
                if self.watch_on:
                    self.set_watch(False)
                self._finalize_msgs()
                if self.state not in ("nokey",):
                    self.set_state("idle")

    async def _after_turn(self):
        # ждём, пока договорит, затем возвращаемся к слушанию (или завершаем)
        while self.audio.playing:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.15)
        if self.end_requested:
            await self.end_session("end_conversation")
            return
        if self.session and self.pending_tools == 0 and self.state in ("speaking", "thinking"):
            self.set_state("listening")
        self.last_activity = time.time()

    async def _run_tools(self, calls):
        self.pending_tools += 1
        self.set_state("thinking", ", ".join(c.get("name", "") for c in calls))
        try:
            results = await asyncio.gather(*[self._one_tool(c) for c in calls])
            if self.session:
                await self.session.send_tool_responses(results)
        finally:
            self.pending_tools -= 1
            self.last_activity = time.time()

    async def _one_tool(self, c):
        name, args = c.get("name"), c.get("args") or {}
        log.info("TOOL %s %s", name, json.dumps(args, ensure_ascii=False)[:300])
        self.broadcast({"t": "tool", "name": name, "args": args})
        try:
            res = await asyncio.wait_for(asyncio.to_thread(self.tools.call, name, args), 130 if name == "routine_run" else 45)
        except asyncio.TimeoutError:
            res = {"error": "функция выполнялась слишком долго"}
        log.info("TOOL %s → %s", name, json.dumps(res, ensure_ascii=False)[:300])
        if not isinstance(res, dict):
            res = {"result": res}
        out = {"name": name, "response": res}
        if c.get("id"):
            out["id"] = c["id"]
        return out

    async def _reconnect(self):
        old = self.session
        if not old:
            return
        try:
            sess = LiveSession(old.key, old.model, self.build_setup(False), self._on_live_event, self.http)
            sess.resume_handle = old.resume_handle
            await sess.connect()
            self.session = sess
            await old.close()
            asyncio.create_task(self._mic_sender(sess))
        except Exception as e:
            log.warning("reconnect: %s", e)

    # ════════════════════════ текст из интерфейса ════════════════════════
    async def user_text(self, text):
        text = text.strip()
        if not text:
            return
        mid = uuid.uuid4().hex[:8]
        self._msg("user", text, mid, True)
        self.store.add_history("user", text)
        self.audio.clear()
        if self.session and self.session.alive:
            self.drop_audio = False
            await self.session.send_text(text)
            self.set_state("thinking")
        else:
            ok = await self.start_session(chime=False, initial_text=text)
            if ok:
                self.set_state("thinking")
            else:
                await self.classic_answer(text)
        self.last_activity = time.time()

    async def classic_answer(self, text):
        """Запасной путь без Live: текстовая модель + синтез речи."""
        self.set_state("thinking")
        try:
            reply = await asyncio.to_thread(self.gemini.ask, text, build_prompt(
                self.cfg, dt.datetime.now().strftime("%d.%m.%Y %H:%M")))
        except Exception as e:
            reply = f"Нет связи с Gemini: {str(e)[:80]}"
        mid = uuid.uuid4().hex[:8]
        self._msg("jarvis", reply, mid, True)
        await self.say(reply)
        self.set_state("idle")

    async def say(self, text):
        pcm = await asyncio.to_thread(self.gemini.tts, text, self.cfg.get("voice", "Charon"))
        if pcm:
            data, rate = pcm
            if rate != 24000:
                from .audio import resample
                data = resample(np.frombuffer(data, dtype=np.int16), rate, 24000).tobytes()
            self.set_state("speaking")
            self.audio.play(data)
            while self.audio.playing:
                await asyncio.sleep(0.05)

    # ════════════════════════ фоновые циклы ════════════════════════
    async def _levels_loop(self):
        while True:
            await asyncio.sleep(1 / 30)
            if self.clients:
                self.broadcast({"t": "lvl", "i": round(self.audio.in_level, 3), "o": round(self.audio.out_level, 3),
                                "w": round(self.wake.score, 2) if self.wake else 0})

    async def _stats_loop(self):
        while True:
            try:
                s = await asyncio.to_thread(self.stats.snapshot)
                self.last_stats = s
                self.broadcast({"t": "stats", "data": dict(s, gaming_since=self.game_since)})
            except Exception as e:
                log.debug("stats: %s", e)
            await asyncio.sleep(1.5)

    async def _weather_loop(self):
        while True:
            try:
                d = await asyncio.to_thread(self.tools.weather_data, None, 4)
                self.weather = d
                self.broadcast({"t": "weather", "data": d})
                await asyncio.sleep(900)
            except Exception as e:
                log.info("weather: %s", e)
                await asyncio.sleep(120)

    async def _timers_loop(self):
        while True:
            await asyncio.sleep(1)
            for t in self.store.pop_due():
                asyncio.create_task(self._fire_timer(t))

    async def _fire_timer(self, t):
        kind = {"timer": "Таймер", "reminder": "Напоминание", "alarm": "Будильник"}.get(t["kind"], "Таймер")
        label = t.get("label") or ""
        from .brand import name as brand_name
        k_tr, up = self.tr(kind), self.tr("время вышло")
        self.broadcast({"t": "alert", "title": k_tr, "text": label or up})
        from .desktop import notify
        notify(f"{brand_name(self.lang)} · {k_tr}", label or self.tr("Время вышло"))
        self.tg_notify(f"⏰ {k_tr}: {label or up}")
        reps = 3 if t["kind"] == "alarm" else 1
        for _ in range(reps):
            self.audio.chime("alert")
            await asyncio.sleep(1.1)
        msg = f"[СИСТЕМА: сработал {kind.lower()}" + (f" «{label}»" if label else "") + ". Коротко сообщи об этом пользователю.]"
        if self.session and self.session.alive:
            await self.session.send_text(msg)
        else:
            ok = await self.start_session(chime=False, initial_text=msg, silent_fail=True, briefing=False)
            if not ok:
                await self.say(f"{self.cfg.get('user_name', 'сэр').capitalize()}, {kind.lower()}: {label or 'время вышло'}.")

    async def _idle_loop(self):
        while True:
            await asyncio.sleep(0.5)
            s = self.session
            if not s or not s.alive:
                continue
            if self.audio.playing or self.pending_tools:
                self.last_activity = time.time()
                continue
            limit = float(self.cfg.get("watch_idle_timeout", 90) if self.watch_on else self.cfg.get("idle_timeout", 14))
            if time.time() - self.last_activity > limit:
                await self.end_session("тишина")
            elif time.time() - s.started > 14 * 60:
                await self._reconnect()

    # ════════════════════════ утренний брифинг ════════════════════════
    def _briefing_block(self, n):
        self._briefing_due = False
        if not self.cfg.get("morning_briefing", True) or not (5 <= n.hour < 12):
            return ""
        if self.store.data.get("last_briefing") == n.date().isoformat():
            return ""
        self._briefing_due = True
        parts = []
        w = self.weather
        if w and w.get("now"):
            d0 = (w.get("days") or [{}])[0]
            parts.append(f"weather in {w.get('city')}: now {w['now']['temp']}°, {w['now']['desc']}; high {d0.get('max', '?')}°, "
                         f"low {d0.get('min', '?')}°, chance of rain {d0.get('rain', '?')}%")
        snap = self.store.snapshot()
        todo = [t["text"] for t in snap["tasks"] if not t["done"]][:5]
        if todo:
            parts.append("open tasks: " + "; ".join(todo))
        end = dt.datetime.combine(n.date(), dt.time(23, 59)).timestamp()
        today = [t for t in snap["timers"] if t["due"] <= end and t["kind"] in ("reminder", "alarm")]
        if today:
            parts.append("reminders today: " + "; ".join(
                f"{dt.datetime.fromtimestamp(t['due']):%H:%M} {t['label'] or ''}".strip() for t in today[:5]))
        if not parts:
            parts.append("nothing special planned")
        return ("- MORNING BRIEFING: this is the first conversation today. If the user greets you or asks something general — "
                "wish them a good morning and give a briefing in 2–4 short sentences. If they gave a specific command — do it first, "
                "then give the briefing in one or two sentences. Data: " + " | ".join(parts) + "\n")

    # ════════════════════════ режим «вижу экран» ════════════════════════
    def set_watch(self, on):
        """Можно вызывать из любого потока."""
        if on and not self.pro:
            return {"error": "«Вижу экран» — функция Pro (Настройки → Pro)"}
        if on and not (self.session and self.session.alive):
            return {"error": "этот режим работает во время разговора"}
        self.watch_on = bool(on)
        self._threadsafe({"t": "watch", "on": self.watch_on})
        if on:
            self.loop.call_soon_threadsafe(self._start_watch_task)
            return {"ok": True, "note": f"кадры экрана приходят каждые {self.cfg.get('watch_interval', 2.0)} с, пока идёт разговор; "
                                        "отвечай по ним, не вызывай look_at_screen"}
        return "режим «вижу экран» выключен"

    def _start_watch_task(self):
        if self._watch_task and not self._watch_task.done():
            return
        self._watch_task = asyncio.create_task(self._watch_loop())

    def _grab_frame(self):
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=False)
        img.thumbnail((1280, 1280))
        b = io.BytesIO()
        img.convert("RGB").save(b, "JPEG", quality=68)
        return b.getvalue()

    async def _watch_loop(self):
        log.info("вижу экран: вкл")
        frames = 0
        while self.watch_on and self.session and self.session.alive:
            t0 = time.time()
            try:
                jpg = await asyncio.to_thread(self._grab_frame)
                if self.session and await self.session.send_image(jpg):
                    frames += 1
            except Exception as e:
                log.warning("watch: %s", e)
            await asyncio.sleep(max(0.3, float(self.cfg.get("watch_interval", 2.0)) - (time.time() - t0)))
        if self.watch_on:
            self.watch_on = False
            self.broadcast({"t": "watch", "on": False})
        log.info("вижу экран: выкл, кадров %s", frames)

    # ════════════════════════ проактивность ════════════════════════
    def quiet(self):
        return float(self.store.data.get("quiet_until", 0) or 0) > time.time()

    async def _proactive_loop(self):
        await asyncio.sleep(45)
        while True:
            try:
                await self._proactive_check()
                await self._flush_pending()
            except Exception:
                log.exception("proactive")
            await asyncio.sleep(20)

    async def _proactive_check(self):
        from . import winsys
        s, now = self.last_stats or {}, time.time()
        g = s.get("gpu") or {}
        util = float(g.get("util", 0) or 0)
        # игра = видеокарта загружена в среднем ≥45% последние ~3 минуты
        self._busy_gpu = [(t, u) for t, u in self._busy_gpu if now - t < 180] + [(now, util)]
        if util >= 40:
            self._last_busy = now
        avg = sum(u for _, u in self._busy_gpu) / len(self._busy_gpu)
        span = now - self._busy_gpu[0][0]
        if avg >= 45 and span >= 150 and not self.game_since:
            self.game_since = self._busy_gpu[0][0]
            self.game_proc = await asyncio.to_thread(winsys.foreground_process)
            log.info("похоже, началась игра: %s", self.game_proc)
        elif self.game_since and now - getattr(self, "_last_busy", 0) > 300:
            log.info("игра закончилась (%.0f мин)", (now - self.game_since) / 60)
            self.game_since = 0.0
            self._said.pop("game_long", None)
        if not self.cfg.get("proactive", True) or not self.pro:
            return
        temp = float(g.get("temp", 0) or 0)
        self._gpu_hot = self._gpu_hot + 1 if temp >= int(self.cfg.get("proactive_gpu_temp", 87)) else 0
        if self._gpu_hot >= 3:
            self.announce("gpu_hot", 1200, f"🔥 Видеокарта {temp:.0f}°C",
                          f"видеокарта нагрелась до {temp:.0f} градусов и держится так уже минуту. Предложи проверить охлаждение, "
                          "поставить ноутбук на подставку или снизить графику/ограничить FPS")
        b = s.get("battery")
        if b is not None:
            if s.get("plugged"):
                self._said.pop("battery", None)
                self._said.pop("battery_crit", None)
            elif b <= 5:
                self.announce("battery_crit", 10 ** 9, f"🪫 Батарея {b}%", f"батарея почти села — {b} процентов. Срочно подключить зарядку")
            elif b <= int(self.cfg.get("proactive_battery", 15)):
                self.announce("battery", 10 ** 9, f"🔋 Батарея {b}%", f"заряд батареи {b} процентов, зарядка не подключена")
        free = s.get("disk_free")
        if free is not None and free < int(self.cfg.get("proactive_disk_gb", 10)):
            self.announce("disk", 86400, f"💾 Мало места: {free} ГБ",
                          f"на системном диске осталось всего {free} гигабайт. Предложи очистить корзину, загрузки или временные файлы")
        hours = float(self.cfg.get("proactive_game_hours", 2.0) or 0)
        if hours and self.game_since and now - self.game_since >= hours * 3600:
            played = int((now - self.game_since) / 60)
            self.announce("game_long", 3600, f"🎮 Играете {played // 60} ч {played % 60} мин",
                          f"пользователь играет уже {played // 60} ч {played % 60} мин подряд"
                          + (f" (процесс {self.game_proc})" if getattr(self, "game_proc", "") else "")
                          + ". Ненавязчиво, с юмором предложи короткий перерыв: размяться, попить воды")
        h = dt.datetime.now().hour
        if self.cfg.get("proactive_night", True) and self.game_since and 1 <= h < 5:
            self.announce("night", 6 * 3600, "🌙 Уже глубокая ночь",
                          f"сейчас {dt.datetime.now():%H:%M}, а пользователь всё ещё играет. Мягко, по-дружески напомни про сон, без нотаций")

    def announce(self, key, cooldown, short, text):
        now = time.time()
        if now - self._said.get(key, 0) < cooldown:
            return
        self._said[key] = now
        log.info("проактивно [%s]: %s", key, short)
        self.toast(short)
        if self.cfg.get("telegram_notify", True):
            self.tg_notify(self.tr(short))
        if self.quiet() or not self.cfg.get("proactive_voice", True):
            from .desktop import notify
            from .brand import name as brand_name
            notify(brand_name(self.lang), self.tr(short))
            return
        self._pending_say.append(text)

    async def _flush_pending(self):
        if not self._pending_say:
            return
        busy = self.state in ("thinking", "speaking", "connecting") or self.pending_tools or self.audio.playing \
            or (self.session and time.time() - self.last_activity < 3)
        if busy:
            return
        text = "; ".join(self._pending_say)
        self._pending_say.clear()
        msg = f"[СИСТЕМА: проактивное наблюдение — {text}. Скажи это пользователю сам, коротко (1–2 фразы), по-человечески.]"
        if self.session and self.session.alive:
            await self.session.send_text(msg)
            self.set_state("thinking")
        else:
            await self.start_session(chime=True, initial_text=msg, silent_fail=True, briefing=False)

    # ════════════════════════ лицензия ════════════════════════
    @property
    def pro(self):
        return self.license.pro

    async def _license_loop(self):
        while True:
            was = self.pro
            try:
                await asyncio.to_thread(self.license.refresh)
            except Exception:
                log.exception("license")
            if was != self.pro:
                self.on_license_changed()
            await asyncio.sleep(6 * 3600)

    def on_license_changed(self):
        if not self.pro and self.watch_on:
            self.set_watch(False)
        self.restart_telegram()
        self.push_settings()

    # ════════════════════════ обновления ════════════════════════
    def push_update(self):
        self._threadsafe({"t": "update", "data": self.updater.info})

    async def _update_loop(self):
        await asyncio.sleep(8)
        r = self.updater.pop_result()
        if r:
            if r.get("ok"):
                txt = f"Обновлено до версии {r['new']} ✓"
            else:
                txt = f"Обновление до {r['new']} не удалось ({r.get('error', '')[:80]}) — вернул версию {r['old']}"
            log.info(txt)
            self.toast(txt)
            self.tg_notify(("⬆ " if r.get("ok") else "⚠ ") + self.tr(txt))
            if r.get("ok") and self.cfg.get("sounds", True):
                self.audio.chime("on")
        notified = ""
        while True:
            if self.cfg.get("update_auto_check", True):
                info = await asyncio.to_thread(self.updater.check)
                self.push_update()
                if info.get("available") and info.get("latest") != notified:
                    notified = info["latest"]
                    self.toast(f"⬆ Доступна новая версия {info['latest']} — кнопка вверху")
                    self.tg_notify(self.tr(f"⬆ Доступна новая версия {info['latest']} — кнопка вверху") + f"\n{info.get('notes', '')[:600]}")
            await asyncio.sleep(6 * 3600)

    # ════════════════════════ телефон ════════════════════════
    def tg_notify(self, text):
        if self.telegram:
            self.telegram.notify(text)

    def restart_telegram(self):
        from .telegram import TelegramBot
        if self.telegram:
            self.telegram.stop()
            self.telegram = None
        if self.cfg.get("telegram_enabled") and (self.cfg.get("telegram_token") or "").strip() and self.pro:
            self.telegram = TelegramBot(self)
            self.telegram.start()

    def tg_status(self):
        if not self.cfg.get("telegram_enabled"):
            return {"on": False}
        if not self.pro:
            return {"on": True, "error": "Telegram-бот — функция Pro (Настройки → Pro)"}
        if not self.telegram:
            return {"on": True, "error": "нет токена бота"}
        return self.telegram.status()

    # ════════════════════════ команды из интерфейса ════════════════════════
    async def handle_ui(self, msg):
        t = msg.get("t")
        if t == "text":
            await self.user_text(msg.get("text", ""))
        elif t == "activate":
            await self.activate("click")
        elif t == "stop":
            self.audio.clear()
            if self.session:
                await self.end_session("stop")
        elif t == "mic":
            self.mic_enabled = bool(msg.get("on", True))
            self.broadcast({"t": "mic", "on": self.mic_enabled})
        elif t == "settings":
            await self.apply_settings(msg.get("data") or {}, silent=bool(msg.get("silent")))
        elif t == "key_check":
            key = (msg.get("key") or "").strip()
            ok, err = await asyncio.to_thread(self._check_key, key)
            if ok:
                await self.apply_settings({"gemini_api_key": key}, silent=True)
            self.broadcast({"t": "key_check", "ok": ok, "error": err})
        elif t == "timer_cancel":
            self.store.cancel_timer(tid=msg.get("id"))
        elif t == "task_add":
            self.store.add_task(msg.get("text", ""))
        elif t == "task_toggle":
            for x in self.store.snapshot()["tasks"]:
                if x["id"] == msg.get("id"):
                    self.store.set_task(tid=x["id"], done=not x["done"])
        elif t == "task_delete":
            self.store.set_task(tid=msg.get("id"), delete=True)
        elif t == "memory_delete":
            with self.store.lock:
                self.store.data["memory"] = [m for m in self.store.data["memory"] if m["id"] != msg.get("id")]
            self.store.save()
        elif t == "card_closed":
            self.card_open = False
        elif t == "cancel_shutdown":
            await asyncio.to_thread(self.tools.t_power, "cancel_shutdown")
        elif t == "memory_add":
            if (msg.get("text") or "").strip():
                self.store.remember(msg["text"].strip())
        elif t == "memory_edit":
            with self.store.lock:
                for m in self.store.data["memory"]:
                    if m["id"] == msg.get("id"):
                        m["fact"] = (msg.get("text") or m["fact"]).strip()
            self.store.save()
        elif t == "memory_clear":
            with self.store.lock:
                self.store.data["memory"] = []
            self.store.save()
        elif t == "notes_delete":
            with self.store.lock:
                self.store.data["notes"] = [n for n in self.store.data["notes"] if n["id"] != msg.get("id")]
            self.store.save()
        elif t == "history_clear":
            with self.store.lock:
                self.store.data["history"] = []
            self.store.save()
            self.toast("История разговоров очищена")
        elif t == "find_app":
            q = (msg.get("q") or "").strip()
            from .util import norm
            found = self.apps.find_installed(norm(q)) if q else None
            self.broadcast({"t": "find_app", "q": q, "found": found[1] if found else None,
                            "score": round(found[0], 2) if found else 0})
        elif t == "test_sound":
            self.audio.chime("on")
        elif t == "open_path":
            from . import winsys
            what = msg.get("what")
            target = {"folder": str(BASE), "log": str(BASE / "jarvis.log"), "data": str(BASE / "data"),
                      "screenshots": str(self.apps.folder_path("SCREENSHOTS"))}.get(what)
            if target:
                winsys.open_path(target)
        elif t == "selftest":
            asyncio.create_task(self._run_selftest(msg.get("full", True), msg.get("only")))
        elif t == "restart":
            self.toast("Перезапуск…")
            await asyncio.sleep(0.4)
            from .desktop import restart_jarvis
            restart_jarvis()
        elif t == "quit":
            import os
            os._exit(0)
        elif t == "routine_run":
            r = self.store.find_routine(msg.get("id") or "")
            if r:
                res = await asyncio.to_thread(self.tools.call, "routine_run", {"name": r["id"]})
                if res.get("error") != "pro_only":
                    self.toast(f"⚙ «{r['name']}»: выполнено {len(res.get('done', []))}" +
                               (f", ошибки: {'; '.join(res['errors'])[:120]}" if res.get("errors") else ""))
        elif t == "routine_delete":
            self.store.delete_routine(msg.get("id") or "")
        elif t == "routine_save":
            d = msg.get("data") or {}
            res = await asyncio.to_thread(self.tools.call, "routine_save", {"name": d.get("name", ""), "steps": d.get("steps", []),
                                                                           "description": d.get("description", "")})
            if isinstance(res, dict) and res.get("error") and res["error"] != "pro_only":
                self.toast("Режим не сохранён: " + "; ".join([res["error"]] + res.get("problems", [])))
        elif t == "quiet":
            await asyncio.to_thread(self.tools.call, "quiet_mode", {"minutes": msg.get("minutes", 60), "off": not msg.get("on", True)})
        elif t == "license_activate":
            info = await asyncio.to_thread(self.license.activate, msg.get("key", ""))
            self.toast("⭐ Pro активирован" + (f": {info['name']}" if info.get("name") else "") if info["pro"]
                       else ("Ключ удалён — бесплатная версия" if not info["has_key"] else "Ключ не принят: " + info.get("error", "")))
            self.on_license_changed()
        elif t == "watch" and msg.get("on") and not self.pro:
            self.toast("⭐ «Вижу экран» — функция Pro (Настройки → Pro)")
        elif t == "watch":
            if msg.get("on"):
                if not (self.session and self.session.alive):
                    await self.start_session(chime=True, briefing=False)
                r = self.set_watch(True)
                if isinstance(r, dict) and r.get("error"):
                    self.toast(r["error"])
                elif self.session:
                    await asyncio.sleep(1.5)  # пусть дойдёт первый кадр
                    await self.session.send_text("[СИСТЕМА: пользователь включил режим «вижу экран» кнопкой — тебе приходят "
                                                 "кадры его экрана. Скажи одной короткой фразой, что видишь экран и готов помогать.]")
            else:
                self.set_watch(False)
        elif t == "tg_unlink":
            self.cfg["telegram_chat_id"] = 0
            self.cfg.save()
            self.restart_telegram()
            self.push_settings()
        elif t == "tg_test":
            if self.telegram and self.cfg.get("telegram_chat_id"):
                from .i18n import ui as uistr
                self.telegram.notify("✅ " + uistr("py.tg_test_msg", self.lang))
                self.toast("Отправил тестовое сообщение в Telegram")
            else:
                self.toast("Сначала привяжите бота (код в настройках)")
        elif t == "update_check":
            await asyncio.to_thread(self.updater.check)
            self.push_update()
        elif t == "update_install":
            if self.session:
                await self.end_session("update")
            res = await asyncio.to_thread(self.updater.install)
            if res.get("error"):
                self.toast("Обновление: " + res["error"])
        elif t == "test_voice":
            await self.start_session(chime=True, briefing=False,
                                     initial_text="[СИСТЕМА: пользователь проверяет голос. Поздоровайся одной фразой.]")

    async def _refresh_weather(self):
        try:
            d = await asyncio.to_thread(self.tools.weather_data, None, 4)
            self.weather = d
            self.broadcast({"t": "weather", "data": d})
        except Exception as e:
            self.toast(f"Погода: {e}")

    def _check_key(self, key):
        """Проверка ключа Gemini из мастера первого запуска: список моделей."""
        import requests
        if not key:
            return False, "empty"
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key},
                             params={"pageSize": 5}, timeout=15)
            if r.status_code == 200:
                return True, ""
            try:
                return False, (r.json().get("error") or {}).get("message", f"HTTP {r.status_code}")[:160]
            except Exception:
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)[:160]

    async def apply_settings(self, data, silent=False):
        from .config import coerce
        changed, errors = [], []
        for k, v in data.items():
            if k in ("gemini_api_key", "telegram_token"):
                v = (v or "").strip()
                if v and v != self.cfg.get(k):
                    self.cfg[k] = v
                    changed.append(k)
                    if k == "telegram_token":
                        self.cfg["telegram_chat_id"] = 0  # новый бот — новая привязка
                continue
            try:
                nv = coerce(k, v)
            except Exception as e:
                errors.append(str(e))
                continue
            if self.cfg.get(k) != nv:
                self.cfg[k] = nv
                changed.append(k)
        self.cfg.save()
        notes = []
        if "gemini_api_key" in changed or "live_model" in changed or "text_model" in changed:
            self.models_ready.clear()
            asyncio.create_task(self._init_models())
            if self.state == "nokey":
                self.set_state("idle")
        if {"mic_device", "speaker_device"} & set(changed):
            await asyncio.to_thread(self.audio.restart)
        if {"wake_engine", "wake_word", "ui_language"} & set(changed):
            self.audio.consumers.clear()
            self.wake = await asyncio.to_thread(Wake, self.cfg, self._on_wake_thread)
            self.audio.consumers.append(self._on_frame)
        if "hotkey" in changed:
            from .desktop import start_hotkey
            start_hotkey(self)
        if "autostart" in changed or ("autostart_window" in changed and self.cfg.get("autostart")):
            from .desktop import set_autostart
            ok = await asyncio.to_thread(set_autostart, bool(self.cfg.get("autostart")))
            if not ok:
                errors.append("не удалось настроить автозапуск")
        if "city" in changed:
            self.tools._weather_cache.clear()
            self.tools._home = None
            asyncio.create_task(self._refresh_weather())
        if "port" in changed:
            notes.append("порт сменится после перезапуска")
        if {"telegram_enabled", "telegram_token"} & set(changed):
            self.restart_telegram()
            await asyncio.sleep(1.5)  # чтобы в настройках сразу появилось имя бота
        live_keys = {"voice", "persona", "custom_instructions", "reply_length", "reply_language", "user_name",
                     "vad_silence_ms", "tools_disabled", "confirm_dangerous", "live_model"}
        if self.session and (live_keys & set(changed)):
            notes.append("часть изменений применится со следующего разговора")
        self.push_settings()
        if silent and not errors:
            return
        msg = self.tr("Настройки сохранены") if changed else self.tr("Ничего не изменилось")
        if notes:
            msg += " — " + "; ".join(self.tr(n) for n in notes)
        if errors:
            msg += ". ⚠ " + "; ".join(errors)
        self._threadsafe({"t": "toast", "text": msg})

    async def _run_selftest(self, full=True, only=None):
        import subprocess
        import sys
        py = BASE / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            py = sys.executable
        args = [str(py), str(BASE / "selftest.py")] + ([] if full else ["--quick"])
        if only in ("click", "new", "watch", "update", "i18n"):
            args += ["--only", only]
        self.broadcast({"t": "selftest", "line": "▶ Запускаю самопроверку…", "start": True})
        env = dict(__import__("os").environ, PYTHONIOENCODING="utf-8")
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                    cwd=str(BASE), env=env, creationflags=0x08000000)
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            self.broadcast({"t": "selftest", "line": line.decode("utf-8", "replace").rstrip()})
        await proc.wait()
        self.broadcast({"t": "selftest", "line": "■ Готово", "done": True})
