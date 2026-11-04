# -*- coding: utf-8 -*-
"""Текстовые утилиты: нормализация, транслит, склонения, числа."""
import re

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
                "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s\.\-:/+]", " ", s)
    s = re.sub(r"(?<!\w)[\.\-:/]+|[\.\-:/]+(?!\w)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def translit(s: str) -> str:
    return "".join(_TR.get(ch, ch) for ch in (s or "").lower())


def plural(n, forms) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def pct(n) -> str:
    n = int(round(float(n)))
    return f"{n}%"


def degrees(t) -> str:
    t = int(round(float(t)))
    return f"{'+' if t > 0 else ''}{t}°"


def duration_words(sec) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    out = []
    if h:
        out.append(f"{h} {plural(h, ('час', 'часа', 'часов'))}")
    if m:
        out.append(f"{m} {plural(m, ('минуту', 'минуты', 'минут'))}")
    if s or not out:
        out.append(f"{s} {plural(s, ('секунду', 'секунды', 'секунд'))}")
    return " ".join(out)


def match_stem(text: str, table: dict):
    """Ищет в тексте самый длинный ключ-основу. Ключ с '$' — только целым словом.
    Возвращает (значение, длина_ключа) или (None, 0)."""
    for key in sorted(table, key=len, reverse=True):
        whole = key.endswith("$")
        k = key.rstrip("$")
        pat = r"(?:^|\s)" + re.escape(k) + (r"(?:\s|$)" if whole else "")
        if re.search(pat, text):
            return table[key], len(k)
    return None, 0
