# -*- coding: utf-8 -*-
"""Самопроверка Джарвиса: окружение, звук, слово активации, Gemini Live с настоящими инструментами, сами инструменты.
Результат: data/selftest_report.txt (и .json). Запуск: selftest.bat  (или --quick без Live)."""
import asyncio
import base64
import json
import sys
import time
import traceback
import wave
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
REPORT = BASE / "data" / "selftest_report.txt"
REPORT.parent.mkdir(exist_ok=True)
results = []


def rec(name, ok, info=""):
    mark = "OK  " if ok is True else ("WARN" if ok is None else "FAIL")
    results.append({"test": name, "ok": ok, "info": str(info)[:900]})
    line = f"[{mark}] {name}: {str(info)[:300]}"
    print(line, flush=True)
    REPORT.write_text("\n".join(f"[{'OK  ' if r['ok'] is True else ('WARN' if r['ok'] is None else 'FAIL')}] {r['test']}: {r['info']}" for r in results), encoding="utf-8")


def step(name):
    def deco(fn):
        def run(*a, **k):
            t = time.time()
            try:
                r = fn(*a, **k)
                if isinstance(r, tuple):
                    rec(name, r[0], f"{r[1]}  ({time.time()-t:.1f}s)")
                else:
                    rec(name, True, f"{r}  ({time.time()-t:.1f}s)")
            except Exception as e:
                rec(name, False, f"{e!r} | {traceback.format_exc().splitlines()[-3:]}")
        return run
    return deco


QUICK = "--quick" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
rec("python", True, sys.version.split()[0] + " " + sys.executable)

# ── импорты ──
for mod in ["aiohttp", "requests", "numpy", "sounddevice", "psutil", "PIL", "pycaw", "comtypes", "pystray", "onnxruntime", "scipy"]:
    try:
        m = __import__(mod)
        rec(f"import {mod}", True, getattr(m, "__version__", ""))
    except Exception as e:
        rec(f"import {mod}", mod not in ("aiohttp", "numpy", "sounddevice", "requests") and None, repr(e))

from core.config import Config  # noqa
cfg = Config()


@step("audio devices")
def t_devices():
    import sounddevice as sd
    d = sd.query_devices()
    di, do = sd.default.device
    return f"in={d[di]['name'] if di is not None and di >= 0 else None} | out={d[do]['name'] if do is not None and do >= 0 else None} | всего {len(d)}"


@step("microphone level (2 s)")
def t_mic():
    import numpy as np
    import sounddevice as sd
    x = sd.rec(32000, samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    r = float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))
    peak = int(np.abs(x).max())
    ok = True if peak > 30 else None
    return ok, f"rms={r:.0f} peak={peak} (тишина ≈ 20–300; речь ≈ 1000+)"


@step("wake word: hybrid on synthetic samples")
def t_wake():
    import numpy as np
    from core.audio import resample
    from core.wake import Wake
    fired = []
    w = Wake(cfg, lambda rest: fired.append(rest))
    if w.engine == "off":
        return False, w.status
    out = {"engine": w.engine}
    T = BASE / "data" / "test"
    samples = sorted((T / "wake_samples").glob("*.wav"))[:6] + [T / "wake.wav", T / "q.wav"]
    for p in samples:
        if not p.exists():
            continue
        with wave.open(str(p)) as f:
            pcm, sr = f.readframes(f.getnframes()), f.getframerate()
        x = resample(np.frombuffer(pcm, dtype=np.int16), sr, 16000)
        x = np.concatenate([np.zeros(8000, np.int16), x, np.zeros(16000, np.int16)])
        n0 = len(fired)
        best = 0.0
        w._last = 0
        for i in range(0, len(x) - 1280, 1280):
            fr = x[i:i + 1280]
            r = float(np.sqrt(np.mean(fr.astype(np.float32) ** 2)))
            w.feed(fr, r, r > 400)
            best = max(best, w.score)
        for _ in range(40):
            if len(fired) > n0 or (w._q.empty() and not w._busy):
                break
            time.sleep(0.1)
        time.sleep(0.3)
        out[p.name] = {"score": round(best, 3), "fired": len(fired) > n0, "rest": fired[-1] if len(fired) > n0 else None}
    return True, json.dumps(out, ensure_ascii=False)


@step("gemini models")
def t_models():
    from core.gemini import Gemini
    g = Gemini(cfg)
    g.refresh_models()
    globals()["G"] = g
    return bool(g.live_models), f"live={g.live_models[:3]} text={g.text_models[:4]} tts={g.tts_models[:2]}"


@step("tools: weather")
def t_weather(tb):
    d = tb.t_get_weather("", 3)
    return f"{d['city']} {d['now']['temp']}° {d['now']['desc']}, дней {len(d['days'])}"


@step("tools: exchange EUR→UAH")
def t_fx(tb):
    return tb.t_exchange_rate("EUR", "UAH", 100)


@step("tools: system_status")
def t_sys(tb):
    s = tb.t_system_status()
    return {k: s.get(k) for k in ("cpu", "ram", "battery", "disk_free", "gpu")}


@step("tools: volume get")
def t_vol(tb):
    return tb.t_volume("get")


@step("tools: brightness get")
def t_bright(tb):
    return tb.t_brightness()


@step("tools: clipboard roundtrip")
def t_clip(tb):
    from core import winsys
    old = winsys.clipboard_get()
    winsys.clipboard_set("Джарвис тест ✓")
    v = winsys.clipboard_get()
    winsys.clipboard_set(old or "")
    return v == "Джарвис тест ✓", v


@step("tools: calculate / now / windows")
def t_misc(tb):
    return f"{tb.t_calculate('sqrt(16)+2**10*0.5')} | {tb.t_now()} | окон: {len(tb.t_list_windows()['windows'])}"


@step("apps: index + find")
def t_apps(tb):
    tb.apps.ready.wait(60)
    found = {q: (tb.apps.find_installed(q) or (0, None))[1] for q in ["стим", "телеграм", "дискорд", "хром", "калда", "блендер", "нвидиа"]}
    return f"{len(tb.apps.index)} программ; {found}"


@step("files: index + find")
def t_files(tb):
    for _ in range(60):
        if tb.apps.files:
            break
        time.sleep(1)
    return f"{len(tb.apps.files)} файлов; jarvis → {tb.apps.find_file('jarvis')[:2]}"


@step("web: duckduckgo")
def t_ddg():
    from core.websearch import ddg_search
    r = ddg_search("курс евро к гривне сегодня")
    return bool(r), [x["title"][:50] for x in r[:3]]


@step("web: youtube first video")
def t_yt():
    from core.websearch import youtube_first
    vid, title = youtube_first("lofi hip hop radio")
    return bool(vid), f"{vid} {title[:60]}"


@step("web: google via Edge")
def t_google():
    from core.websearch import google_search
    r = google_search("курс евро к гривне сегодня")
    return bool(r and r["results"]), f"ответ: {(r or {}).get('answer_box','')[:120]} | {[x['title'][:40] for x in (r or {}).get('results', [])[:3]]}"


@step("gemini: search_internet (актуальность)")
def t_search():
    r = G.search("Какой сегодня курс евро к гривне?")
    a = r.get("answer", "")
    return bool(a) and "2024" not in a, a[:260]


@step("tools: click_on_screen (без клика, только поиск координат)")
def t_click(tb):
    from PIL import ImageDraw
    tb.dry_run = True
    out, ok = [], True
    shot = tb._grab()
    W, H = shot.size
    dr = ImageDraw.Draw(shot)
    try:
        for target, check in [("кнопка «Пуск» (логотип Windows) на панели задач", lambda x, y: y > H * 0.85),
                              ("часы с датой в правом нижнем углу", lambda x, y: y > H * 0.85 and x > W * 0.75)]:
            r = tb.t_click_on_screen(target)
            good = isinstance(r, dict) and "at" in r and check(*r["at"])
            ok = ok and good
            out.append({"target": target[:30], "res": r, "ok": good})
            if isinstance(r, dict) and "at" in r:
                x, y = r["at"]
                dr.ellipse((x - 14, y - 14, x + 14, y + 14), outline=(255, 0, 0), width=4)
    finally:
        tb.dry_run = False
    shot.thumbnail((1600, 1600))
    shot.save(BASE / "data" / "click_test.jpg", quality=80)
    return ok, out


@step("config: проверка настроек")
def t_cfg():
    from core.config import coerce
    assert coerce("idle_timeout", "999") == 120 and coerce("mic_device", "") is None and coerce("headphones", "true") is True
    try:
        coerce("voice", "Nope")
        return False, "не отсекает неверный голос"
    except ValueError:
        pass
    from core.assistant import build_prompt
    p = build_prompt({"user_name": "Арсений", "persona": "friend", "reply_length": "detailed", "custom_instructions": "Шути"}, "сейчас")
    return "Арсений" in p and "Шути" in p and "развёрнуто" in p, f"prompt {len(p)} симв."


@step("режимы: создать → запустить → удалить")
def t_routines(tb):
    r = tb.t_routine_save("Самотест", [{"tool": "volume", "args_json": '{"action": "get"}'},
                                       {"tool": "wait", "args_json": '{"seconds": 0.3}'},
                                       {"tool": "now"}, {"tool": "power", "args_json": '{"action": "shutdown"}'},
                                       {"tool": "nope"}], "проверка")
    assert r.get("saved") == "Самотест", r
    assert len(r["skipped"]) == 2, r  # power и несуществующая функция отсеяны
    run = tb.t_routine_run("самотест")
    lst = tb.t_routine_list()
    gone = tb.t_routine_delete("Самотест")
    ok = len(run.get("done", [])) == 2 and not run.get("errors") and "удалён" in str(gone)
    return ok, f"шаги={r['steps']} выполнено={run.get('done')} ошибки={run.get('errors')} список={str(lst)[:80]}"


@step("тихий режим")
def t_quiet(tb):
    a = tb.t_quiet_mode(5)
    on = tb.store.data["quiet_until"] > time.time()
    tb.t_quiet_mode(off=True)
    return on and tb.store.data["quiet_until"] == 0, a


@step("игры: активное окно, Discord, клипы")
def t_gaming(tb):
    from core import winsys
    fg = winsys.foreground_process()
    d = tb.t_discord("mute") if not cfg.get("discord_mute_key") else {"skip": "клавиша задана, не нажимаю"}
    nv = winsys.process_running("NVIDIA Overlay.exe", "NVIDIA app.exe", "nvsphelper64.exe")
    st = tb.t_system_status()
    return bool(fg) and "active_process" in st, f"активный процесс={fg} | полноэкранный={winsys.is_fullscreen()} | NVIDIA app={nv} | discord={str(d)[:90]}"


@step("характер «Репетитор» и брифинг в промпте")
def t_prompt2():
    from core.assistant import build_prompt
    p = build_prompt({"user_name": "Арсений", "persona": "tutor"}, "сейчас", routines="- Сохранённые режимы: «Игровой»\n",
                     briefing="- УТРЕННИЙ БРИФИНГ: тест\n")
    return "репетитор" in p and "«Игровой»" in p and "БРИФИНГ" in p, f"{len(p)} симв."


@step("Telegram: агент с инструментами (без Telegram, только Gemini)")
def t_tg_agent(tb):
    from core.telegram import TelegramBot
    bot = TelegramBot(tb.ctx)
    reply = bot.agent(1, [{"text": "Посчитай функцией calculate: 17*23+4. Ответь только числом."}])
    used = [e for e in tb.ctx.events if e[0] == "tool"]
    reply2 = bot.agent(1, [{"text": "А теперь раздели предыдущий результат на 5 (тоже функцией)."}])
    return "395" in reply and "79" in reply2, f"1) {reply[:60]} | 2) {reply2[:60]} | вызовы={used[-3:]}"


@step("Telegram: токен бота")
def t_tg_token():
    tok = (cfg.get("telegram_token") or "").strip()
    if not tok:
        return None, "токен не задан — пропускаю (вкладка «Телефон»)"
    import requests
    j = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=15).json()
    return bool(j.get("ok")), f"@{j.get('result', {}).get('username')}" if j.get("ok") else j


@step("обновления: GitHub и установщик")
def t_update(tb):
    from core.updater import Updater, current_version, vtuple
    assert vtuple("v2.10.0") > vtuple("2.9.9") > vtuple("2.9") and vtuple("2.1.0") == vtuple("v2.1.0")
    compile((BASE / "core" / "update_helper.py").read_text(encoding="utf-8"), "update_helper.py", "exec")
    i = Updater(tb.ctx).check()
    if i.get("error"):
        return None, f"версия {current_version()}, репозиторий {i.get('repo')}: {i['error']}"
    return True, f"версия {i['current']}, на GitHub {i.get('latest')}, доступно обновление: {i['available']}"


@step("лицензия Pro: ключи и ограничения бесплатной версии")
def t_license(tb):
    from core.license import License, parse_offline, PRO_TOOLS
    assert parse_offline("PRO-abc.def") is None and parse_offline("мусор") is None
    out = []
    skp = BASE / "data" / "license_private.key"
    if skp.exists():
        import subprocess
        key = subprocess.run([sys.executable, str(BASE / "tools" / "make_key.py"), "самотест", "--days", "1"],
                             capture_output=True, text=True, encoding="utf-8").stdout.strip()
        d = parse_offline(key)
        assert d and d["n"] == "самотест", key[:40]
        bad = key[:-3] + ("AAA" if not key.endswith("AAA") else "BBB")
        assert parse_offline(bad) is None, "подделанный ключ принят!"
        out.append("свой ключ выпускается и проверяется, подделка отклоняется")
    else:
        out.append("секрета владельца нет — выпуск ключей не проверял")
    was = getattr(tb.ctx, "pro", True)
    tb.ctx.pro = False
    r = tb.call("routine_list", {})
    tb.ctx.pro = was
    assert r.get("error") == "pro_only", r
    from core.assistant import build_prompt
    p = build_prompt({"persona": "tutor"}, "сейчас", pro=False)
    assert "терпеливый репетитор" not in p and "дворецкий" in p and "бесплатная версия" in p, "в бесплатной версии включился характер Pro"
    assert "терпеливый репетитор" in build_prompt({"persona": "tutor"}, "сейчас", pro=True)
    lic = License(cfg)
    out.append(f"бесплатная версия блокирует {len(PRO_TOOLS)} функций; сейчас: {'Pro' if lic.pro else 'бесплатная'} {lic.info().get('name', '')}")
    return True, "; ".join(out)


@step("gemini: vision")
def t_vision(tb):
    return str(tb.t_look_at_screen("Опиши одним предложением, что на экране"))[:250]


@step("gemini: tts")
def t_tts():
    r = G.tts("Все системы в норме, сэр.")
    if r:
        with wave.open(str(BASE / "data" / "tts_test.wav"), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(r[1]); f.writeframes(r[0])
    return bool(r), f"{len(r[0]) if r else 0} байт"


class FakeCtx:
    def __init__(self):
        from core.apps import Apps
        from core.store import Store
        from core.winsys import Stats
        self.cfg = cfg
        self.store = Store()
        self.apps = Apps(cfg, BASE)
        self.stats = Stats()
        from core.gemini import Gemini
        self.gemini = globals().get("G") or Gemini(cfg)
        self.events = []

    def toast(self, t): self.events.append(("toast", t))
    def ui_card(self, *a, **k): self.events.append(("card", a[0]))
    def push_weather(self, d): pass
    def hide_window_for_capture(self, h): pass
    def ui_shutdown(self, *a): pass
    def later(self, *a): pass
    def request_end(self): self.events.append(("end",))
    def on_settings_changed(self): pass
    def _threadsafe(self, m): self.events.append((m.get("t"), m.get("name") or m.get("text")))
    def quiet(self): return False
    pro = True
    def set_watch(self, on): return {"ok": on}


async def live_full(tb, G):
    """Live-сессия с ПОЛНЫМ набором инструментов и системным промптом Джарвиса."""
    import aiohttp
    import numpy as np
    from core.assistant import PERSONA
    from core.audio import resample
    from core.live import LiveSession
    setup = {
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": cfg.get("voice", "Charon")}}}},
        "systemInstruction": {"parts": [{"text": PERSONA.format(user="сэр", now=time.strftime("%d.%m.%Y %H:%M"), city=cfg.get("city"), memory="", history="")}]},
        "tools": [{"functionDeclarations": tb.declarations()}],
        "inputAudioTranscription": {}, "outputAudioTranscription": {},
        "realtimeInputConfig": {"automaticActivityDetection": {"silenceDurationMs": 650, "prefixPaddingMs": 200}},
        "contextWindowCompression": {"slidingWindow": {}},
    }
    out = {"audio": 0, "in": "", "out": "", "tools": [], "turns": 0}
    done = asyncio.Event()

    async def on_event(kind, data):
        if kind == "audio":
            out["audio"] += len(data)
        elif kind == "in_text":
            out["in"] += data
        elif kind == "out_text":
            out["out"] += data
        elif kind == "tool_call":
            resps = []
            for c in data:
                res = await asyncio.to_thread(tb.call, c["name"], c.get("args") or {})
                out["tools"].append({"name": c["name"], "args": c.get("args"), "res": str(res)[:160]})
                resps.append({"id": c.get("id"), "name": c["name"], "response": res if isinstance(res, dict) else {"result": res}})
            await sess.send_tool_responses(resps)
        elif kind == "turn_complete":
            out["turns"] += 1
            if out["audio"]:
                done.set()
        elif kind == "closed":
            out["closed"] = data
            done.set()

    async with aiohttp.ClientSession() as http:
        sess = LiveSession(cfg["gemini_api_key"].strip(), G.pick_live(), setup, on_event, http)
        t0 = time.time()
        await sess.connect()
        out["setup_s"] = round(time.time() - t0, 2)
        results_ = {}
        # 1) текстом: таймер (действие)
        await sess.send_text("Поставь таймер на 3 минуты, назови его «проверка»")
        try:
            await asyncio.wait_for(done.wait(), 25)
        except asyncio.TimeoutError:
            pass
        results_["text_timer"] = dict(out)
        # 2) голосом (синтезированная речь)
        for k in ("audio", "turns"):
            out[k] = 0
        out.update(**{"in": "", "out": "", "tools": []})
        done.clear()
        wav = BASE / "data" / "test" / "q.wav"
        if wav.exists():
            with wave.open(str(wav)) as f:
                pcm, sr = f.readframes(f.getnframes()), f.getframerate()
            x = resample(np.frombuffer(pcm, dtype=np.int16), sr, 16000).tobytes()
            for i in range(0, len(x), 2560):
                await sess.send_audio(x[i:i + 2560])
                await asyncio.sleep(0.08)
            z = b"\x00" * 2560
            t1 = time.time()
            while not done.is_set() and time.time() - t1 < 20:
                await sess.send_audio(z)
                await asyncio.sleep(0.08)
            results_["voice_weather"] = dict(out)
        # 3) «вижу экран»: кадр через realtimeInput.video + вопрос
        for k in ("audio", "turns"):
            out[k] = 0
        out.update(**{"in": "", "out": "", "tools": []})
        done.clear()
        import io as _io
        img = tb._grab(1280)
        b = _io.BytesIO()
        img.convert("RGB").save(b, "JPEG", quality=68)
        await sess.send_image(b.getvalue())
        await asyncio.sleep(0.5)
        await sess.send_image(b.getvalue())
        await sess.send_text("[СИСТЕМА: включён режим «вижу экран», тебе приходят кадры экрана.] Одним предложением: что на экране? Не вызывай функции.")
        try:
            await asyncio.wait_for(done.wait(), 25)
        except asyncio.TimeoutError:
            pass
        results_["watch_frame"] = dict(out)
        # 4) создание режима словами
        for k in ("audio", "turns"):
            out[k] = 0
        out.update(**{"in": "", "out": "", "tools": []})
        done.clear()
        await sess.send_text("Создай режим «Самотест два»: узнай громкость, потом пауза 1 секунда, потом скажи время. Сохрани без вопросов.")
        t2 = time.time()
        while time.time() - t2 < 30 and not any(x["name"] == "routine_save" for x in out["tools"]):
            await asyncio.sleep(0.3)
        await asyncio.sleep(3)
        results_["routine_voice"] = dict(out)
        await sess.close()
        return results_


async def watch_variants(tb, G):
    """Какой способ передачи кадра экрана модель реально видит."""
    import aiohttp
    import base64 as b64
    import io as _io
    from core.live import LiveSession
    img = tb._grab(1280)
    b = _io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=68)
    jpg = b.getvalue()
    q = "Посмотри на мой экран и назови два конкретных слова или надписи, которые там видишь. Не вызывай функции."
    res = {}
    for variant in ("rt_video+rt_text", "client_inline", "rt_video+client_text", "rt_video+audio"):
        setup = {"generationConfig": {"responseModalities": ["AUDIO"]}, "outputAudioTranscription": {}, "inputAudioTranscription": {},
                 "systemInstruction": {"parts": [{"text": "Ты ассистент, который видит экран пользователя. Отвечай по-русски коротко."}]}}
        out = {"out": "", "audio": 0}
        done = asyncio.Event()

        async def on_event(kind, data):
            if kind == "audio":
                out["audio"] += len(data)
            elif kind == "out_text":
                out["out"] += data
            elif kind in ("turn_complete", "closed"):
                if kind == "closed":
                    out["closed"] = str(data)[:120]
                done.set()
        async with aiohttp.ClientSession() as http:
            sess = LiveSession(cfg["gemini_api_key"].strip(), G.pick_live(), setup, on_event, http)
            try:
                await sess.connect()
                if variant == "client_inline":
                    await sess._send({"clientContent": {"turns": [{"role": "user", "parts": [
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64.b64encode(jpg).decode()}}, {"text": q}]}], "turnComplete": True}})
                else:
                    for _ in range(2):
                        await sess.send_image(jpg)
                        await asyncio.sleep(0.6)
                    if variant == "rt_video+rt_text":
                        await sess._send({"realtimeInput": {"text": q}})
                    elif variant == "rt_video+client_text":
                        await sess.send_text(q)
                    else:
                        wav = BASE / "data" / "test" / "screen_q.wav"
                        if not wav.exists():
                            r = G.tts("Что сейчас у меня на экране? Назови два слова, которые видишь.")
                            with wave.open(str(wav), "wb") as f:
                                f.setnchannels(1); f.setsampwidth(2); f.setframerate(r[1]); f.writeframes(r[0])
                        import numpy as np
                        from core.audio import resample
                        with wave.open(str(wav)) as f:
                            pcm, sr = f.readframes(f.getnframes()), f.getframerate()
                        x = resample(np.frombuffer(pcm, dtype=np.int16), sr, 16000).tobytes()
                        for i in range(0, len(x), 2560):
                            await sess.send_audio(x[i:i + 2560])
                            if i % 25600 == 0:
                                await sess.send_image(jpg)
                            await asyncio.sleep(0.08)
                        for _ in range(40):
                            if done.is_set():
                                break
                            await sess.send_audio(b"\x00" * 2560)
                            await asyncio.sleep(0.08)
                await asyncio.wait_for(done.wait(), 25)
            except Exception as e:
                out["err"] = repr(e)[:150]
            await sess.close()
        low = out["out"].lower()
        import re as _re
        seen = bool(out["out"]) and not _re.search(r"(?<!\w)(не вижу|не трансл|не могу|нет доступа|не отображ|не получ)", low)
        res[variant] = (seen, out)
        rec("WATCH " + variant, seen, json.dumps(out, ensure_ascii=False))
    return res


def main():
    if ONLY == "new":
        t_models()
        ctx = FakeCtx()
        tb = __import__("core.tools", fromlist=["Toolbox"]).Toolbox(ctx)
        ctx.tools = tb
        tb.ctx = ctx
        t_routines(tb); t_quiet(tb); t_gaming(tb); t_prompt2(); t_update(tb); t_tg_agent(tb); t_tg_token()
        r = asyncio.run(live_full(tb, G))
        for k in ("watch_frame", "routine_voice"):
            v = r.get(k, {})
            import re as _re
            good = (v.get("audio", 0) > 0 and not _re.search(r"(?<!\w)(не вижу|не трансл|не могу)", v.get("out", "").lower())) \
                if k == "watch_frame" else any(x["name"] == "routine_save" for x in v.get("tools", []))
            rec("LIVE " + k, good, json.dumps(v, ensure_ascii=False))
        tb.t_routine_delete("Самотест два")
        ctx.store.cancel_timer(label="провер")
        return
    if ONLY == "update":
        ctx = FakeCtx()
        tb = __import__("core.tools", fromlist=["Toolbox"]).Toolbox(ctx)
        t_update(tb)
        t_license(tb)
        return
    if ONLY == "watch":
        t_models()
        ctx = FakeCtx()
        tb = __import__("core.tools", fromlist=["Toolbox"]).Toolbox(ctx)
        asyncio.run(watch_variants(tb, G))
        return
    if ONLY == "click":
        t_models()
        tb = __import__("core.tools", fromlist=["Toolbox"]).Toolbox(FakeCtx())
        t_click(tb)
        return
    t_devices()
    t_mic()
    t_wake()
    if not cfg.get("gemini_api_key"):
        rec("gemini key", False, "ключ не задан")
        return
    t_models()
    ctx = FakeCtx()
    from core.tools import Toolbox
    tb = Toolbox(ctx)
    ctx.tools = tb
    t_weather(tb); t_fx(tb); t_sys(tb); t_vol(tb); t_bright(tb); t_clip(tb); t_misc(tb)
    t_cfg(); t_apps(tb); t_files(tb); t_google(); t_yt()
    t_routines(tb); t_quiet(tb); t_gaming(tb); t_prompt2(); t_update(tb); t_license(tb); t_tg_token()
    if QUICK:
        return
    t_search(); t_vision(tb); t_click(tb); t_tts(); t_tg_agent(tb)
    try:
        t = time.time()
        r = asyncio.run(live_full(tb, G))
        tt = r.get("text_timer", {})
        rec("LIVE text→tool (set_timer)", any(x["name"] == "set_timer" for x in tt.get("tools", [])) and tt.get("audio", 0) > 0,
            json.dumps(tt, ensure_ascii=False))
        vw = r.get("voice_weather", {})
        rec("LIVE voice→tool (weather)", ("Жилин" in vw.get("in", "") or "погод" in vw.get("in", "").lower()) and vw.get("audio", 0) > 0,
            json.dumps(vw, ensure_ascii=False))
        wf = r.get("watch_frame", {})
        import re as _re
        rec("LIVE «вижу экран» (кадр → ответ)", wf.get("audio", 0) > 0 and len(wf.get("out", "")) > 10
            and not _re.search(r"(?<!\w)(не вижу|не трансл|не могу)", wf.get("out", "").lower())
            and not any(x["name"] == "look_at_screen" for x in wf.get("tools", [])), json.dumps(wf, ensure_ascii=False))
        rv = r.get("routine_voice", {})
        saved = [x for x in rv.get("tools", []) if x["name"] == "routine_save"]
        rec("LIVE создание режима словами", bool(saved) and "saved" in saved[0]["res"], json.dumps(rv, ensure_ascii=False))
        tb.t_routine_delete("Самотест два")
        rec("LIVE total", True, f"{time.time()-t:.1f}s")
        ctx.store.cancel_timer(label="провер")
    except Exception as e:
        rec("LIVE full", False, repr(e) + " " + traceback.format_exc()[-600:])


if __name__ == "__main__":
    try:
        main()
    finally:
        (BASE / "data" / "selftest_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        fails = [r for r in results if r["ok"] is False]
        print(f"\nИтог: {len(results) - len(fails)} OK / {len(fails)} FAIL. Отчёт: {REPORT}")
        if "--pause" in sys.argv:
            input("Enter...")
