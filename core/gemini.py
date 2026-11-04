# -*- coding: utf-8 -*-
"""REST-вызовы Gemini: выбор моделей, текст, зрение, поиск Google, синтез речи."""
import base64
import logging
import re
import time

import requests

log = logging.getLogger("jarvis.gemini")
API = "https://generativelanguage.googleapis.com/v1beta"

LIVE_PREF = ["gemini-3.8-live", "gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-latest",
             "gemini-2.5-flash-native-audio-preview-12-2025"]
# порядок по реальной скорости на бесплатном ключе (замерено самотестом)
TEXT_PREF = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash",
             "gemini-3.8-flash", "gemini-3.7-flash", "gemini-flash-latest", "gemini-3.5-flash-lite",
             "gemini-flash-lite-latest"]
FAST_PREF = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.5-flash"]
TTS_PREF = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts"]


class Gemini:
    def __init__(self, cfg):
        self.cfg = cfg
        self.models = []
        self.live_models = []
        self.text_models = []
        self.tts_models = []
        self.bad = {}  # модель -> время, до которого её не трогаем

    @property
    def key(self):
        return (self.cfg.get("gemini_api_key") or "").strip()

    @property
    def h(self):
        return {"x-goog-api-key": self.key, "Content-Type": "application/json"}

    def refresh_models(self):
        names, tok = [], None
        for _ in range(5):
            r = requests.get(f"{API}/models", headers=self.h,
                             params={"pageSize": 200, **({"pageToken": tok} if tok else {})}, timeout=20)
            if r.status_code in (400, 401, 403):
                raise PermissionError("ключ Gemini не подходит")
            r.raise_for_status()
            j = r.json()
            for m in j.get("models", []):
                names.append((m["name"].split("/")[-1], m.get("supportedGenerationMethods", [])))
            tok = j.get("nextPageToken")
            if not tok:
                break
        self.models = names
        have_live = {n for n, s in names if "bidiGenerateContent" in s}
        have_gen = {n for n, s in names if "generateContent" in s}
        self.live_models = [m for m in LIVE_PREF if m in have_live] + sorted(
            n for n in have_live if ("live" in n or "native-audio" in n) and n not in LIVE_PREF
            and not any(b in n for b in ("transcribe", "translate", "robotics", "thinking")))
        self.text_models = [m for m in TEXT_PREF if m in have_gen]
        self.tts_models = [m for m in TTS_PREF if m in have_gen]
        log.info("Live: %s | Text: %s | TTS: %s", self.live_models[:3], self.text_models[:3], self.tts_models[:2])

    def pick_live(self):
        m = self.cfg.get("live_model")
        if m:
            return m
        return self.live_models[0] if self.live_models else "gemini-3.8-live"

    # ── генерация с перебором моделей при перегрузке ──
    def generate(self, contents, tools=None, system=None, models=None, timeout=45, gen_cfg=None):
        order = models or ([self.cfg["text_model"]] if self.cfg.get("text_model") else []) + self.text_models
        if not order:
            order = TEXT_PREF
        last = ""
        now = time.time()
        for m in order:
            if self.bad.get(m, 0) > now:
                continue
            body = {"contents": contents}
            if tools:
                body["tools"] = tools
            if system:
                body["system_instruction"] = {"parts": [{"text": system}]}
            if gen_cfg:
                body["generationConfig"] = gen_cfg
            try:
                r = requests.post(f"{API}/models/{m}:generateContent", headers=self.h, json=body, timeout=timeout)
            except Exception as e:
                last = repr(e)
                continue
            if r.status_code == 200:
                return m, r.json()
            last = f"{m}: {r.status_code} {r.text[:200]}"
            log.warning("generate %s", last)
            if r.status_code in (429, 503, 500, 404):
                self.bad[m] = now + (600 if r.status_code in (404, 429) else 90)
                continue
            break
        raise RuntimeError(last or "нет доступных моделей")

    @staticmethod
    def text_of(j):
        try:
            parts = j["candidates"][0]["content"]["parts"]
            return " ".join(p["text"] for p in parts if p.get("text") and not p.get("thought")).strip()
        except Exception:
            return ""

    def ask(self, prompt, system=None, timeout=45):
        _, j = self.generate([{"role": "user", "parts": [{"text": prompt}]}], system=system, timeout=timeout)
        return self.text_of(j)

    def vision(self, image_jpeg: bytes, question: str):
        _, j = self.generate([{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_jpeg).decode()}},
            {"text": question}]}],
            system="Ты помощник, который смотрит на скриншот экрана пользователя. Отвечай по-русски, по делу, "
                   "без markdown. Если на экране текст/код/ошибка — процитируй важное и объясни.")
        return self.text_of(j)

    def search(self, query: str):
        """Актуальный ответ из интернета: Google (через фоновый Edge) + новости + Википедия → выжимка моделью."""
        from .websearch import google_search, google_news, wikipedia, ddg_search
        g = google_search(query)
        results = (g or {}).get("results") or ddg_search(query, n=6)
        ctx = []
        if g and g.get("answer_box"):
            ctx.append("Блок ответа Google: " + g["answer_box"])
        if results:
            ctx.append("Результаты поиска:\n" + "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results))
        if re.search(r"новост|случил|произош|сегодня|вчера|матч|выбор|войн|news", query, re.I) or not results:
            news = google_news(query)
            if news:
                ctx.append("Свежие новости (Google News):\n" + "\n".join(f"- {n['date']} · {n['source']}: {n['title']}" for n in news))
        if not results:
            w = wikipedia(query)
            if w:
                ctx.append(f"Википедия «{w['title']}»: {w['extract']}")
        if not ctx:
            txt = self.ask(query + "\n(Ответь кратко. Предупреди, что данные могут быть неактуальны.)")
            return {"answer": txt, "sources": [], "note": "поиск недоступен, ответ по знаниям модели"}
        prompt = (f"Вопрос пользователя: {query}\nСегодня {time.strftime('%d.%m.%Y %H:%M')}.\n\n" + "\n\n".join(ctx) +
                  "\n\nОтветь по-русски ТОЛЬКО по найденному выше, 2–5 предложений, с конкретными цифрами и датами. "
                  "Если данные противоречат друг другу — скажи. Без markdown.")
        try:
            _, j = self.generate([{"role": "user", "parts": [{"text": prompt}]}], models=FAST_PREF + self.text_models, timeout=30)
            ans = self.text_of(j)
        except Exception as e:
            ans = "Не удалось обработать результаты: " + str(e)[:100]
        return {"answer": ans, "sources": [{"title": r["title"], "url": r["url"]} for r in (results or [])[:5]]}

    def tts(self, text: str, voice="Charon"):
        """Возвращает PCM 24 кГц или None."""
        for m in self.tts_models or TTS_PREF:
            if self.bad.get(m, 0) > time.time():
                continue
            # только сам текст: новые TTS-модели зачитывают указания вроде «произнеси спокойно» вслух
            body = {"contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"],
                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
            try:
                r = requests.post(f"{API}/models/{m}:generateContent", headers=self.h, json=body, timeout=40)
                if r.status_code == 200:
                    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                    rate = int((re.search(r"rate=(\d+)", part.get("mimeType", "")) or [0, 24000])[1])
                    return base64.b64decode(part["data"]), rate
                self.bad[m] = time.time() + 300
            except Exception as e:
                log.warning("tts %s: %s", m, e)
        return None
