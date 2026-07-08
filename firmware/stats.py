"""Persistent query statistics with 7-day rolling window.

Tracks total/blocked queries, recent activity, and top blocked domains.
Data is persisted to stats.json every 30s. Old entries (day < today-7)
are pruned automatically on load and save.
"""
import gc, json, os
from time import time


CAT_RULES = (
    ("telemetry", ["telemetry", "functional.events", "dc.services", "appinsight",
     "diagnostics", "monitor", "metrics", "events.data", "prod.otel",
     "in.applicationinsights"]),
    ("tracking", ["track", "analytics", "pixel", "beacon", "click",
     "doubleclick", "googlesyndication", "googlead", "admob",
     "adnxs", "rubicon", "openx", "criteo", "pubmatic",
     "adsystem", "adservice", "adserver", "advertising"]),
    ("malware", ["malware", "phish", "ransom", "trojan", "exploit",
     "c2.", "command.and.control", "shadowserver"]),
    ("social", ["facebook", "fbcdn", "instagram", "linkedin",
     "tiktok", "snapchat", "pinterest"]),
)


def categorize(domain):
    for cat, keywords in CAT_RULES:
        for kw in keywords:
            if kw in domain:
                return cat
    return "ads"


class Stats:
    def __init__(self):
        self.dirty = False
        self.last_save = 0
        self.reset()
        self.load()

    def reset(self):
        self.total = 0
        self.blocked = 0
        self.start_time = time()
        self.last_blocked = ""
        self.recent = []
        self.top = {}

    @property
    def _today(self):
        return int(time() // 86400)

    def add(self, domain, is_blocked):
        self.total += 1
        if is_blocked:
            self.blocked += 1
            self.last_blocked = domain
            today = self._today
            if domain in self.top:
                self.top[domain]["c"] += 1
            else:
                self.top[domain] = {"c": 1, "d": today}
            self.dirty = True
        self.recent.append((domain, is_blocked, time()))
        if len(self.recent) > 100:
            self.recent = self.recent[-50:]

    @property
    def allowed(self):
        return self.total - self.blocked

    @property
    def ratio(self):
        if self.total == 0:
            return 0
        return round(self.blocked / self.total * 100, 1)

    @property
    def uptime(self):
        return int(time() - self.start_time)

    @staticmethod
    def free_ram():
        return gc.mem_free()

    @staticmethod
    def alloc_ram():
        return gc.mem_alloc()

    @staticmethod
    def total_ram():
        return gc.mem_free() + gc.mem_alloc()

    def _cleanup(self):
        cutoff = self._today - 7
        todel = [d for d, v in self.top.items() if v.get("d", 0) < cutoff]
        for d in todel:
            del self.top[d]
        if todel:
            self.dirty = True

    def top_blocked(self, n=10):
        return sorted(self.top.items(), key=lambda x: -x[1]["c"])[:n]

    def load(self):
        self.top = {}
        try:
            with open(FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                raw = {k: v for k, v in data.items() if k != "_ts"}
                for domain, val in raw.items():
                    if isinstance(val, dict):
                        self.top[domain] = {"c": val.get("c", 1), "d": val.get("d", 0)}
                    elif isinstance(val, int):
                        self.top[domain] = {"c": val, "d": 0}
                self._cleanup()
            self.blocked = sum(v["c"] for v in self.top.values())
            self.total = self.blocked
        except:
            pass

    def save(self):
        if not self.dirty:
            return
        self.dirty = False
        self._cleanup()
        try:
            data = {}
            for domain, val in self.top.items():
                data[domain] = val
            data["_ts"] = int(time())
            with open(FILE, "w") as f:
                json.dump(data, f)
            self.last_save = time()
        except:
            pass

    def tick(self):
        if self.dirty and time() - self.last_save > 30:
            self.save()

    def to_dict(self):
        now = time()
        return {
            "total": self.total,
            "blocked": self.blocked,
            "allowed": self.allowed,
            "ratio": self.ratio,
            "uptime": self.uptime,
            "free_ram": self.free_ram(),
            "alloc_ram": self.alloc_ram(),
            "total_ram": self.total_ram(),
            "last_blocked": self.last_blocked,
            "recent": [(d, b, categorize(d) if b else "", int(now - t)) for d, b, t in self.recent[-20:]],
            "top": [{"d": d, "c": v["c"], "g": categorize(d)} for d, v in self.top_blocked(10)],
        }
