# -*- coding: utf-8 -*-
"""Поиск без ключей: DuckDuckGo HTML + извлечение текста страницы."""
import html as htmlmod
import logging
import re
import urllib.parse

import requests

log = logging.getLogger("jarvis.web")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0 Safari/537.36")


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return htmlmod.unescape(re.sub(r"\s+", " ", s)).strip()


def ddg_search(query, n=6):
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "ru-ru"},
                          headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"}, timeout=12)
        r.raise_for_status()
    except Exception as e:
        log.warning("ddg: %s", e)
        return []
    out = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                        r.text, flags=re.S)
    for href, title, rest in blocks:
        url = href
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            url = urllib.parse.unquote(m.group(1))
        if url.startswith("//"):
            url = "https:" + url
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):
            continue
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, flags=re.S)
        out.append({"title": _clean(title), "url": url, "snippet": _clean(sm.group(1)) if sm else ""})
        if len(out) >= n:
            break
    return out


def fetch_text(url, limit=4000):
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"}, timeout=8)
        if "text/html" not in r.headers.get("content-type", ""):
            return ""
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        t = r.text
    except Exception:
        return ""
    t = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav|form)[^>]*>.*?</\1>", " ", t)
    t = _clean(t)
    return t[:limit]


def youtube_first(query):
    """ID первого видео в поиске YouTube (без API)."""
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": query, "hl": "ru"},
                         headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"},
                         cookies={"CONSENT": "YES+cb", "SOCS": "CAI"}, timeout=10)
        ids = re.findall(r'"videoId":"([\w-]{11})"', r.text)
        titles = re.findall(r'"title":\{"runs":\[\{"text":"(.*?)"\}', r.text)
        if ids:
            return ids[0], (htmlmod.unescape(titles[0]) if titles else "")
    except Exception as e:
        log.warning("youtube: %s", e)
    return None, ""


# ───────────── поиск через установленный Edge (без ботов-капч) ─────────────
import os
import subprocess
import threading
import time
from pathlib import Path

_edge_lock = threading.Lock()


def _edge_exe():
    for root in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LocalAppData")):
        if root:
            p = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if p.exists():
                return str(p)
    return None


def edge_dump(url, timeout=25):
    """Загружает страницу в фоновом (headless) Edge и возвращает готовый DOM."""
    exe = _edge_exe()
    if not exe:
        return ""
    prof = Path(__file__).resolve().parent.parent / "data" / "edge_headless"
    prof.mkdir(parents=True, exist_ok=True)
    with _edge_lock:
        try:
            r = subprocess.run([exe, "--headless=new", f"--user-data-dir={prof}", "--disable-gpu", "--no-first-run",
                                "--no-default-browser-check", "--lang=ru", "--mute-audio", "--virtual-time-budget=3000",
                                "--dump-dom", url], capture_output=True, timeout=timeout, creationflags=0x08000000)
            return r.stdout.decode("utf-8", "replace")
        except Exception as e:
            log.warning("edge_dump: %s", e)
            return ""


def _text(dom):
    dom = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", dom)
    return htmlmod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dom))).strip()


def google_search(query, n=8):
    """Выдача Google: блок ответа + результаты (заголовок, сайт, сниппет)."""
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "ru", "num": 10})
    dom = edge_dump(url)
    if not dom or "<h3" not in dom:
        return None
    results = []
    blocks = re.split(r'<div[^>]+class="MjjYud"', dom)[1:] or [dom]
    for b in blocks:
        h = re.search(r"<h3[^>]*>(.*?)</h3>", b, re.S)
        if not h:
            continue
        cite = re.search(r"<cite[^>]*>(.*?)</cite>", b, re.S)
        site = _clean(cite.group(1)).split(" › ")[0] if cite else ""
        sn = re.search(r'class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>', b, re.S)
        results.append({"title": _clean(h.group(1)), "url": site, "snippet": _clean(sn.group(1)) if sn else ""})
        if len(results) >= n:
            break
    full = _text(dom)
    answer = ""
    i = full.find("Результаты поиска")
    if i >= 0 and results:
        j = full.find(results[0]["title"][:30], i)
        answer = full[i + len("Результаты поиска"): j if j > i else i + 900].strip()[:700]
    return {"answer_box": answer, "results": results}


def google_news(query, n=8):
    try:
        r = requests.get("https://news.google.com/rss/search",
                         params={"q": query, "hl": "ru", "gl": "SK", "ceid": "SK:ru"}, headers={"User-Agent": UA}, timeout=10)
        items = re.findall(r"<item>(.*?)</item>", r.text, re.S)[:n]
        out = []
        for it in items:
            t = re.search(r"<title>(.*?)</title>", it, re.S)
            d = re.search(r"<pubDate>(.*?)</pubDate>", it)
            s = re.search(r"<source[^>]*>(.*?)</source>", it)
            out.append({"title": _clean(t.group(1)) if t else "", "date": d.group(1)[:16] if d else "",
                        "source": _clean(s.group(1)) if s else ""})
        return out
    except Exception as e:
        log.warning("news: %s", e)
        return []


def wikipedia(query, lang="ru"):
    try:
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 1, "prop": "extracts",
            "exintro": 1, "explaintext": 1, "format": "json"}, headers={"User-Agent": UA}, timeout=10).json()
        pages = list((r.get("query") or {}).get("pages", {}).values())
        if pages:
            return {"title": pages[0].get("title"), "extract": (pages[0].get("extract") or "")[:2500]}
    except Exception as e:
        log.warning("wiki: %s", e)
    return None
