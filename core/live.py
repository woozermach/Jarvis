# -*- coding: utf-8 -*-
"""Клиент Gemini Live API (двунаправленный WebSocket, голос↔голос) на aiohttp."""
import asyncio
import base64
import json
import logging
import time

import aiohttp

log = logging.getLogger("jarvis.live")
URL = ("wss://generativelanguage.googleapis.com/ws/"
       "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")


class LiveError(Exception):
    pass


class LiveSession:
    """События отдаются в on_event(kind, data):
       audio(bytes) · in_text(str) · out_text(str) · turn_complete · interrupted · tool_call(list) ·
       tool_cancel(list) · go_away · closed(reason)"""

    def __init__(self, api_key, model, setup, on_event, http: aiohttp.ClientSession):
        self.key = api_key
        self.model = model
        self.setup = setup
        self.on_event = on_event
        self.http = http
        self.ws = None
        self.task = None
        self.alive = False
        self.resume_handle = None
        self.started = 0.0
        self.close_reason = ""

    async def connect(self, timeout=12):
        setup = dict(self.setup)
        setup["model"] = f"models/{self.model}"
        setup.setdefault("sessionResumption", {})
        if self.resume_handle:
            setup["sessionResumption"] = {"handle": self.resume_handle}
        t0 = time.time()
        self.ws = await self.http.ws_connect(URL, headers={"x-goog-api-key": self.key},
                                             max_msg_size=0, heartbeat=25, timeout=aiohttp.ClientWSTimeout(ws_close=5))
        await self.ws.send_str(json.dumps({"setup": setup}))
        msg = await asyncio.wait_for(self.ws.receive(), timeout)
        if msg.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
            reason = msg.extra or msg.data or self.ws.close_code
            await self._safe_close()
            raise LiveError(f"{reason}")
        d = json.loads(msg.data)
        if "setupComplete" not in d:
            await self._safe_close()
            raise LiveError(f"неожиданный ответ: {str(d)[:200]}")
        self.alive = True
        self.started = time.time()
        log.info("Live сессия %s открыта за %.2f c", self.model, time.time() - t0)
        self.task = asyncio.create_task(self._recv())

    async def _recv(self):
        try:
            async for msg in self.ws:
                if msg.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    break
                try:
                    d = json.loads(msg.data)
                except Exception:
                    continue
                await self._dispatch(d)
            self.close_reason = f"{self.ws.close_code} {getattr(self.ws, 'close_message', '') or ''}".strip()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.close_reason = repr(e)
            log.warning("Live recv: %s", e)
        finally:
            self.alive = False
            try:
                await self.on_event("closed", self.close_reason)
            except Exception:
                log.exception("on closed")

    async def _dispatch(self, d):
        sc = d.get("serverContent")
        if sc:
            mt = sc.get("modelTurn") or {}
            for p in mt.get("parts", []):
                inline = p.get("inlineData")
                if inline and inline.get("data"):
                    await self.on_event("audio", base64.b64decode(inline["data"]))
            if sc.get("inputTranscription", {}).get("text"):
                await self.on_event("in_text", sc["inputTranscription"]["text"])
            if sc.get("outputTranscription", {}).get("text"):
                await self.on_event("out_text", sc["outputTranscription"]["text"])
            if sc.get("interrupted"):
                await self.on_event("interrupted", None)
            if sc.get("turnComplete"):
                await self.on_event("turn_complete", None)
        if "toolCall" in d:
            await self.on_event("tool_call", d["toolCall"].get("functionCalls", []))
        if "toolCallCancellation" in d:
            await self.on_event("tool_cancel", d["toolCallCancellation"].get("ids", []))
        if "sessionResumptionUpdate" in d:
            u = d["sessionResumptionUpdate"]
            if u.get("resumable") and u.get("newHandle"):
                self.resume_handle = u["newHandle"]
        if "goAway" in d:
            await self.on_event("go_away", d["goAway"])

    async def _send(self, obj):
        if not self.alive or self.ws is None or self.ws.closed:
            return False
        try:
            await self.ws.send_str(json.dumps(obj))
            return True
        except Exception as e:
            log.warning("Live send: %s", e)
            return False

    async def send_audio(self, pcm16: bytes):
        return await self._send({"realtimeInput": {"audio": {"data": base64.b64encode(pcm16).decode(),
                                                             "mimeType": "audio/pcm;rate=16000"}}})

    async def send_image(self, jpeg: bytes):
        return await self._send({"realtimeInput": {"video": {"data": base64.b64encode(jpeg).decode(),
                                                             "mimeType": "image/jpeg"}}})

    async def send_text(self, text: str):
        return await self._send({"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}],
                                                   "turnComplete": True}})

    async def send_tool_responses(self, responses):
        return await self._send({"toolResponse": {"functionResponses": responses}})

    async def audio_end(self):
        return await self._send({"realtimeInput": {"audioStreamEnd": True}})

    async def _safe_close(self):
        try:
            if self.ws is not None and not self.ws.closed:
                await self.ws.close()
        except Exception:
            pass

    async def close(self):
        self.alive = False
        await self._safe_close()
        if self.task:
            try:
                await asyncio.wait_for(self.task, 3)
            except Exception:
                pass
