# -*- coding: utf-8 -*-
"""Название продукта — ТОЛЬКО здесь. Сменить бренд = поменять этот файл (и иконку ui/jarvis.ico)."""
import re

NAME = "Oswin"
NAMES = {"ru": "Освин", "uk": "Освін"}          # как писать имя в языках с другой азбукой
TAGLINE = "Your voice for your PC"
APP_ID = "oswin"                                # имя ярлыка автозапуска, окна и т.п.
WINDOW_TITLE = NAME
LEGACY_TITLES = ("Sayro", "J.A.R.V.I.S")       # окна прежних версий — тоже «свои»
_OWN_TITLES = {WINDOW_TITLE, "Sayro", "J.A.R.V.I.S", "J.A.R.V.I.S."}


def is_own_window(title, legacy=True):
    """Окно интерфейса — только при ТОЧНОМ совпадении заголовка. По началу строки нельзя:
    вкладка браузера с нашим сайтом («Oswin — the voice assistant… - Microsoft Edge») тоже начинается с «Oswin»."""
    t = (title or "").strip()
    return t == WINDOW_TITLE or (legacy and t in _OWN_TITLES)
LEGACY_NAMES = ("Sayro", "J.A.R.V.I.S.")        # прежние имена ярлыков автозапуска
SITE = "https://woozermach.github.io/Jarvis/"

# как распознаватель речи может услышать имя (ru/uk/en/de/fr/es/it/pl/sk/cs)
WAKE_WORDS = {
    # «Hey Oswin»: как его слышит распознаватель на разных языках (проверено TTS → STT, см. selftest --only wake2)
    "oswin": (r"\bos\s?wi?y?n\b|\boswyn\b|\bozwin\b|osborne?\b|\bosv[ií]n\b|\bosvin\b|\bos\s?vin\b|"
              r"освин|освін|осв[иі]н|озвин|(?:эй|ей|гей|hey|hej|hi|hallo)[\s,]+ось\s?він"),
    "jarvis": r"(?:дж|ж|ч|д)[аеэ]р?[вб][иы]с|jarvis|джарви",
}


def name(lang="en"):
    return NAMES.get(lang, NAME)


def wake_re(word="oswin"):
    word = "oswin" if word == "sayro" else word
    return re.compile(WAKE_WORDS.get(word, WAKE_WORDS["oswin"]), re.I)
