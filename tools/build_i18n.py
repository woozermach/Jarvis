# -*- coding: utf-8 -*-
"""Собирает английский словарь ui/i18n/en.json из ui/index.html (data-i18n*), STR в ui/app.js и core/i18n.py (py.*).
Переводы для других языков лежат рядом (<lang>.json); missing.py показывает, каких ключей там не хватает.
  python tools/build_i18n.py            — пересобрать en.json
  python tools/build_i18n.py --missing  — вывести недостающие ключи по языкам (JSON)"""
import html
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
UI = BASE / "ui"


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack = {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-i18n-ph" in a and a.get("placeholder"):
            self.out.setdefault(a["data-i18n-ph"], a["placeholder"])
        self.stack.append([a.get("data-i18n"), ""])

    def handle_endtag(self, tag):
        if self.stack:
            key, text = self.stack.pop()
            if key:
                self.out.setdefault(key, " ".join(text.split()))
            if self.stack:
                self.stack[-1][1] += text

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][1] += data


def collect():
    p = P()
    p.feed((UI / "index.html").read_text(encoding="utf-8"))
    d = dict(p.out)
    js = (UI / "app.js").read_text(encoding="utf-8")
    objs = re.findall(r"const STR = (\{.*?\n\});", js, re.S) + re.findall(r"Object\.assign\(STR, (\{.*?\n\})\);", js, re.S)
    for o in objs:
        r = subprocess.run(["node", "-e", f"process.stdout.write(JSON.stringify({o}))"], capture_output=True, text=True, encoding="utf-8")
        d.update(json.loads(r.stdout))
    from core.i18n import PY, PY_ONLY
    for _, k, en in PY:
        d["py." + k] = en
    for k, en in PY_ONLY.items():
        d["py." + k] = en
    return d


if __name__ == "__main__":
    en = collect()
    if "--missing" in sys.argv:
        miss = {}
        for f in sorted(UI.glob("i18n/*.json")):
            if f.stem == "en":
                continue
            have = json.loads(f.read_text(encoding="utf-8"))
            miss[f.stem] = [k for k in en if k not in have]
        print(json.dumps(miss, ensure_ascii=False))
    else:
        (UI / "i18n").mkdir(exist_ok=True)
        (UI / "i18n" / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"en.json: {len(en)} ключей")
