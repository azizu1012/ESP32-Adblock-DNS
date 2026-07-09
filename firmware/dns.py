"""DNS proxy với adblock filtering.

Blocking layers (theo thứ tự):
1. SAFELIST — bỏ qua domain trong whitelist tĩnh
2. Dynamic Safelist (GCT) — bỏ qua domain đã được đối chứng và tự động phục hồi
3. Heuristic — pattern "ad.*"
4. Keyword — telemetry/analytics/doubleclick...
5. Blocked Bloom Filter — 1.2MB bitmap trên blocked.bin
"""
import socket
import struct
import select
import gc
import time
import _thread

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
        """Khởi tạo DNS server, bộ đệm Bloom Filter và luồng phục hồi GCT."""
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

        # Bloom Filter Buffer
        self._bloom_buf = bytearray(64)  # Đọc khối 64 bytes từ flash
        
        # Cau truc du lieu cho forwarder khong block (Async DNS proxy)
        self.pending_queries = {}
        self.tx_counter = 0

        # Graduated Consensus Trust (GCT) structures
        self.lock = _thread.allocate_lock()
        self.verify_queue = []  # Hàng đợi tên miền chờ kiểm chứng
        self.safelist_dyn = {}  # domain -> (expiry, level, last_query)
        self.query_counts = {}  # domain -> (count, window_start_time)
        self.custom_safelist = set()
        try:
            with open("safelist.txt") as f:
                for line in f:
                    d = line.strip().lower()
                    if d:
                        self.custom_safelist.add(d)
        except:
            pass

        try:
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        except:
            pass

        # Bắt đầu luồng kiểm chứng ngầm (GCT Worker)
        _thread.start_new_thread(self._verify_worker, ())

    def _measure_rtt(self, ip, timeout_ms=300):
        """Đo độ trễ RTT tới một IP bằng cách gửi DNS query cho google.com."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_ms / 1000.0)
        try:
            t0 = time.ticks_us()
            q = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01'
            sock.sendto(q, (ip, 53))
            resp, _ = sock.recvfrom(512)
            if resp and resp[:2] == b'\xaa\xbb':
                dt_us = time.ticks_diff(time.ticks_us(), t0)
                return round(dt_us / 1000.0, 1)
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
        
        # 1. Kiểm tra định kỳ (6 giờ)
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
        """Mở socket DNS (UDP) và socket upstream dưới dạng non-blocking."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(False)
        self.sock.bind(("0.0.0.0", self.PORT))
        
        # Socket gui len DNS upstream duoc dat o che do non-blocking de khong treo main thread
        self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream.setblocking(False)
        
        print(f"DNS server on port {self.PORT}")
        return self.sock

    def poll(self):
        """Poll hoat dong DNS khong block: chap nhan ca truy van tu client va phan hoi tu upstream."""
        self._cleanup_pending_queries()
        
        try:
            # Giam sat dong thoi ca client socket va upstream socket de forward bat dong bo
            readable, _, _ = select.select([self.sock, self.upstream], [], [], 0.05)
        except OSError:
            return False

        if not readable:
            self._gc_tick()
            return False

        blocked_any = False
        for s in readable:
            if s is self.sock:
                try:
                    request, addr = self.sock.recvfrom(512)
                except OSError:
                    continue
                if len(request) < 12:
                    continue
                self.last_query_ticks = time.ticks_ms()
                domain = self._parse_domain(request)
                if domain:
                    is_blocked, layer = self._check(domain)
                    if is_blocked:
                        self.stats.add(domain, True, layer, client_ip=addr[0])
                        print(f"[DNS] {addr[0]} -> {domain} (BLOCK: {layer})")
                        resp = self._block_response(request)
                        if resp:
                            try:
                                self.sock.sendto(resp, addr)
                            except OSError:
                                pass
                        blocked_any = True
                    else:
                        self.stats.add(domain, False, client_ip=addr[0])
                        print(f"[DNS] {addr[0]} -> {domain} (PASS)")
                        self._async_proxy_send(request, addr, domain)
                else:
                    self._async_proxy_send(request, addr, None)
            elif s is self.upstream:
                try:
                    response, _ = self.upstream.recvfrom(1024)
                except OSError:
                    continue
                if len(response) >= 12:
                    self._async_proxy_recv(response)
        
        self._gc_tick()
        return blocked_any

    def _gc_tick(self):
        """Thu gom rác mỗi 100 poll để tránh STW đột ngột."""
        self._gc_cnt = (self._gc_cnt + 1) % 100
        if self._gc_cnt == 0:
            gc.collect()

    def _parse_domain(self, data):
        """Giải nén domain name từ DNS request."""
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
        """Kiểm tra domain qua các lớp chặn, bao gồm cả GCT dynamic safelist."""
        # Bỏ qua truy vấn mạng nội bộ và reverse DNS (.local, .arpa)
        if domain.endswith(".local") or domain.endswith(".arpa"):
            return False, None

        # Lớp 1: Safelist tĩnh (hệ thống + custom)
        if domain in self.SAFELIST or domain in self.custom_safelist:
            return False, None

        # Lớp 2: Dynamic Safelist (GCT tự phục hồi)
        with self.lock:
            if domain in self.safelist_dyn:
                expiry, level, _ = self.safelist_dyn[domain]
                if time.time() < expiry:
                    # Update last query time
                    self.safelist_dyn[domain] = (expiry, level, time.time())
                    return False, None

        # Lớp 3: Heuristics
        parts = domain.split(".")
        if not parts:
            return False, None
        first = parts[0]
        if first.startswith("ad"):
            suffix = first[2:]
            if not suffix or suffix == "s" or suffix.isdigit() or (suffix.startswith("s") and suffix[1:].isdigit()):
                return True, "heuristic"

        # Lớp 4: Keywords
        for part in parts:
            if part in self.KEYWORDS:
                return True, "keyword"

        # Lớp 5: Blocked Bloom Filter
        if self._bloom_search(domain):
            # Nếu bị Bloom Filter chặn, xếp hàng đợi kiểm chứng ngầm GCT
            self._enqueue_verification(domain)
            return True, "hash"

        return False, None

    def add_custom_safelist(self, domain):
        """Thêm domain vào custom safelist (RAM + Flash). Trả về True nếu thành công."""
        domain = domain.strip().lower()
        if not domain:
            return False
        with self.lock:
            if domain in self.custom_safelist:
                return True
            self.custom_safelist.add(domain)
            # Dọn dẹp khỏi hàng thử thách GCT nếu có
            if domain in self.safelist_dyn:
                try:
                    del self.safelist_dyn[domain]
                except:
                    pass
            # Ghi cấu hình xuống file
            try:
                with open("safelist.txt", "a") as f:
                    f.write(domain + "\n")
            except Exception as e:
                print("Write safelist.txt error:", e)
                return False
        return True

    def remove_custom_safelist(self, domain):
        """Xóa domain khỏi custom safelist (RAM + Flash). Trả về True nếu thành công."""
        domain = domain.strip().lower()
        if not domain:
            return False
        with self.lock:
            if domain not in self.custom_safelist:
                return True
            self.custom_safelist.discard(domain)
            # Rewrite file
            try:
                with open("safelist.txt", "w") as f:
                    for d in self.custom_safelist:
                        f.write(d + "\n")
            except Exception as e:
                print("Rewrite safelist.txt error:", e)
                return False
        return True

    def get_safelist_dyn(self):
        """Trả về danh sách các domain đang ở trạng thái tạm tha GCT."""
        res = []
        now = time.time()
        with self.lock:
            for domain, val in self.safelist_dyn.items():
                expiry, level, last_q = val
                ttl = int(expiry - now)
                if ttl > 0:
                    res.append({
                        "d": domain,
                        "t": ttl,
                        "l": level
                    })
        res.sort(key=lambda x: x["t"], reverse=True)
        return res

    @staticmethod
    def _fnv1a_64(data):
        """FNV-1a 64-bit hash."""
        h = 0xCBF29CE484222325
        p = 0x100000001B3
        for b in data:
            h = ((h ^ b) * p) & 0xFFFFFFFFFFFFFFFF
        return h

    def _bloom_search(self, domain):
        """Tìm domain trong Blocked Bloom Filter bằng 1 lần đọc Flash 64 bytes."""
        try:
            h = self._fnv1a_64(domain.encode("utf-8"))
            block_idx = (h >> 32) % 18750
            h_low = h & 0xFFFFFFFF
            
            with open(self.BLOCKED_BIN, "rb") as f:
                f.seek(block_idx * 64)
                f.readinto(self._bloom_buf)
                
            for i in range(8):
                bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512
                byte_pos = bit_pos // 8
                bit_mask = 1 << (bit_pos % 8)
                if not (self._bloom_buf[byte_pos] & bit_mask):
                    return False
            return True
        except:
            return False

    def _enqueue_verification(self, domain):
        """Thêm domain vào hàng đợi kiểm chứng ngầm GCT nếu chưa có."""
        with self.lock:
            # Nếu đang trong hàng đợi hoặc safelist động chưa hết hạn, bỏ qua
            if domain not in self.verify_queue:
                # Giới hạn hàng đợi tối đa 20 phần tử để tránh phình RAM
                if len(self.verify_queue) < 20:
                    self.verify_queue.append(domain)

    def _dns_query_raw(self, domain, server_ip, timeout=1.5):
        """Gửi gói tin DNS UDP thô để xác minh trạng thái domain ở luồng phụ."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            # Tạo gói tin DNS Query chuẩn cho bản ghi A
            header = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
            parts = domain.split('.')
            qname = b''
            for part in parts:
                qname += bytes([len(part)]) + part.encode()
            qname += b'\x00'
            footer = b'\x00\x01\x00\x01'
            query = header + qname + footer

            sock.sendto(query, (server_ip, 53))
            resp, _ = sock.recvfrom(512)
            if len(resp) > 12:
                # Đọc số lượng câu trả lời (Answer Count)
                ancount = struct.unpack(">H", resp[6:8])[0]
                if ancount > 0:
                    # Kiểm tra 4 byte cuối cùng (IP phân giải)
                    ip = resp[-4:]
                    if ip != b'\x00\x00\x00\x00' and ip != b'\x7f\x00\x00\x01':
                        return True  # Phân giải thành công sang IP thật
            return False
        except:
            return False
        finally:
            sock.close()

    def _verify_worker(self):
        """Luồng phụ liên tục kiểm chứng hàng đợi bằng cơ chế đồng thuận 3/3."""
        while True:
            if not self.verify_queue:
                time.sleep(2)
                continue

            domain = None
            with self.lock:
                if self.verify_queue:
                    domain = self.verify_queue.pop(0)

            if not domain:
                continue

            # Bước 1: Kiểm tra xem domain có chạy bình thường trên internet không
            g_ok = self._dns_query_raw(domain, "8.8.8.8")
            if not g_ok:
                continue  # Bỏ qua nếu domain chết hoặc mạng mất kết nối

            # Bước 2: Truy vấn chéo 3 cổng DNS chặn quảng cáo lớn
            adg_ok = self._dns_query_raw(domain, "94.140.14.14")
            ctd_ok = self._dns_query_raw(domain, "76.76.2.2")
            mul_ok = self._dns_query_raw(domain, "194.242.2.12")

            # Đồng thuận 3/3: Cả 3 máy chủ đều xác nhận tên miền sạch
            if adg_ok and ctd_ok and mul_ok:
                self._heal_domain(domain)
            else:
                # Nếu bất kỳ con DNS nào báo chặn, hạ cấp ngay khỏi safelist nếu đang tạm tha
                with self.lock:
                    if domain in self.safelist_dyn:
                        del self.safelist_dyn[domain]
                        print(f"[GCT] Re-blocked real ad: {domain}")

    def _heal_domain(self, domain):
        """Đưa domain vào diện tạm tha và thăng hạng cấp độ tin cậy."""
        with self.lock:
            level = 0
            ttl = 300  # 5 phút mặc định cho level 0
            if domain in self.safelist_dyn:
                _, old_level, _ = self.safelist_dyn[domain]
                if old_level == 0:
                    level = 1
                    ttl = 3600  # 1 giờ cho level 1
                elif old_level >= 1:
                    level = 2
                    ttl = 86400  # 24 giờ cho level 2
            
            self.safelist_dyn[domain] = (time.time() + ttl, level, time.time())
            print(f"[GCT] Self-healed {domain}: level={level}, ttl={ttl}s")

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

    def _async_proxy_send(self, request, client_addr, domain=None):
        """Gui DNS request len upstream bang cach map TX ID ma khong he gay block."""
        if domain and domain in self.safelist_dyn:
            now_sec = time.time()
            count, start_t = self.query_counts.get(domain, (0, now_sec))
            if now_sec - start_t > 60:
                count = 1
                start_t = now_sec
            else:
                count += 1
            self.query_counts[domain] = (count, start_t)
            if count > 30:
                print(f"[GCT] Demoted {domain} due to high activity: {count} req/min")
                with self.lock:
                    if domain in self.safelist_dyn:
                        del self.safelist_dyn[domain]
                self.query_counts[domain] = (0, now_sec)

        # Lay client TX ID de luu vet phuc hoi
        client_tx_id = struct.unpack(">H", request[0:2])[0]
        
        # Sinh Transaction ID duy nhat cho upstream
        with self.lock:
            self.tx_counter = (self.tx_counter + 1) & 0xFFFF
            upstream_tx_id = self.tx_counter
            
        self.pending_queries[upstream_tx_id] = (client_addr, client_tx_id, time.ticks_ms(), time.ticks_us())
        modified_request = struct.pack(">H", upstream_tx_id) + request[2:]
        
        try:
            self.upstream.sendto(modified_request, (self.upstream_ip, self.PORT))
        except OSError as e:
            print(f"[DNS] Upstream send error: {e}")
            try:
                self.upstream.close()
            except:
                pass
            self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.upstream.setblocking(False)

    def _async_proxy_recv(self, response):
        """Nhan phan hoi tu upstream, restore TX ID va forward ve dung client."""
        upstream_tx_id = struct.unpack(">H", response[0:2])[0]
        query_info = self.pending_queries.pop(upstream_tx_id, None)
        if query_info:
            client_addr, client_tx_id, start_ticks, start_us = query_info
            client_response = struct.pack(">H", client_tx_id) + response[2:]
            try:
                self.sock.sendto(client_response, client_addr)
            except OSError:
                pass
                
            # Do RTT
            dt_us = time.ticks_diff(time.ticks_us(), start_us)
            rtt = round(dt_us / 1000.0, 1)
            self.upstream_rtt = rtt
            self.stats.upstream_rtt = rtt
            
            # Tinh trung binh trượt RTT
            if self.rtt_cnt < 5:
                self.rtt_sum += rtt
                self.rtt_cnt += 1
            else:
                self.rtt_sum = int(self.rtt_sum * 0.8 + rtt * 0.2)
                if self.rtt_sum > 150 and time.ticks_diff(time.ticks_ms(), self.last_opt_ticks) > 300000:
                    print(f"[DNS] High latency detected ({self.rtt_sum} ms), re-optimizing...")
                    self.rtt_cnt = 0
                    self.rtt_sum = 0
                    try:
                        self.optimize_upstream()
                    except:
                        pass

    def _cleanup_pending_queries(self):
        """Don dep cac truy van cho qua lau (> 2s) de tranh ro ri RAM."""
        now = time.ticks_ms()
        last_clean = getattr(self, "_last_clean_ticks", 0)
        if time.ticks_diff(now, last_clean) < 5000:
            return
        self._last_clean_ticks = now
        
        todel = []
        for tx_id, info in self.pending_queries.items():
            start_ticks = info[2]
            if time.ticks_diff(now, start_ticks) > 2000:
                todel.append(tx_id)
        for tx_id in todel:
            self.pending_queries.pop(tx_id, None)
