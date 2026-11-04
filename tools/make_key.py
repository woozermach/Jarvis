# -*- coding: utf-8 -*-
"""Выпуск своего ключа Pro (владельцу, друзьям, для тестов). Нужен секрет data/license_private.key — он есть только у владельца.

  .venv\\Scripts\\python.exe tools\\make_key.py "Имя или email" [--days 30]
Без --days ключ бессрочный."""
import json
import sys
import time
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from core import ed25519  # noqa: E402
from core.license import PUBLIC_KEY, b64e, parse_offline  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
args = [a for a in sys.argv[1:] if not a.startswith("--")]
days = float(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 0
if days:
    args = [a for a in args if a != sys.argv[sys.argv.index("--days") + 1]]
name = " ".join(args) or "без имени"
skp = BASE / "data" / "license_private.key"
if not skp.exists():
    sys.exit("Нет data/license_private.key — выпускать ключи может только владелец.")
sk = bytes.fromhex(skp.read_text().strip())
if ed25519.public_key(sk) != PUBLIC_KEY:
    sys.exit("Секрет не подходит к открытому ключу в core/license.py")
payload = json.dumps({"n": name, "p": "pro", "i": uuid.uuid4().hex[:10], "t": int(time.time()),
                      "e": int(time.time() + days * 86400) if days else 0}, ensure_ascii=False, separators=(",", ":")).encode()
key = "PRO-" + b64e(payload) + "." + b64e(ed25519.sign(sk, payload))
assert parse_offline(key)
print(key)
