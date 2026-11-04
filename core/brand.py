# -*- coding: utf-8 -*-
"""Название продукта — ТОЛЬКО здесь. Сменить бренд = поменять этот файл (и иконку ui/app.ico)."""
import re

NAME = "Sayro"
NAMES = {"ru": "Сайро", "uk": "Сайро"}          # как писать имя в языках с другой азбукой
TAGLINE = "Your voice for your PC"
APP_ID = "sayro"                                # имя ярлыка автозапуска, окна и т.п.
WINDOW_TITLE = NAME
SITE = "https://github.com/woozermach/Jarvis"

# как распознаватель речи может услышать имя (ru/uk/en/de/fr/es/it/pl/sk/cs)
WAKE_WORDS = {
    "sayro": r"сайр[оауы]|саир[оа]|сай\s?ро|s[ae]y\s?ro|sai\s?ro|sayr[oa]|seiro|sajro|sejro|cairo|kairo|кайро",
    "jarvis": r"(?:дж|ж|ч|д)[аеэ]р?[вб][иы]с|jarvis|джарви",
}


def name(lang="en"):
    return NAMES.get(lang, NAME)


def wake_re(word="sayro"):
    return re.compile(WAKE_WORDS.get(word, WAKE_WORDS["sayro"]), re.I)
