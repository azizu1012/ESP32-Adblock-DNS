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
import time

# Fallback for standard Python desktop testing
if not hasattr(time, "ticks_ms"):
    def ticks_ms():
        return int(time.time() * 1000)
    def ticks_diff(t1, t2):
        return t1 - t2
    time.ticks_ms = ticks_ms
    time.ticks_diff = ticks_diff


class DNSServer:
    UPSTREAM = "1.1.1.1"
    PORT = 53
    BLOCKED_BIN = "blocked.bin"
    SAFELIST = (
        "adwords.google.com", "adidas.com",
        "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com",
    )
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
        self.upstream_ip = "1.1.1.1"
        self.upstream_rtt = 0
        self.last_opt_ticks = time.ticks_ms()
        self.last_query_ticks = time.ticks_ms()
        self.rtt_sum = 0
        self.rtt_cnt = 0
        self.wifi = None
        self.stats.upstream_ip = "1.1.1.1"
        self.stats.upstream_rtt = 0
        try:
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        except:
            pass

    def _measure_rtt(self, ip, timeout_ms=300):
        """Đo độ trễ RTT tới một IP bằng cách gửi DNS query cho google.com."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_ms / 1000.0)
        try:
            t0 = time.ticks_ms()
            q = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01'
            sock.sendto(q, (ip, 53))
            resp, _ = sock.recvfrom(512)
            if resp and resp[:2] == b'\xaa\xbb':
                return time.ticks_diff(time.ticks_ms(), t0)
        except:
            pass
        finally:
            sock.close()
        return 999999

    def optimize_upstream(self, wifi_manager=None):
        """Đo độ trễ tới nhiều DNS server và chọn upstream tối ưu nhất."""
        if wifi_manager:
            self.wifi = wifi_manager
        else:
            wifi_manager = self.wifi

        candidates = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "1.0.0.1", "8.8.4.4"]
        if wifi_manager and wifi_manager.is_connected():
            try:
                dhcp_dns = wifi_manager.ifconfig()[3]
                if dhcp_dns and dhcp_dns != "0.0.0.0" and dhcp_dns not in candidates:
                    candidates.insert(0, dhcp_dns)
            except:
                pass

        best_ip = self.upstream_ip
        best_rtt = 999999
        print(f"[DNS] Optimizing upstream among {candidates}...")
        for ip in candidates:
            r1 = self._measure_rtt(ip, 300)
            if r1 < 999999:
                r2 = self._measure_rtt(ip, 300)
                rtt = (r1 + r2) // 2
            else:
                rtt = 999999
            print(f"  - DNS {ip}: {rtt if rtt < 999999 else 'timeout'} ms")
            if rtt < best_rtt:
                best_rtt = rtt
                best_ip = ip

        if best_rtt < 999999:
            self.upstream_ip = best_ip
            self.upstream_rtt = best_rtt
            self.stats.upstream_ip = best_ip
            self.stats.upstream_rtt = best_rtt
            print(f"[DNS] Best upstream selected: {best_ip} ({best_rtt} ms)")
        else:
            self.upstream_ip = "1.1.1.1"
            self.upstream_rtt = 0
            self.stats.upstream_ip = "1.1.1.1"
            self.stats.upstream_rtt = 0
            print("[DNS] No responsive upstream, fallback to 1.1.1.1")
        gc.collect()

    def tick(self, wifi_manager=None):
        """Định kỳ và tự động tối ưu hóa dựa trên tải và độ trễ."""
        if wifi_manager:
            self.wifi = wifi_manager
        else:
            wifi_manager = self.wifi

        now = time.ticks_ms()
        
        # 1. Kiểm tra định kỳ (fallback 6 giờ)
        if time.ticks_diff(now, self.last_opt_ticks) > 21600000:
            self.last_opt_ticks = now
            try:
                self.optimize_upstream(wifi_manager)
            except Exception as e:
                print("Periodic optimize error:", e)
            return

        # 2. Phát hiện trạng thái rảnh (Idle): Không có truy vấn trong 15 phút
        # và đã hơn 1 giờ chưa tối ưu hóa lại.
        idle_time = time.ticks_diff(now, self.last_query_ticks)
        time_since_opt = time.ticks_diff(now, self.last_opt_ticks)
        if idle_time > 900000 and time_since_opt > 3600000:
            self.last_opt_ticks = now
            try:
                print("[DNS] Idle detected, running silent optimize...")
                self.optimize_upstream(wifi_manager)
            except:
                pass

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
        self.last_query_ticks = time.ticks_ms()
        domain = self._parse_domain(request)
        blocked = False
        layer = None
        if domain:
            is_blocked, layer = self._check(domain)
            if is_blocked:
                self.stats.add(domain, True, layer, client_ip=addr[0])
                print(f"[DNS] {addr[0]} -> {domain} (BLOCK: {layer})")
                resp = self._block_response(request)
                if resp:
                    self.sock.sendto(resp, addr)
                blocked = True
            else:
                self.stats.add(domain, False, client_ip=addr[0])
                print(f"[DNS] {addr[0]} -> {domain} (PASS)")
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
        try:
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
        except:
            return b""

    def _proxy(self, request, addr):
        """Chuyển tiếp DNS request lên upstream và gửi response về client."""
        t0 = time.ticks_ms()
        self.last_query_ticks = t0
        try:
            self.upstream.sendto(request, (self.upstream_ip, self.PORT))
            response, _ = self.upstream.recvfrom(1024)
            self.sock.sendto(response, addr)
            
            # Đo RTT truy vấn thực tế
            rtt = time.ticks_diff(time.ticks_ms(), t0)
            self.upstream_rtt = rtt
            self.stats.upstream_rtt = rtt
            
            # Tính trung bình trượt RTT để phát hiện DNS bị chậm
            if self.rtt_cnt < 5:
                self.rtt_sum += rtt
                self.rtt_cnt += 1
            else:
                self.rtt_sum = int(self.rtt_sum * 0.8 + rtt * 0.2)
                # Nếu RTT trung bình cao (> 150ms) và chưa tối ưu hóa trong 5 phút
                if self.rtt_sum > 150 and time.ticks_diff(time.ticks_ms(), self.last_opt_ticks) > 300000:
                    print(f"[DNS] High latency detected ({self.rtt_sum} ms), re-optimizing...")
                    self.rtt_cnt = 0
                    self.rtt_sum = 0
                    try:
                        self.optimize_upstream()
                    except:
                        pass
        except Exception as e:
            print(f"[DNS] Upstream {self.upstream_ip} error: {e}")
            try:
                self.upstream.close()
            except:
                pass
            self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.upstream.settimeout(2.0)
            if time.ticks_diff(time.ticks_ms(), self.last_opt_ticks) > 30000:
                try:
                    self.optimize_upstream()
                except:
                    pass
