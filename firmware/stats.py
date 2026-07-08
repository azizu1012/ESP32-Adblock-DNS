"""Thống kê truy vấn với cửa sổ 7 ngày.

Theo dõi tổng số/chặn, hoạt động gần đây, top domain bị chặn.
Dữ liệu lưu vào stats.json mỗi 30s. Mục cũ (day < today-7)
bị xoá tự động khi load/save.
"""
import gc, json, os, _thread
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
    """Phân loại domain vào nhóm: telemetry, tracking, malware, social, ads."""
    for cat, keywords in CAT_RULES:
        for kw in keywords:
            if kw in domain:
                return cat
    return "ads"


class Stats:
    def __init__(self):
        """Khởi tạo stats, xoá sạch và load từ file."""
        self.lock = _thread.allocate_lock()
        self.dirty = False
        self.last_save = 0
        self.reset()
        self.load()

    def reset(self):
        """Đặt lại tất cả bộ đếm về 0."""
        self.total = 0
        self.blocked = 0
        self.start_time = time()
        self.last_blocked = ""
        self.recent = []
        self.top = {}

    @property
    def _today(self):
        return int(time() // 86400)

    def add(self, domain, is_blocked, layer=None, client_ip=""):
        """Ghi nhận một truy vấn: tăng bộ đếm, cập nhật top và recent."""
        self.lock.acquire()
        try:
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
            self.recent.append((domain, is_blocked, layer, time(), client_ip))
            if len(self.recent) > 200:
                self.recent = self.recent[-100:]
        finally:
            self.lock.release()

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
        """Xoá các mục cũ hơn 7 ngày."""
        cutoff = self._today - 7
        todel = [d for d, v in self.top.items() if v.get("d", 0) < cutoff]
        for d in todel:
            del self.top[d]
        if todel:
            self.dirty = True

    def top_blocked(self, n=10):
        """Trả về n domain bị chặn nhiều nhất, sắp xếp giảm dần."""
        return sorted(self.top.items(), key=lambda x: -x[1]["c"])[:n]

    def load(self):
        """Đọc stats.json, phục hồi top và dọn dẹp mục cũ."""
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
        """Ghi stats.json nếu có thay đổi (dirty flag)."""
        if not self.dirty:
            return
        self.lock.acquire()
        try:
            self.dirty = False
            self._cleanup()
            data = {}
            for domain, val in self.top.items():
                data[domain] = val
            data["_ts"] = int(time())
            with open(FILE, "w") as f:
                json.dump(data, f)
            self.last_save = time()
        except:
            pass
        finally:
            self.lock.release()

    def tick(self):
        """Tự động lưu nếu dirty hơn 30 giây."""
        if self.dirty and time() - self.last_save > 30:
            self.save()

    @staticmethod
    def flash_free():
        """Dung lượng trống trên filesystem (bytes)."""
        try:
            import os
            s = os.statvfs("/")
            return s[0] * s[3]
        except:
            return 0

    @staticmethod
    def flash_total():
        """Tổng dung lượng filesystem (bytes)."""
        try:
            import os
            s = os.statvfs("/")
            return s[0] * s[2]
        except:
            return 0

    @staticmethod
    def flash_chip():
        """Tổng dung lượng chip flash (bytes) — thường 4MB."""
        try:
            import esp
            return esp.flash_size()
        except:
            return 0

    @staticmethod
    def blocked_count():
        """Số lượng entry trong blocked.bin (từ kích thước file)."""
        try:
            return os.stat("blocked.bin")[6] // 8
        except:
            return 0

    @staticmethod
    def cpu_freq():
        """Tần số CPU (MHz)."""
        try:
            import machine
            return machine.freq() // 1000000
        except:
            return 0

    @staticmethod
    def core_count():
        """Số nhân CPU — ESP32-D0WD-V3 có 2 nhân."""
        try:
            return 2
        except:
            return 1

    def to_dict(self):
        """Xuất toàn bộ thống kê dạng dict để serve JSON API."""
        self.lock.acquire()
        now = time()
        try:
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
                "recent": [(d, b, categorize(d) if b else "", int(now - t), layer, ip) for d, b, layer, t, ip in self.recent[-50:]],
                "top": [{"d": d, "c": v["c"], "g": categorize(d)} for d, v in self.top_blocked(10)],
                "flash_free": self.flash_free(),
                "flash_total": self.flash_total(),
                "flash_chip": self.flash_chip(),
                "blocklist_entries": self.blocked_count(),
                "cpu_freq": self.cpu_freq(),
                "core_count": self.core_count(),
            }
        finally:
            self.lock.release()
