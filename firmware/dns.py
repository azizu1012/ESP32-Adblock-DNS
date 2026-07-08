"""DNS proxy với adblock filtering.

Blocking layers (theo thứ tự):
1. SAFELIST — bỏ qua domain trong whitelist
2. Heuristic — pattern "ad.*"
3. Keyword — telemetry/analytics/doubleclick...
4. Binary search — FNV-1a 64-bit hash trên blocked.bin

GC threshold được đặt ở init; thu gom mỗi 100 poll để tránh
stop-the-world trên mỗi truy vấn.
"""
import socket
import struct
import select
import gc


class DNSServer:
    UPSTREAM = "1.1.1.1"
    PORT = 53
    BLOCKED_BIN = "blocked.bin"
    SAFELIST = ("adwords.google.com", "adidas.com")
    KEYWORDS = (
        "telemetry", "analytics", "adserver", "adsystem",
        "doubleclick", "adcolony", "applovin", "popunder",
    )

    def __init__(self, stats):
        """Khởi tạo DNS server, đặt GC threshold để thu gom sớm."""
        self.stats = stats
        self.sock = None
        self.upstream = None
        self._gc_cnt = 0
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

    def start(self):
        """Mở socket DNS (UDP) và socket upstream."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(False)
        self.sock.bind(("0.0.0.0", self.PORT))
        self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream.settimeout(2.0)
        print(f"DNS server on port {self.PORT}")
        return self.sock

    def poll(self):
        """Poll một gói DNS: parse, check block, proxy hoặc trả về fake response.
        
        Returns True nếu bị chặn (block).
        """
        readable, _, _ = select.select([self.sock], [], [], 1.0)
        if not readable:
            self._gc_tick()
            return False
        request, addr = self.sock.recvfrom(512)
        if len(request) < 12:
            return False
        domain = self._parse_domain(request)
        blocked = False
        layer = None
        if domain:
            is_blocked, layer = self._check(domain)
            if is_blocked:
                self.stats.add(domain, True, layer)
                self.sock.sendto(self._block_response(request), addr)
                blocked = True
            else:
                self.stats.add(domain, False)
                self._proxy(request, addr)
        else:
            self._proxy(request, addr)
        self._gc_tick()
        return blocked

    def _gc_tick(self):
        """Thu gom rác mỗi 100 poll để tránh STW đột ngột."""
        self._gc_cnt = (self._gc_cnt + 1) % 100
        if self._gc_cnt == 0:
            gc.collect()

    def _parse_domain(self, data):
        """Giải nén domain name từ DNS request (format nhãn độ dài)."""
        try:
            offset = 12
            labels = []
            while True:
                length = data[offset]
                if length == 0:
                    break
                offset += 1
                labels.append(data[offset : offset + length].decode().lower())
                offset += length
            return ".".join(labels)
        except:
            return None

    def _check(self, domain):
        """Kiểm tra domain qua 4 lớp: SAFELIST → heuristic → keyword → hash.
        
        Returns (blocked: bool, layer: str|None).
        """
        if domain in self.SAFELIST:
            return False, None
        parts = domain.split(".")
        if not parts:
            return False, None
        first = parts[0]
        if first.startswith("ad"):
            suffix = first[2:]
            if not suffix or suffix == "s" or suffix.isdigit() or (suffix.startswith("s") and suffix[1:].isdigit()):
                return True, "heuristic"
        for part in parts:
            if part in self.KEYWORDS:
                return True, "keyword"
        if self._hash_search(self._fnv1a_64(domain.encode("utf-8"))):
            return True, "hash"
        return False, None

    @staticmethod
    def _fnv1a_64(data):
        """FNV-1a 64-bit hash — nhanh, không mã hoá, 3 toán tử/byte."""
        h = 0xCBF29CE484222325
        p = 0x100000001B3
        for b in data:
            h = ((h ^ b) * p) & 0xFFFFFFFFFFFFFFFF
        return h

    def _hash_search(self, target):
        """Tìm hash trong blocked.bin bằng binary search (trên flash, không vào RAM)."""
        try:
            with open(self.BLOCKED_BIN, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                count = size // 8
                lo, hi = 0, count - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    f.seek(mid * 8)
                    val = struct.unpack("<Q", f.read(8))[0]
                    if val == target:
                        return True
                    if val < target:
                        lo = mid + 1
                    else:
                        hi = mid - 1
        except:
            pass
        return False

    @staticmethod
    def _block_response(request):
        """Tạo DNS response giả chặn domain: A → 0.0.0.0, AAAA → ::1."""
        tx_id = request[0:2]
        flags = b"\x81\x80"
        counts = b"\x00\x01\x00\x01\x00\x00\x00\x00"
        offset = 12
        while True:
            length = request[offset]
            if length == 0:
                offset += 1
                break
            offset += 1 + length
        qtype = request[offset : offset + 2]
        question = request[12 : offset + 4]
        if qtype == b"\x00\x1c":
            answer = b"\xc0\x0c\x00\x1c\x00\x01\x00\x00\x01\x2c\x00\x10" + b"\x00" * 16
        else:
            answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x01\x2c\x00\x04\x00\x00\x00\x00"
        return tx_id + flags + counts + question + answer

    def _proxy(self, request, addr):
        """Chuyển tiếp DNS request lên upstream (1.1.1.1) và gửi response về client."""
        try:
            self.upstream.sendto(request, (self.UPSTREAM, self.PORT))
            response, _ = self.upstream.recvfrom(1024)
            self.sock.sendto(response, addr)
        except:
            pass
