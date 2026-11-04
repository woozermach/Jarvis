# -*- coding: utf-8 -*-
"""Переводит недостающие строки интерфейса из ui/i18n/en.json на все языки через Gemini (ключ из config.json).
  .venv\\Scripts\\python.exe tools\\translate_i18n.py [de fr ...]"""
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.config import Config  # noqa: E402
from core.gemini import Gemini  # noqa: E402

LANG_NAMES = {"de": "German", "fr": "French", "es": "Spanish (Spain)", "it": "Italian", "pl": "Polish", "cs": "Czech",
              "sk": "Slovak", "uk": "Ukrainian", "ru": "Russian"}
I18N = BASE / "ui" / "i18n"
RULES = """You translate the user interface of "Sayro", a voice AI assistant app for Windows PCs, from English into {lang}.
Rules:
- Return ONLY a JSON object with exactly the same keys and the translated strings as values.
- Keep {{placeholders}} like {{name}}, {{v}}, {{s}} exactly as they are. Keep emoji, symbols (→ ✓ ⚠ ⬆ ·), keyboard names (Ctrl+Alt+J, Win+Alt+G), URLs and product names (Sayro, Google, Gemini, Telegram, Discord, Steam, NVIDIA, Xbox Game Bar, Windows) unchanged.
- Keep the “|” separators and the line numbering in multi-step strings.
- Use the natural, concise tone Apple uses in its software in {lang}. Buttons are short. Keep quotes as typographic quotes of {lang}.
- Phrases in quotes are examples of what the user SAYS to the assistant: translate them as natural spoken commands in {lang}, and translate the wake phrase “Hey Sayro” naturally (e.g. German “Hey Sayro”, Russian «Эй, Сайро»).
- Keys starting with "tool." are short lowercase status labels shown while the assistant works (e.g. "searching the web").
- Keys starting with "py." are notifications; "\\n" are line breaks — keep them."""


def main():
    cfg = Config()
    if not cfg.get("gemini_api_key"):
        sys.exit("нет ключа Gemini")
    g = Gemini(cfg)
    try:
        g.refresh_models()
    except Exception as e:
        print("models:", e)
    en = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    langs = [a for a in sys.argv[1:] if a in LANG_NAMES] or list(LANG_NAMES)
    total = 0
    for lang in langs:
        path = I18N / f"{lang}.json"
        have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        miss = {k: v for k, v in en.items() if k not in have and v}
        print(f"[{lang}] не хватает {len(miss)}", flush=True)
        keys = list(miss)
        for i in range(0, len(keys), 70):
            chunk = {k: miss[k] for k in keys[i:i + 70]}
            for attempt in range(3):
                try:
                    _, j = g.generate([{"role": "user", "parts": [{"text": json.dumps(chunk, ensure_ascii=False)}]}],
                                      system=RULES.format(lang=LANG_NAMES[lang]), timeout=120,
                                      gen_cfg={"responseMimeType": "application/json", "temperature": 0.2})
                    out = json.loads(g.text_of(j))
                    bad = [k for k in chunk if k not in out or not isinstance(out[k], str)
                           or sorted(__import__("re").findall(r"\{\w+\}", out[k])) != sorted(__import__("re").findall(r"\{\w+\}", chunk[k]))]
                    for k in chunk:
                        if k in out and k not in bad:
                            have[k] = out[k]
                    print(f"  {lang} {i + len(chunk)}/{len(keys)} ok, проблем {len(bad)}", flush=True)
                    if not bad:
                        break
                    chunk = {k: chunk[k] for k in bad}
                except Exception as e:
                    print(f"  {lang} ошибка: {str(e)[:150]}", flush=True)
                    time.sleep(4)
            path.write_text(json.dumps(have, ensure_ascii=False, indent=0), encoding="utf-8")
        total += len(miss)
    print(f"Готово: переведено строк {total}")


if __name__ == "__main__":
    main()
