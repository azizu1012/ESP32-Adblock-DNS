"""Thống kê truy vấn với cửa sổ 7 ngày.

Theo dõi tổng số/chặn, hoạt động gần đây, top domain bị chặn.
Dữ liệu lưu vào stats.json mỗi 30s. Mục cũ (day < today-7)
bị xoá tự động khi load/save.
"""
import gc, json, os, _thread
from time import time
try:
    import utime
    ticks_ms = utime.ticks_ms
    ticks_diff = utime.ticks_diff
except ImportError:
    # PC Fallback
    def ticks_ms():
        import time
        return int(time.time() * 1000)
    def ticks_diff(t1, t2):
        return t1 - t2


TIER1_EXACT = {
    "doubleclick.net": ["ads", "tracking"],
    "firebaselogging-pa.googleapis.com": ["analytics"],
    "mask.apple-dns.net": ["privacy"],
    "default.exp-tas.com": ["experiment"],
    "settings-win.data.microsoft.com": ["telemetry"],
    "functional.events.data.microsoft.com": ["telemetry"],
    "prod.otel.kaizen.nvidia.com": ["telemetry"]
}

TIER2_PREFIX = (
    ("events.telemetry.", ["telemetry"]),
    ("prod.otel.", ["telemetry"]),
    ("gx-target-experiments-", ["experiment"])
)

TIER3_CONTAINS = (
    ("ads", ["doubleclick", "googlead", "admob", "adnxs", "rubicon", "openx",
             "criteo", "pubmatic", "adsystem", "adservice", "adserver", "advertising"]),
    ("tracking", ["track", "pixel", "beacon", "click"]),
    ("telemetry", ["telemetry", "diagnostics", "monitor", "metrics", "appinsight", 
                   "events.data", "prod.otel", "functional.events", "dc.services", "settings-win", "inputsuggestions"]),
    ("analytics", ["analytics", "firebaselogging", "firebase-settings", "log-upload"]),
    ("privacy", ["mask.apple-dns", "mask-h2", "mask.icloud"]),
    ("malware", ["malware", "phish", "ransom", "trojan", "exploit", "c2.", "shadowserver"]),
    ("experiment", ["experiment", "exp-tas", "gx-target-experiments", "ab-testing", "tas.msedge", "tas.microsoft"])
)

FILE = "stats.json"


def categorize(domain):
    """Phân loại domain qua 4 tầng: Exact -> Prefix -> Contains -> Fallback."""
    domain = domain.lower()
    
    # Tier 1: Exact match
    if domain in TIER1_EXACT:
        return TIER1_EXACT[domain]
        
    # Tier 2: Prefix match
    for prefix, tags in TIER2_PREFIX:
        if domain.startswith(prefix):
            return tags
            
    # Tier 3: Contains match (multi-tag collection)
    res = []
    for cat, keywords in TIER3_CONTAINS:
        for kw in keywords:
            if kw in domain:
                res.append(cat)
                break
    if res:
        return res
        
    # Tier 4: Fallback
    return ["ads"]


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
        self.start_ticks = ticks_ms()
        self.last_blocked = ""
        self.recent = []
        self.top = {}
        self.client_ips = {}
        self.upstream_ip = "1.1.1.1"
        self.upstream_rtt = 0
        self.blocked_categories = {"ads": 0, "tracking": 0, "telemetry": 0, "analytics": 0, "privacy": 0, "malware": 0, "experiment": 0}

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
                if domain not in self.top:
                    # Prevent OOM from random domain spam (capped at 50)
                    if len(self.top) >= 50:
                        min_k = min(self.top, key=lambda k: self.top[k]["c"])
                        del self.top[min_k]
                    self.top[domain] = {"c": 0, "s": layer, "d": self._today}
                self.top[domain]["c"] += 1
                self.top[domain]["d"] = self._today
                self.dirty = True
                
                cats = categorize(domain)
                for cat in cats:
                    if cat in self.blocked_categories:
                        self.blocked_categories[cat] += 1
            if client_ip:
                self.client_ips[client_ip] = time()
                # Prevent OOM from spoofed IPs
                if len(self.client_ips) > 50:
                    oldest_ip = min(self.client_ips, key=self.client_ips.get)
                    del self.client_ips[oldest_ip]
            self.recent.append((domain, is_blocked, layer, time(), client_ip))
            # Giam limit self.recent xuong 50 de tiet kiem TOI DA RAM cho Web Server
            if len(self.recent) > 50:
                self.recent = self.recent[-30:]
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
        try:
            return max(0, int(ticks_diff(ticks_ms(), self.start_ticks) // 1000))
        except Exception:
            return 0

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
                stripped = False
                for domain, val in raw.items():
                    # Lọc sạch các truy vấn Bonjour/mDNS/reverse DNS lịch sử
                    if domain.endswith(".arpa") or domain.endswith(".local"):
                        stripped = True
                        continue
                    if isinstance(val, dict):
                        self.top[domain] = {"c": val.get("c", 1), "d": val.get("d", 0)}
                    elif isinstance(val, int):
                        self.top[domain] = {"c": val, "d": 0}
                if stripped:
                    self.dirty = True
                self._cleanup()
            self.blocked_categories = {"ads": 0, "tracking": 0, "telemetry": 0, "analytics": 0, "privacy": 0, "malware": 0, "experiment": 0}
            for domain, val in self.top.items():
                cats = categorize(domain)
                for cat in cats:
                    if cat in self.blocked_categories:
                        self.blocked_categories[cat] += val.get("c", 0)
        except Exception:
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
        except Exception:
            pass
        finally:
            self.lock.release()

    def tick(self):
        """Tự động lưu nếu dirty hơn 5 phút (300s) — giảm 10x flash writes."""
        if self.dirty and time() - self.last_save > 300:
            self.save()

    @staticmethod
    def flash_free():
        """Dung lượng trống trên filesystem (bytes)."""
        try:
            import os
            s = os.statvfs("/")
            return s[0] * s[3]
        except Exception:
            return 0

    @staticmethod
    def flash_total():
        """Tổng dung lượng filesystem (bytes)."""
        try:
            import os
            s = os.statvfs("/")
            return s[0] * s[2]
        except Exception:
            return 0

    @staticmethod
    def flash_chip():
        """Tổng dung lượng chip flash (bytes) — thường 4MB."""
        try:
            import esp
            return esp.flash_size()
        except Exception:
            return 0

    @staticmethod
    def blocked_count():
        """Số lượng entry trong blocked.bin (lưu ở 4 byte cuối)."""
        try:
            import struct
            with open("blocked.bin", "rb") as f:
                f.seek(-4, 2)
                return struct.unpack("<I", f.read(4))[0]
        except Exception:
            return 0

    @staticmethod
    def cpu_freq():
        """Tần số CPU (MHz)."""
        try:
            import machine
            return machine.freq() // 1000000
        except Exception:
            return 0

    @staticmethod
    def core_count():
        """Số nhân CPU — ESP32-D0WD-V3 có 2 nhân."""
        try:
            return 2
        except Exception:
            return 1

    def to_dict(self):
        """Xuất thống kê tóm tắt dạng dict để serve JSON API (lược bỏ recent/top)."""
        self.lock.acquire()
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
                "categories": self.blocked_categories,
                "flash_free": self.flash_free(),
                "flash_total": self.flash_total(),
                "flash_chip": self.flash_chip(),
                "blocklist_entries": self.blocked_count(),
                "cpu_freq": self.cpu_freq(),
                "core_count": self.core_count(),
                "upstream": getattr(self, "upstream_ip", "1.1.1.1"),
                "upstream_rtt": getattr(self, "upstream_rtt", 0),
            }
        finally:
            self.lock.release()

    def to_recent_list(self):
        """Xuất danh sách 50 truy vấn gần đây."""
        self.lock.acquire()
        now = time()
        try:
            return [(d, b, categorize(d) if b else [], int(now - t), layer, ip) for d, b, layer, t, ip in self.recent[-50:]]
        finally:
            self.lock.release()

    def to_top_list(self):
        """Xuất danh sách top 10 domain bị chặn."""
        self.lock.acquire()
        try:
            return [{"d": d, "c": v["c"], "g": categorize(d)} for d, v in self.top_blocked(10)]
        finally:
            self.lock.release()
