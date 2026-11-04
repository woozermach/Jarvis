# -*- coding: utf-8 -*-
"""Постоянное хранилище: таймеры, задачи, заметки, долгая память, история разговора."""
import json
import threading
import time
import uuid

from .config import DATA_DIR

PATH = DATA_DIR / "data.json"


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.data = {"timers": [], "tasks": [], "notes": [], "memory": [], "history": [], "routines": [],
                     "quiet_until": 0, "last_briefing": ""}
        if PATH.exists():
            try:
                self.data.update(json.loads(PATH.read_text(encoding="utf-8")))
            except Exception:
                pass
        self.listeners = []

    def save(self):
        with self.lock:
            tmp = PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(PATH)
        for fn in self.listeners:
            try:
                fn()
            except Exception:
                pass

    @staticmethod
    def _id():
        return uuid.uuid4().hex[:8]

    # ── таймеры и напоминания ──
    def add_timer(self, due_ts: float, label: str, kind: str = "timer"):
        t = {"id": self._id(), "due": float(due_ts), "label": label or "", "kind": kind, "created": time.time()}
        with self.lock:
            self.data["timers"].append(t)
            self.data["timers"].sort(key=lambda x: x["due"])
        self.save()
        return t

    def cancel_timer(self, tid=None, label=None):
        with self.lock:
            before = len(self.data["timers"])
            if tid:
                self.data["timers"] = [t for t in self.data["timers"] if t["id"] != tid]
            elif label:
                low = label.lower()
                self.data["timers"] = [t for t in self.data["timers"] if low not in t["label"].lower()]
            else:
                self.data["timers"] = self.data["timers"][1:]
            n = before - len(self.data["timers"])
        self.save()
        return n

    def pop_due(self, now=None):
        now = now or time.time()
        with self.lock:
            due = [t for t in self.data["timers"] if t["due"] <= now]
            if due:
                self.data["timers"] = [t for t in self.data["timers"] if t["due"] > now]
        if due:
            self.save()
        return due

    # ── задачи ──
    def add_task(self, text):
        t = {"id": self._id(), "text": text.strip(), "done": False, "created": time.time()}
        with self.lock:
            self.data["tasks"].append(t)
        self.save()
        return t

    def set_task(self, tid=None, text=None, done=True, delete=False):
        with self.lock:
            hit = None
            for t in self.data["tasks"]:
                if (tid and t["id"] == tid) or (text and text.lower() in t["text"].lower()):
                    hit = t
                    break
            if not hit:
                return None
            if delete:
                self.data["tasks"].remove(hit)
            else:
                hit["done"] = bool(done)
        self.save()
        return hit

    def clear_done(self):
        with self.lock:
            self.data["tasks"] = [t for t in self.data["tasks"] if not t["done"]]
        self.save()

    # ── заметки ──
    def add_note(self, text):
        n = {"id": self._id(), "text": text.strip(), "created": time.time()}
        with self.lock:
            self.data["notes"].append(n)
            self.data["notes"] = self.data["notes"][-500:]
        self.save()
        return n

    # ── долгая память ──
    def remember(self, fact):
        with self.lock:
            for m in self.data["memory"]:
                if m["fact"].lower() == fact.lower():
                    return m
            m = {"id": self._id(), "fact": fact.strip(), "created": time.time()}
            self.data["memory"].append(m)
            self.data["memory"] = self.data["memory"][-200:]
        self.save()
        return m

    def forget(self, query):
        low = query.lower()
        with self.lock:
            before = len(self.data["memory"])
            self.data["memory"] = [m for m in self.data["memory"] if low not in m["fact"].lower()]
            n = before - len(self.data["memory"])
        self.save()
        return n

    # ── история разговора (для контекста между сессиями) ──
    def add_history(self, role, text):
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self.data["history"].append({"r": role, "t": text[:600], "ts": time.time()})
            self.data["history"] = self.data["history"][-40:]
        self.save()

    def recent_history(self, max_age=6 * 3600, n=16):
        cutoff = time.time() - max_age
        with self.lock:
            return [h for h in self.data["history"] if h["ts"] > cutoff][-n:]

    # ── режимы (сценарии из нескольких действий) ──
    def save_routine(self, name, steps, description=""):
        name = name.strip()
        with self.lock:
            self.data["routines"] = [r for r in self.data["routines"] if r["name"].lower() != name.lower()]
            r = {"id": self._id(), "name": name, "steps": steps, "description": description.strip(), "created": time.time()}
            self.data["routines"].append(r)
        self.save()
        return r

    def find_routine(self, name):
        from .util import norm
        q = norm(name).replace("режим", "").strip()
        with self.lock:
            rs = list(self.data["routines"])
        for r in rs:
            if norm(r["name"]) == norm(name) or r["id"] == name:
                return r
        for r in rs:
            n = norm(r["name"]).replace("режим", "").strip()
            if q and n and (q in n or n in q):
                return r
        # по началу слов: «игровой» ≈ «игра», «учёба» ≈ «учебный»
        for r in rs:
            n = norm(r["name"]).replace("режим", "").strip()
            if q and n and q[:4] == n[:4]:
                return r
        return None

    def delete_routine(self, name):
        r = self.find_routine(name)
        if not r:
            return None
        with self.lock:
            self.data["routines"] = [x for x in self.data["routines"] if x["id"] != r["id"]]
        self.save()
        return r

    def set_meta(self, key, value):
        with self.lock:
            self.data[key] = value
        self.save()

    def snapshot(self):
        with self.lock:
            d = {k: self.data.get(k, []) for k in ("timers", "tasks", "notes", "memory", "routines")}
            d["quiet_until"] = self.data.get("quiet_until", 0)
            return json.loads(json.dumps(d))
