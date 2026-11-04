# -*- coding: utf-8 -*-
"""Микрофон 16 кГц и динамик 24 кГц через sounddevice. Буфер воспроизведения можно мгновенно очистить."""
import logging
import queue
import threading
import time
from collections import deque

import numpy as np

log = logging.getLogger("jarvis.audio")
try:
    import sounddevice as sd
except Exception as e:  # pragma: no cover
    sd = None
    log.error("sounddevice недоступен: %s", e)

IN_RATE = 16000
OUT_RATE = 24000
FRAME = 1280  # 80 мс при 16 кГц — размер кадра для openWakeWord
import re as _re
HEADSET_RE = _re.compile(r"headset|headphone|наушник|гарнитур|blackshark|kraken|barracuda|hyperx|cloud ii|airpods|buds|"
                         r"arctis|steelseries|astro|corsair|logitech g|razer|jbl|wh-1000|sony wh|bose|sennheiser|beyerdynamic|"
                         r"hands-free|bluetooth", _re.I)


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or len(x) == 0:
        return x
    n = max(1, int(round(len(x) * sr_to / sr_from)))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x.astype(np.float32)).astype(np.int16)


def rms(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))


class AudioIO:
    def __init__(self, cfg):
        self.cfg = cfg
        self.frames = queue.Queue(maxsize=200)
        self.consumers = []           # функции f(frame: np.int16[1280])
        self.in_level = 0.0
        self.out_level = 0.0
        self.noise = 120.0
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.last_out = 0.0           # когда в последний раз реально играл звук
        self.preroll = deque(maxlen=int(1.2 * IN_RATE / FRAME))
        self.in_stream = None
        self.out_stream = None
        self._in_rate = IN_RATE
        self._out_rate = OUT_RATE
        self._carry = np.zeros(0, dtype=np.int16)
        self.mic_ok = False
        self.spk_ok = False
        self.mic_name = ""
        self.spk_name = ""
        self.spk_is_headset = False
        self.error = ""

    # ── запуск ──
    def start(self):
        if sd is None:
            self.error = "sounddevice не установлен"
            return
        self._open_out()
        self._open_in()
        threading.Thread(target=self._pump, daemon=True, name="audio-pump").start()

    def _open_in(self):
        dev = self.cfg.get("mic_device")
        for d in ([dev] if dev is not None else []) + [None]:
            for rate in (IN_RATE, None):
                try:
                    if rate is None:
                        info = sd.query_devices(d, "input")
                        rate = int(info["default_samplerate"])
                    blk = int(FRAME * rate / IN_RATE)
                    self.in_stream = sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=blk,
                                                    device=d, callback=self._in_cb)
                    self.in_stream.start()
                    self._in_rate = rate
                    self.mic_ok = True
                    self.mic_name = sd.query_devices(d if d is not None else sd.default.device[0])["name"]
                    log.info("Микрофон: %s @ %d Гц", self.mic_name, rate)
                    return
                except Exception as e:
                    log.warning("Не открыть микрофон %s @ %s: %s", d, rate, e)
        self.error = "микрофон не найден"

    def _open_out(self):
        dev = self.cfg.get("speaker_device")
        for d in ([dev] if dev is not None else []) + [None]:
            for rate in (OUT_RATE, None):
                try:
                    if rate is None:
                        info = sd.query_devices(d, "output")
                        rate = int(info["default_samplerate"])
                    self.out_stream = sd.OutputStream(samplerate=rate, channels=1, dtype="int16",
                                                      blocksize=int(rate * 0.02), device=d, callback=self._out_cb,
                                                      latency="low")
                    self.out_stream.start()
                    self._out_rate = rate
                    self.spk_ok = True
                    self.spk_name = sd.query_devices(d if d is not None else sd.default.device[1])["name"]
                    self.spk_is_headset = bool(HEADSET_RE.search(self.spk_name))
                    log.info("Динамик: %s @ %d Гц%s", self.spk_name, rate, " (гарнитура)" if self.spk_is_headset else "")
                    return
                except Exception as e:
                    log.warning("Не открыть динамик %s @ %s: %s", d, rate, e)

    def restart(self):
        for s in (self.in_stream, self.out_stream):
            try:
                s and s.close()
            except Exception:
                pass
        self.mic_ok = self.spk_ok = False
        self._open_out()
        self._open_in()

    # ── вход ──
    def _in_cb(self, indata, frames, t, status):
        x = indata[:, 0].copy()
        if self._in_rate != IN_RATE:
            x = resample(x, self._in_rate, IN_RATE)
        g = float(self.cfg.get("mic_gain", 1.0) or 1.0)
        if g != 1.0:
            x = np.clip(x.astype(np.float32) * g, -32768, 32767).astype(np.int16)
        x = np.concatenate([self._carry, x])
        while len(x) >= FRAME:
            fr, x = x[:FRAME], x[FRAME:]
            try:
                self.frames.put_nowait(fr)
            except queue.Full:
                pass
        self._carry = x

    def _pump(self):
        while True:
            fr = self.frames.get()
            r = rms(fr)
            self.in_level = 0.7 * self.in_level + 0.3 * min(1.0, r / 3000.0)
            if r < self.noise * 1.8:
                self.noise = 0.995 * self.noise + 0.005 * max(r, 30)
            self.preroll.append(fr)
            for c in list(self.consumers):
                try:
                    c(fr, r)
                except Exception:
                    log.exception("consumer")

    def is_voice(self, r: float) -> bool:
        return r > max(self.noise * 3.0, 350)

    # ── выход ──
    def _out_cb(self, outdata, frames, t, status):
        need = frames * 2
        with self.lock:
            chunk = bytes(self.buf[:need])
            del self.buf[:need]
        if len(chunk) < need:
            chunk += b"\x00" * (need - len(chunk))
        else:
            self.last_out = time.time()
        a = np.frombuffer(chunk, dtype=np.int16)
        outdata[:, 0] = a
        self.out_level = 0.6 * self.out_level + 0.4 * min(1.0, rms(a) / 5000.0)

    def play(self, pcm24: bytes):
        if not pcm24:
            return
        if self._out_rate != OUT_RATE:
            pcm24 = resample(np.frombuffer(pcm24, dtype=np.int16), OUT_RATE, self._out_rate).tobytes()
        with self.lock:
            self.buf.extend(pcm24)
        self.last_out = time.time()

    def clear(self):
        with self.lock:
            self.buf.clear()

    @property
    def playing(self) -> bool:
        with self.lock:
            return len(self.buf) > 0

    def recently_played(self, tail=0.45) -> bool:
        return self.playing or (time.time() - self.last_out) < tail

    def buffered_seconds(self) -> float:
        with self.lock:
            return len(self.buf) / 2 / self._out_rate

    # ── звуки интерфейса ──
    def chime(self, kind="on"):
        if not self.cfg.get("sounds", True):
            return
        sr = OUT_RATE

        def tone(f0, f1, dur, vol=0.18):
            n = int(sr * dur)
            t = np.arange(n) / sr
            f = np.linspace(f0, f1, n)
            ph = 2 * np.pi * np.cumsum(f) / sr
            env = np.minimum(1, t / 0.008) * np.exp(-t * 7)
            s = np.sin(ph) * 0.7 + np.sin(2 * ph) * 0.2 + np.sin(3 * ph) * 0.1
            return (s * env * vol * 32767).astype(np.int16)

        if kind == "on":
            s = np.concatenate([tone(880, 990, 0.09), tone(1320, 1480, 0.16)])
        elif kind == "off":
            s = np.concatenate([tone(1200, 1100, 0.08), tone(780, 700, 0.16)])
        elif kind == "alert":
            s = np.concatenate([tone(1400, 1400, 0.12), np.zeros(1800, np.int16), tone(1400, 1400, 0.12),
                                np.zeros(1800, np.int16), tone(1760, 1760, 0.22)])
        else:  # tick
            s = tone(1600, 1500, 0.05, 0.1)
        self.play(s.tobytes())


def list_devices():
    if sd is None:
        return {"inputs": [], "outputs": []}
    ins, outs = [], []
    try:
        apis = sd.query_hostapis()
        for i, d in enumerate(sd.query_devices()):
            api = apis[d["hostapi"]]["name"]
            if "MME" not in api:
                continue
            if d["max_input_channels"] > 0:
                ins.append({"id": i, "name": d["name"]})
            if d["max_output_channels"] > 0:
                outs.append({"id": i, "name": d["name"]})
    except Exception as e:
        log.warning("list_devices: %s", e)
    return {"inputs": ins, "outputs": outs}
