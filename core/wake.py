# -*- coding: utf-8 -*-
"""Слово активации «(Эй,) Джарвис».

Гибрид из двух ступеней:
 1) openWakeWord (модель hey_jarvis) крутится локально на каждом кадре 80 мс.
    Уверенный ответ (score ≥ wake_threshold) — мгновенная активация.
 2) Если модель «что-то услышала» (score ≥ verify_threshold), но не уверена (русское произношение),
    последние ~2.5 с звука проверяются распознаванием речи Google на слово «джарвис».
    Это ловит и «Эй, Джарвис», и просто «Джарвис», а заодно и команду, сказанную в той же фразе.
Если openWakeWord недоступен — работает только ступень 2 на любых коротких фразах.
"""
import logging
import queue
import re
import sys
import threading
import time
import types
from collections import deque

import numpy as np

log = logging.getLogger("jarvis.wake")
WAKE_RE = re.compile(r"(?:дж|ж|ч|д)[аеэ]р?[вб][иы]с|jarvis|джарви", re.I)
STRIP_RE = re.compile(r"^.*?(?:" + WAKE_RE.pattern + r")\w*[\s,.!?:;-]*", re.I)


def _stub_sklearn_dependency():
    """openwakeword/__init__ импортирует sklearn ради обучения своих моделей (нам не нужно).
    На некоторых Windows DLL sklearn блокируется политикой — подменяем этот модуль заглушкой."""
    if "openwakeword.custom_verifier_model" not in sys.modules:
        stub = types.ModuleType("openwakeword.custom_verifier_model")
        stub.train_custom_verifier = lambda *a, **k: None
        sys.modules["openwakeword.custom_verifier_model"] = stub


class Wake:
    def __init__(self, cfg, on_wake):
        self.cfg = cfg
        self.on_wake = on_wake          # on_wake(rest_text: str | None)
        self.engine = "off"
        self.model = None
        self.score = 0.0
        self.enabled = True
        self.status = ""
        self._last = 0.0
        self.ring = deque(maxlen=32)    # 2.56 с
        self._cand = None
        self._after = 0
        self._busy = False
        self._q = queue.Queue(maxsize=3)
        self._seg, self._voiced, self._silent = [], 0, 0
        self.verify_ok = False
        self.stats = {"fast": 0, "verified": 0, "rejected": 0}

        eng = cfg.get("wake_engine", "auto")
        if eng == "off":
            self.status = "выключено"
            return
        if eng in ("auto", "openwakeword"):
            self._init_oww()
        self.verify_ok = True
        threading.Thread(target=self._verify_worker, daemon=True, name="wake-verify").start()
        if self.engine == "off" and self.verify_ok:
            self.engine = "google"
            self.status = "по распознаванию речи (openWakeWord недоступен)"
        elif self.engine == "openwakeword":
            self.status = "локально (openWakeWord)" + (" + проверка речи" if self.verify_ok else "")
        log.info("Wake: %s — %s", self.engine, self.status)

    def _init_oww(self):
        try:
            _stub_sklearn_dependency()
            from openwakeword.model import Model
            try:
                self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            except Exception:
                from openwakeword.utils import download_models
                download_models(model_names=["hey_jarvis"])
                self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            self.engine = "openwakeword"
        except Exception as e:
            self.status = f"openWakeWord недоступен: {e}"
            log.warning(self.status)

    # ── кадры из аудиопотока (поток audio-pump) ──
    def feed(self, frame: np.ndarray, level: float, is_voice: bool):
        self.ring.append(frame)
        if not self.enabled or self.engine == "off":
            self._cand = None
            return
        if self.engine == "openwakeword":
            try:
                scores = self.model.predict(frame)
                s = float(max(scores.values())) if scores else 0.0
            except Exception as e:
                log.warning("oww predict: %s", e)
                return
            self.score = s
            if s >= float(self.cfg.get("wake_threshold", 0.5)):
                self.stats["fast"] += 1
                self._fire(None, s)
                return
            if self.verify_ok and s >= float(self.cfg.get("wake_verify_threshold", 0.002)) and self._cand is None:
                self._cand = time.time()
                self._after = 0
            if self._cand is not None:
                self._after += 1
                # ждём конца фразы (пауза ≥ 0.4 с) или максимум ~1.6 с после пика
                if not is_voice:
                    self._silent += 1
                else:
                    self._silent = 0
                if (self._silent >= 5 and self._after >= 4) or self._after >= 20:
                    self._submit(np.concatenate(list(self.ring)))
                    self._cand = None
                    self._silent = 0
        elif self.engine == "google":
            # без модели: каждую короткую фразу проверяем распознаванием
            if is_voice:
                self._seg.append(frame); self._voiced += 1; self._silent = 0
            elif self._seg:
                self._seg.append(frame); self._silent += 1
            if self._seg and (self._silent >= 6 or len(self._seg) > 40):
                if 3 <= self._voiced <= 40:
                    self._submit(np.concatenate(self._seg))
                self._seg, self._voiced, self._silent = [], 0, 0

    def _submit(self, pcm: np.ndarray):
        if self._busy:
            return
        now = time.time()
        self._recent = [t for t in getattr(self, "_recent", []) if now - t < 60]
        if len(self._recent) >= 25:  # не чаще 25 проверок в минуту
            return
        self._recent.append(now)
        try:
            self._q.put_nowait(pcm.astype(np.int16).tobytes())
        except queue.Full:
            pass

    def _verify_worker(self):
        while True:
            pcm = self._q.get()
            self._busy = True
            try:
                from .stt import transcribe
                text = transcribe(pcm, (self.cfg.get("gemini_api_key") or "").strip())
            except Exception:
                text = ""
            finally:
                self._busy = False
            if text and WAKE_RE.search(text):
                rest = STRIP_RE.sub("", text, count=1).strip(" ,.!?")
                self.stats["verified"] += 1
                log.info("Wake (проверено речью): «%s» → команда «%s»", text, rest)
                self._fire(rest or None, self.score)
            else:
                self.stats["rejected"] += 1
                if text:
                    log.debug("wake reject: %s", text)

    def _fire(self, rest, score):
        now = time.time()
        if now - self._last < 1.5:
            return
        self._last = now
        self._cand = None
        if self.model is not None:
            try:
                self.model.reset()
            except Exception:
                pass
        log.info("Wake! score=%.2f rest=%s", score, rest)
        self.on_wake(rest)
