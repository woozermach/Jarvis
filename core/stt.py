# -*- coding: utf-8 -*-
"""Быстрое распознавание коротких фраз (для проверки слова «Джарвис»).
Google Speech (как в Chrome) принимает сырой PCM 16 кГц — без внешнего flac.exe.
Запасной путь — модель Gemini для расшифровки."""
import base64
import io
import json
import logging
import wave

import requests

log = logging.getLogger("jarvis.stt")
_URL = "https://www.google.com/speech-api/v2/recognize"
_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"  # публичный ключ Chromium, тот же, что в SpeechRecognition
_session = requests.Session()


def google(pcm16k: bytes, lang="ru-RU", timeout=6) -> str:
    r = _session.post(_URL, params={"output": "json", "lang": lang, "key": _KEY, "client": "chromium"},
                      data=pcm16k, headers={"Content-Type": "audio/l16; rate=16000"}, timeout=timeout)
    r.raise_for_status()
    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        for res in j.get("result", []):
            alts = res.get("alternative") or []
            if alts:
                return alts[0].get("transcript", "")
    return ""


def wav_bytes(pcm16k: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm16k)
    return b.getvalue()


def gemini(pcm16k: bytes, api_key: str, model="gemini-3.1-flash-lite", timeout=8) -> str:
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav_bytes(pcm16k)).decode()}},
        {"text": "Transcribe the speech in this recording verbatim, in its original language. Output only the text. If there is no speech, output nothing."}]}]}
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=body, timeout=timeout)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return " ".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def transcribe(pcm16k: bytes, api_key: str = "", lang: str = "ru-RU") -> str:
    try:
        return google(pcm16k, lang)
    except Exception as e:
        log.debug("google stt: %s", e)
    if api_key:
        try:
            return gemini(pcm16k, api_key)
        except Exception as e:
            log.debug("gemini stt: %s", e)
    return ""
