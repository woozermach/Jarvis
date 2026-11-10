# -*- coding: utf-8 -*-
"""Слово активации («Эй, Освин» / «Hey Jarvis»).

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
from .brand import wake_re

WAKE_RE = wake_re("jarvis")  # для совместимости (selftest)
STT_LANG = {"ru": "ru-RU", "uk": "uk-UA", "en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT",
            "pl": "pl-PL", "sk": "sk-SK", "cs": "cs-CZ"}


def strip_re(rx):
    return re.compile(r"^.*?(?:" + rx.pattern + r")\w*[\s,.!?:;-]*", re.I)


def _stub_sklearn_dependency():
    """openwakeword/__init__ импортирует sklearn ради обучения своих моделей (нам не нужно).
    На некоторых Windows DLL sklearn блокируется политикой — подменяем этот модуль заглушкой."""
    if "openwakeword.custom_verifier_model" not in sys.modules:
        stub = types.ModuleType("openwakeword.custom_verifier_model")
        stub.train_custom_verifier = lambda *a, **k: None
        sys.modules["openwakeword.custom_verifier_model"] = stub


def _custom_model(word):
    """models/hey_<word>.onnx рядом с программой — локальная модель слова активации."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "models" / f"hey_{word}.onnx"
    return p if p.exists() else None


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

        self.word = cfg.get("wake_word", "oswin")
        self.rx = wake_re(self.word)
        self.strip = strip_re(self.rx)
        eng = cfg.get("wake_engine", "auto")
        self.model_file = _custom_model(self.word)
        # модель «Hey Oswin» обучена на английском произношении: на ru/sk/de «Освин» она почти не срабатывает
        # (см. CLAUDE.md), поэтому в режиме «авто» на других языках интерфейса имя слушает распознавание речи
        if (self.model_file and eng == "auto" and self.word != "jarvis"
                and (cfg.get("ui_language") or "en").split("-")[0] not in ("en", "pl")):
            self.model_file = None
        if self.word != "jarvis" and not self.model_file and eng in ("auto", "openwakeword"):
            eng = "google"  # локальной модели для этого имени нет — только распознавание речи
        # пороги: для своей модели мгновенное срабатывание строже, а «похоже на имя» проверяется речью
        self._fast_thr = float(cfg.get("wake_threshold", 0.5))
        self._verify_thr = float(cfg.get("wake_verify_threshold", 0.002))
        if self.model_file:
            self._fast_thr = max(self._fast_thr, 0.75)
            self._verify_thr = max(self._verify_thr, 0.1)
        if eng == "off":
            self.status = "off"
            return
        if eng in ("auto", "openwakeword"):
            self._init_oww()
        self.verify_ok = True
        threading.Thread(target=self._verify_worker, daemon=True, name="wake-verify").start()
        if self.engine == "off" and self.verify_ok:
            self.engine = "google"
            self.status = (f"speech recognition · “{self.word}”" if eng == "google"
                           else "speech recognition (on-device model unavailable)")
        elif self.engine == "openwakeword":
            self.status = ("on-device model “hey " + self.word + "”" if self.model_file else "on-device (openWakeWord)") \
                + (" + speech check" if self.verify_ok else "")
        log.info("Wake: %s — %s", self.engine, self.status)

    def _init_oww(self):
        try:
            _stub_sklearn_dependency()
            from openwakeword.model import Model
            if self.model_file:  # своя модель (models/hey_<имя>.onnx), обученная tools/wakeword
                self.model = Model(wakeword_models=[str(self.model_file)], inference_framework="onnx")
            else:
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
            if s >= self._fast_thr:
                self.stats["fast"] += 1
                self._fire(None, s)
                return
            if self.verify_ok and s >= self._verify_thr and self._cand is None:
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
            self.score = 0.0
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
                from .stt import transcribe_all
                lang = self.cfg.get("ui_language") or "en"
                alts = transcribe_all(pcm, STT_LANG.get(lang, "en-US"))
                if not any(self.rx.search(t) for t in alts) and lang != "en" and self.word != "jarvis":
                    # имя часто распознаётся как английское слово — второй шанс
                    alts += transcribe_all(pcm, "en-US")
                text = next((t for t in alts if self.rx.search(t)), alts[0] if alts else "")
            except Exception:
                text = ""
            finally:
                self._busy = False
            if text and self.rx.search(text):
                rest = self.strip.sub("", text, count=1).strip(" ,.!?")
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
