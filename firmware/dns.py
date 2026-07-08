"""DNS proxy with adblock filtering.

Blocking layers (in order):
1. SAFELIST — skip domains in whitelist
2. Heuristic — "ad.*" pattern matching
3. Keyword — telemetry/analytics/doubleclick...
4. Binary search — FNV-1a 32-bit hash against blocked.bin

Unblocked queries are proxied upstream to 1.1.1.1.
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
        self.stats = stats
        self.sock = None
        self.upstream = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(False)
        self.sock.bind(("0.0.0.0", self.PORT))
        self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream.settimeout(2.0)
        print(f"DNS server on port {self.PORT}")
        return self.sock

    def poll(self):
        readable, _, _ = select.select([self.sock], [], [], 1.0)
        if not readable:
            return False
        request, addr = self.sock.recvfrom(512)
        if len(request) < 12:
            return False
        domain = self._parse_domain(request)
        blocked = False
        if domain:
            if self._is_blocked(domain):
                self.stats.add(domain, True)
                self.sock.sendto(self._block_response(request), addr)
                blocked = True
            else:
                self.stats.add(domain, False)
                self._proxy(request, addr)
        else:
            self._proxy(request, addr)
        gc.collect()
        return blocked

    def _parse_domain(self, data):
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

    def _is_blocked(self, domain):
        if domain in self.SAFELIST:
            return False
        parts = domain.split(".")
        if not parts:
            return False
        first = parts[0]
        if first.startswith("ad"):
            suffix = first[2:]
            if not suffix or suffix == "s" or suffix.isdigit() or (suffix.startswith("s") and suffix[1:].isdigit()):
                return True
        for part in parts:
            if part in self.KEYWORDS:
                return True
        return self._hash_search(self._fnv1a(domain.encode("utf-8")))

    def _fnv1a(self, data):
        h = 0x811C9DC5
        for b in data:
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
        return h

    def _hash_search(self, target):
        try:
            with open(self.BLOCKED_BIN, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                count = size // 4
                lo, hi = 0, count - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    f.seek(mid * 4)
                    val = struct.unpack("<I", f.read(4))[0]
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
        question = request[12 : offset + 4]
        answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x01\x2c\x00\x04\x00\x00\x00\x00"
        return tx_id + flags + counts + question + answer

    def _proxy(self, request, addr):
        try:
            self.upstream.sendto(request, (self.UPSTREAM, self.PORT))
            response, _ = self.upstream.recvfrom(1024)
            self.sock.sendto(response, addr)
        except:
            pass
