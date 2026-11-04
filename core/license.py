# -*- coding: utf-8 -*-
"""Лицензия Pro.

Два вида ключей:
- ключ Gumroad (покупатель получает его письмом после оплаты) — проверяется онлайн у Gumroad, раз в 3 дня;
  без интернета Pro работает ещё 14 дней после последней успешной проверки;
- свой ключ «PRO-…» (владельцу, друзьям, для тестов) — подписан секретом владельца (Ed25519), проверяется без интернета.
  Выпуск: tools/make_key.py (нужен data/license_private.key — он есть только у владельца и в git не попадает)."""
import base64
import json
import logging
import time

import requests

from . import ed25519
from .config import DATA_DIR

log = logging.getLogger("jarvis.license")

PUBLIC_KEY = bytes.fromhex("1fc62c76483aad822d9c65791dddf2d01ce5e5e91021cd3d0915684a3f12a5d7")
GUMROAD_PRODUCT_ID = ""   # заполнить после создания товара на Gumroad (Product → Content → License key → product_id)
BUY_URL = ""              # ссылка на страницу товара, например https://woozermach.gumroad.com/l/jarvis-pro
RECHECK = 3 * 86400
GRACE = 14 * 86400
STATE = DATA_DIR / "license.json"

PRO_FEATURES = {
    "telegram": "Telegram-бот: управление с телефона и уведомления",
    "watch": "«Вижу экран» и характер «Репетитор»",
    "routines": "Режимы одной фразой и тихий режим",
    "proactive": "Проактивность и утренний брифинг",
}
PRO_TOOLS = {"routine_save", "routine_run", "routine_list", "routine_delete", "quiet_mode", "watch_screen"}
PRO_PERSONAS = {"tutor"}


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def parse_offline(key):
    """PRO-<payload>.<signature> → dict или None."""
    key = "".join(key.split())
    if not key.upper().startswith("PRO-") or "." not in key:
        return None
    body, sig = key[4:].rsplit(".", 1)
    try:
        payload, signature = _b64d(body), _b64d(sig)
    except Exception:
        return None
    if not ed25519.verify(PUBLIC_KEY, payload, signature):
        return None
    try:
        d = json.loads(payload)
    except Exception:
        return None
    if d.get("e") and time.time() > float(d["e"]):
        return {"expired": True, **d}
    return d


class License:
    def __init__(self, cfg):
        self.cfg = cfg
        self.state = {}
        if STATE.exists():
            try:
                self.state = json.loads(STATE.read_text(encoding="utf-8"))
            except Exception:
                self.state = {}
        if self.state.get("key") != (cfg.get("license_key") or "").strip():
            self.state = {}

    def _save(self):
        STATE.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")

    @property
    def pro(self):
        s = self.state
        if not s.get("ok"):
            return False
        if s.get("kind") == "offline":
            return not s.get("expires") or time.time() < s["expires"]
        return time.time() - s.get("verified", 0) < GRACE

    def info(self):
        s = self.state
        return {"pro": self.pro, "kind": s.get("kind", ""), "name": s.get("name", ""), "error": s.get("error", ""),
                "expires": s.get("expires", 0), "verified": s.get("verified", 0), "has_key": bool(s.get("key")),
                "buy_url": BUY_URL, "features": PRO_FEATURES}

    def activate(self, key):
        """Проверяет ключ и запоминает результат. Возвращает info()."""
        key = (key or "").strip()
        self.cfg["license_key"] = key
        self.cfg.save()
        self.state = {"key": key}
        if not key:
            self._save()
            return self.info()
        d = parse_offline(key)
        if key.upper().startswith("PRO-"):
            if not d:
                self.state.update(ok=False, error="ключ повреждён или не настоящий")
            elif d.get("expired"):
                self.state.update(ok=False, kind="offline", name=d.get("n", ""), error="срок действия ключа закончился")
            else:
                self.state.update(ok=True, kind="offline", name=d.get("n", ""), expires=float(d.get("e") or 0), verified=time.time())
            self._save()
            return self.info()
        self._verify_gumroad(first=True)
        return self.info()

    def _verify_gumroad(self, first=False):
        key = self.state.get("key", "")
        if not GUMROAD_PRODUCT_ID:
            self.state.update(ok=False, kind="gumroad", error="магазин ещё не подключён — используйте ключ PRO-…")
            self._save()
            return
        try:
            r = requests.post("https://api.gumroad.com/v2/licenses/verify", timeout=15,
                              data={"product_id": GUMROAD_PRODUCT_ID, "license_key": key, "increment_uses_count": "true" if first else "false"})
            j = r.json()
        except Exception as e:
            # нет сети — оставляем прежний статус (действует GRACE)
            self.state["error"] = f"не удалось проверить ключ: {str(e)[:80]}"
            self._save()
            return
        pur = j.get("purchase") or {}
        bad = (not j.get("success") or pur.get("refunded") or pur.get("chargebacked") or pur.get("disputed")
               or pur.get("subscription_ended_at") or pur.get("subscription_failed_at"))
        if bad:
            msg = j.get("message") or ("покупка возвращена" if pur.get("refunded") else "ключ не действителен")
            self.state.update(ok=False, kind="gumroad", error=msg)
        else:
            self.state.update(ok=True, kind="gumroad", name=pur.get("email", ""), verified=time.time(), error="",
                              uses=j.get("uses", 0))
        self._save()

    def refresh(self):
        """Периодическая перепроверка ключа Gumroad (свои ключи не требуют сети)."""
        if self.state.get("kind") == "gumroad" and time.time() - self.state.get("verified", 0) > RECHECK:
            self._verify_gumroad()
        elif not self.state and (self.cfg.get("license_key") or "").strip():
            self.activate(self.cfg["license_key"])
        return self.pro
