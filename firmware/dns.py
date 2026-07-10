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

# Tối ưu hóa hiệu năng: Cache các hàm gọi thường xuyên (Global to Local)
# Việc lookup biến ở cấp độ module sẽ nhanh hơn so với phải lookup qua 2 cấp độ (module.function)
_ticks_ms = time.ticks_ms
_ticks_diff = time.ticks_diff
_time_sec = time.time
_struct_unpack = struct.unpack
_struct_pack = struct.pack

# Fallback for standard Python desktop testing
if not hasattr(time, "ticks_ms"):
    def ticks_ms():
        return int(_time_sec() * 1000)
    def ticks_diff(t1, t2):
        return t1 - t2
    _ticks_ms = ticks_ms
    _ticks_diff = ticks_diff


class DNSServer:
    UPSTREAM = "1.1.1.1"
    PORT = 53
    BLOCKED_BIN = "blocked.bin"
    SAFELIST = (
        "adwords.google.com", "adidas.com",
        "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com",
        # YouTube history & Google core
        "s.youtube.com", "video-stats.l.google.com", "clients4.google.com", "clients1.google.com",
        "android.clients.google.com", "connectivitycheck.gstatic.com",
        # Windows / MS
        "msftconnecttest.com", "msftncsi.com",
        # Apple
        "captive.apple.com", "gsp1.apple.com",
        # Spotify
        "spclient.wg.spotify.com", "apresolve.spotify.com",
    )
    SAFELIST_SUFFIX = frozenset((
        # TikTok / ByteDance
        "tiktok.com", "tiktokv.com", "tiktokcdn.com", "byteoversea.com", "ibytedtos.com", "ibyteimg.com",
        # Shopee & ShopeeFood
        "shopee.vn", "shopee.com", "shopeemobile.com", "shopeesz.com", "susercontent.com", "shopeefood.vn", "foody.vn", "now.vn",
        # Lazada, Sendo, AliExpress
        "lazada.vn", "lazcdn.com", "alicdn.com", "lazada.com", "sendo.vn", "senimg.com",
        # Tiki
        "tiki.vn", "tikicdn.com", "tiki.com.vn",
        # Zalo & VN E-wallets / Banks
        "zalo.me", "zadn.vn", "zaloapp.com", "zalo.vn", "momo.vn", "mservice.io", "mservice.com.vn", "zalopay.vn", "vnpay.vn",
        # Meta (Facebook/Instagram/Messenger/WhatsApp)
        "fbcdn.net", "cdninstagram.com", "facebook.com", "instagram.com", "messenger.com", "whatsapp.com", "whatsapp.net",
        # Google Services & YouTube CDNs (mở rộng ảnh & video)
        "googlevideo.com", "ytimg.com", "ggpht.com", "googleapis.com", "gstatic.com",
        # Apple & App Store CDNs
        "apple.com", "icloud.com", "cdn-apple.com", "mzstatic.com",
        # Grab, Gojek, Be
        "grab.com", "grabtaxi.com", "gojek.com", "go-jek.com", "be.com.vn",
        # Netflix, Spotify, VN Streaming (FPT Play, VieON, ZingMP3, NCT)
        "netflix.com", "nflximg.net", "nflxvideo.net", "nflxso.net", "nflxext.com", "spotify.com", "scdn.co", "fptplay.vn", "fptplay.net", "vieon.vn", "zingmp3.vn", "zmdcdn.me", "nhaccuatui.com", "nixcdn.com",
        # X (Twitter), Reddit, Discord, Pinterest
        "twimg.com", "twitter.com", "x.com", "reddit.com", "redditmedia.com", "redditstatic.com", "discord.com", "discordapp.com", "discordapp.net", "pinimg.com",
        # Telegram & Viber
        "telegram.org", "viber.com",
        # Captcha Services (Chống liệt web khi đăng nhập)
        "recaptcha.net", "hcaptcha.com",
        # Roblox
        "roblox.com", "rbxcdn.com",
        # Báo chí VN CDNs (VnExpress)
        "vnecdn.net",
        # Mihoyo / Hoyoverse
        "mihoyo.com", "hoyoverse.com", "starrails.com", "zenlesszonezero.com", "cognosphere.com", "yuanshen.com",
        # KuroGames
        "kurogames.com", "kurogame.com",
        # Arknights (Hypergryph / Yostar)
        "hypergryph.com", "yostar.com", "hg-cdn.com", "arknights.global",
        # Steam / Valve
        "steampowered.com", "steamcommunity.com", "steamgames.com", "valvesoftware.com",
        # Riot Games (LOL / Valorant)
        "riotgames.com", "valorant.com",
        # Epic Games
        "epicgames.com", "unrealengine.com",
        # EA / Ubisoft
        "ea.com", "ubi.com", "ubisoft.com",
        # Google Mail Images & Play Store
        "googleusercontent.com", "gvt1.com", "gvt2.com",
        # Office365 / Windows updates (safe suffixes)
        "update.microsoft.com", "windowsupdate.com",
        # Apple iCloud / Updates
        "apple-dns.net"
    ))
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
        self.timeout_errors = 0
        self.wifi = None
        self.stats.upstream_ip = "1.1.1.1"
        self.stats.upstream_rtt = 0

        # Bloom Filter Buffer
        self._bloom_buf = bytearray(64)  # Đọc khối 64 bytes từ flash
        self._bloom_file = None  # File handle mở vĩnh viễn (lazy init)
        
        # Cau truc du lieu cho forwarder khong block (Async DNS proxy)
        self.pending_queries = {}
        self.tx_counter = 0
        self._is_optimizing = False
        self.sock_errors = 0  # Theo doi loi cong 53 de tu phuc hoi

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
        except Exception:
            pass

        try:
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        except Exception:
            pass

        # Bắt đầu luồng kiểm chứng ngầm (GCT Worker)
        _thread.start_new_thread(self._verify_worker, ())





    def tick(self, wifi_manager=None):
        """Định kỳ và tự động tối ưu hóa dựa trên tải và độ trễ."""
        if wifi_manager:
            self.wifi = wifi_manager
        else:
            wifi_manager = self.wifi

        now = time.ticks_ms()
        
        # 1. Kiểm tra định kỳ (2 giờ)
        if time.ticks_diff(now, self.last_opt_ticks) > 7200000:
            self.last_opt_ticks = now
            try:
                self.optimize_upstream(wifi_manager)
            except Exception as e:
                print("Periodic optimize error:", e)

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
        # 1. Dọn dẹp các truy vấn quá hạn (timeout) để không rò rỉ RAM
        self._cleanup_pending_queries()
        
        try:
            # 2. Lấy dữ liệu từ cả 2 nguồn: Client (gửi câu hỏi) và Upstream (trả câu trả lời)
            # Timeout 0.05s để giải phóng vòng lặp chính
            readable, _, _ = select.select([self.sock, self.upstream], [], [], 0.05)
            self.sock_errors = 0  # Reset bo dem neu socket khoe manh
        except OSError:
            self.sock_errors += 1
            if self.sock_errors >= 5:
                print("[DNS] Critical port 53 failure! Auto-recovering socket...")
                try:
                    self.sock.close()
                except Exception:
                    pass
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.sock.setblocking(False)
                    self.sock.bind(("0.0.0.0", self.PORT))
                    self.sock_errors = 0
                    print("[DNS] Port 53 successfully recreated!")
                except Exception as e:
                    print("[DNS] Failed to recover port 53:", e)
            return False

        # 3. Nếu không có dữ liệu, thực hiện dọn dẹp rác định kỳ (GC)
        if not readable:
            self._gc_tick()
            return False

        blocked_any = False
        # 4. Duyệt qua các kết nối đang có dữ liệu
        for s in readable:
            if s is self.sock:
                # ==========================================
                # A. NHẬN TRUY VẤN TỪ CLIENT (LAPTOP, ĐIỆN THOẠI)
                # ==========================================
                try:
                    request, addr = self.sock.recvfrom(512)
                except OSError:
                    continue
                
                # Gói tin DNS tối thiểu phải 12 bytes
                if len(request) < 12:
                    continue
                
                # Cache lại thời gian
                self.last_query_ticks = _ticks_ms()
                
                # Bóc tách tên miền từ gói tin
                domain = self._parse_domain(request)
                if domain:
                    # Kiểm tra tên miền qua 5 lớp chặn
                    is_blocked, layer = self._check(domain)
                    if is_blocked:
                        # Ghi nhận vào thống kê và chặn (trả về 0.0.0.0)
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
                        # Ghi nhận cho phép và chuyển tiếp lên Upstream (Google/Cloudflare)
                        self.stats.add(domain, False, client_ip=addr[0])
                        print(f"[DNS] {addr[0]} -> {domain} (PASS)")
                        self._async_proxy_send(request, addr, domain)
                else:
                    # Nếu không bóc tách được (bị lỗi định dạng), cứ chuyển tiếp cho an toàn
                    self._async_proxy_send(request, addr, None)
            elif s is self.upstream:
                # ==========================================
                # B. NHẬN KẾT QUẢ TỪ UPSTREAM SERVER
                # ==========================================
                try:
                    response, _ = self.upstream.recvfrom(1024)
                except OSError:
                    continue
                    
                if len(response) >= 12:
                    # Xử lý ID khớp và gửi trả kết quả ngược về cho Client
                    self._async_proxy_recv(response)
        
        # 5. Gom rác sau mỗi nhịp xử lý
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
        except Exception:
            return None

    def _check(self, domain):
        """Kiểm tra domain qua các lớp chặn, bao gồm cả GCT dynamic safelist."""
        # Bỏ qua truy vấn mạng nội bộ và reverse DNS (.local, .arpa)
        if domain.endswith(".local") or domain.endswith(".arpa"):
            return False, None

        # Lớp 1: Safelist tĩnh (hệ thống + custom)
        if domain in self.SAFELIST or domain in self.custom_safelist:
            return False, None
            
        # Bỏ qua theo đuôi tĩnh (Game, Dịch vụ đặc thù) - O(1) set lookup thay vì O(n) linear scan
        if domain in self.SAFELIST_SUFFIX:
            return False, None
        dot = domain.find(".")
        while dot != -1:
            if domain[dot + 1:] in self.SAFELIST_SUFFIX:
                return False, None
            dot = domain.find(".", dot + 1)

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
                except Exception:
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
        except Exception:
            return b""

    def _async_proxy_send(self, request, client_addr, domain=None):
        """Gui DNS request len upstream bang cach map TX ID ma khong he gay block."""
        # 1. Giám sát các tên miền trong danh sách Tạm Tha (GCT Safelist)
        if domain and domain in self.safelist_dyn:
            now_sec = _time_sec()
            count, start_t = self.query_counts.get(domain, (0, now_sec))
            
            # Nếu đã qua 60 giây, reset bộ đếm
            if now_sec - start_t > 60:
                count = 1
                start_t = now_sec
            else:
                count += 1
            self.query_counts[domain] = (count, start_t)
            
            # 2. Luật Chống Lạm Dụng: Đâm quá 30 req/min sẽ bị đá lại vào Blocklist
            if count > 30:
                print(f"[GCT] Demoted {domain} due to high activity: {count} req/min")
                with self.lock:
                    if domain in self.safelist_dyn:
                        del self.safelist_dyn[domain]
                self.query_counts[domain] = (0, now_sec)

        # 3. Giới hạn trần cuốn sổ tay (Memory Fence)
        if len(self.pending_queries) >= 50:
            print("[DNS] Dropped query: Pending queue full (>50) - Protecting RAM")
            return

        # 3. Lấy Transaction ID gốc của thiết bị (Laptop/Phone) để lưu vết
        client_tx_id = _struct_unpack(">H", request[0:2])[0]
        
        # 4. Sinh Transaction ID duy nhất của riêng ESP32 để gửi lên Upstream
        with self.lock:
            self.tx_counter = (self.tx_counter + 1) & 0xFFFF
            upstream_tx_id = self.tx_counter
            
        # 5. Lưu lại mapping để khi có kết quả trả về, ESP32 biết đường trả về cho ai
        self.pending_queries[upstream_tx_id] = (client_addr, client_tx_id, _ticks_ms(), time.ticks_us())
        
        # 6. Chế tạo lại gói tin DNS với TX ID mới
        modified_request = _struct_pack(">H", upstream_tx_id) + request[2:]

        
        try:
            self.upstream.sendto(modified_request, (self.upstream_ip, self.PORT))
        except OSError as e:
            print(f"[DNS] Upstream send error: {e}")
            try:
                self.upstream.close()
            except Exception:
                pass
            self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.upstream.setblocking(False)

    def _async_proxy_recv(self, response):
        """Nhan phan hoi tu upstream, restore TX ID va forward ve dung client."""
        # 1. Bóc TX ID từ gói tin Upstream trả về
        upstream_tx_id = _struct_unpack(">H", response[0:2])[0]
        
        # 2. Tìm kiếm trong từ điển pending_queries
        query_info = self.pending_queries.pop(upstream_tx_id, None)
        if query_info:
            client_addr, client_tx_id, start_ticks, start_us = query_info
            
            # 3. Phục hồi lại TX ID gốc của thiết bị và gửi trả
            client_response = _struct_pack(">H", client_tx_id) + response[2:]
            try:
                self.sock.sendto(client_response, client_addr)
            except OSError:
                pass
                
            # 4. Đo lường RTT (Độ trễ thời gian thực)
            dt_us = time.ticks_diff(time.ticks_us(), start_us)
            rtt = round(dt_us / 1000.0, 1)
            self.upstream_rtt = rtt
            self.stats.upstream_rtt = rtt
            
            # 5. Tính trung bình trượt EMA (Exponential Moving Average) để làm mịn nhiễu mạng
            if self.rtt_sum == 0:
                self.rtt_sum = rtt
            else:
                self.rtt_sum = (self.rtt_sum * 0.8) + (rtt * 0.2)
                self.timeout_errors = 0  # Bất cứ khi nào nhận được phản hồi, reset bộ đếm rớt mạng
                
                # 6. Reactive Congestion Control: Nếu RTT > 85ms, ép tìm DNS khác nhanh hơn
                if self.rtt_sum > 85 and _ticks_diff(_ticks_ms(), self.last_opt_ticks) > 120000:
                    print(f"[DNS] High latency detected ({self.rtt_sum} ms), re-optimizing...")
                    self.rtt_cnt = 0
                    self.rtt_sum = 0
                    try:
                        self.optimize_upstream()
                    except Exception:
                        pass

    def _cleanup_pending_queries(self):
        """Don dep cac truy van cho qua lau (> 2s) de tranh ro ri RAM."""
        now = _ticks_ms()
        last_clean = getattr(self, "_last_clean_ticks", 0)
        
        # Chỉ chạy dọn dẹp mỗi 5 giây 1 lần để tiết kiệm CPU
        if _ticks_diff(now, last_clean) < 5000:
            return
        self._last_clean_ticks = now
        
        todel = []
        # Tìm các truy vấn kẹt quá 2 giây
        for tx_id, info in self.pending_queries.items():
            start_ticks = info[2]
            if _ticks_diff(now, start_ticks) > 2000:
                todel.append(tx_id)
                
        # Xóa các truy vấn kẹt và tăng biến đếm rớt mạng
        for tx_id in todel:
            self.pending_queries.pop(tx_id, None)
            self.timeout_errors += 1
            
        # 7. Cơ chế Fail-Fast: Nếu rớt 5 truy vấn liên tiếp (chết lâm sàng), đổi server khẩn cấp!
        if self.timeout_errors >= 5 and _ticks_diff(now, self.last_opt_ticks) > 30000:
            print(f"[DNS] Upstream totally dead ({self.timeout_errors} timeouts), Fail-Fast re-optimizing...")
            self.timeout_errors = 0
            try:
                self.optimize_upstream()
            except Exception:
                pass

# Load external modules and attach them to DNSServer
try:
    import dns_bloom
    dns_bloom.attach(DNSServer)
except ImportError as e:
    print("Warning: dns_bloom module not found", e)

try:
    import dns_gct
    dns_gct.attach(DNSServer)
except ImportError as e:
    print("Warning: dns_gct module not found", e)

try:
    import dns_upstream
    dns_upstream.attach(DNSServer)
except ImportError as e:
    print("Warning: dns_upstream module not found", e)
