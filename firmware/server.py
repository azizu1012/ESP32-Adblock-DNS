"""HTTP web server: dashboard, stats API, config, upload.

Routes:
  GET  /             -- Dashboard (streams web/index.html from flash)
  GET  /setup        -- Setup page (streams web/setup.html from flash)
  GET  /api/stats    -- JSON stats endpoint
  POST /api/upload   -- Upload blocked.bin (stream to flash)
  POST /api/config/wifi  -- Save WiFi config & reboot
  POST /api/config/reset -- Delete config & reboot
  POST /api/config/dhcp  -- Switch to DHCP & reboot
  POST /api/reboot       -- Reboot device

HTML/CSS is stored in web/ folder on flash.
server.py contains only routing + API logic.
"""
import socket
import json
import time
import os
from stats import Stats


class WebServer:
    def __init__(self, stats, dns=None, ip="0.0.0.0", port=80):
        """Khoi tao web server voi stats, dns va dia chi IP."""
        self.stats = stats
        self.dns = dns
        self.ip = ip
        self.port = port
        self.sock = None

    def start(self):
        """Mo socket TCP, bind, listen voi backlog 8 va timeout 1s."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        # Tang backlog len 8 de hang doi TCP giu vung cac yeu cau ket noi song song thay vi lam rot (Connection Refused)
        self.sock.listen(8)
        self.sock.settimeout(1.0)
        print(f"Web server on port {self.port}")

    def serve(self, wifi_manager=None):
        """Vong lap chinh: chap nhan ket noi, xu ly request, dong."""
        import gc
        import utime
        self.start()
        while True:
            try:
                try:
                    conn, addr = self.sock.accept()
                except OSError:
                    # Tranh tight loop ngua CPU 100% khi xay ra loi tai nguyen TCP, cho phep LwIP xoa trang thai TIME_WAIT
                    utime.sleep_ms(20)
                    continue

                # 1. Khóa mỏm Web Server (Memory Fence) - Đã tinh chỉnh
                # Nếu RAM < 15KB, thử dọn rác trước. Nếu vẫn < 10KB thì mới chặn.
                # Điều này giúp tránh chặn oan khi RAM chỉ đang chứa rác chưa dọn.
                if gc.mem_free() < 15360:
                    gc.collect()
                    if gc.mem_free() < 10240:
                        print("[WEB] Warning: Free RAM < 10KB. Dropping connection to protect DNS!")
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue

                try:
                    # Thiet lap timeout doc Header cuc ngan (200ms) de tránh treo luong khi socket bi client ngat/cham
                    conn.settimeout(0.2)
                    self._handle(conn, wifi_manager)
                except Exception as e:
                    print("HTTP serve error:", e)
                finally:
                    # Offload TIME_WAIT to client: wait for client to send FIN first
                    # Voi ESP32 LwIP, SO_LINGER ko duoc ho tro. Ta phai cho client dong socket truoc (nhan duoc FIN).
                    # Dat timeout 2.0s (thay vi 0.1s) de chac chan cho duoc goi FIN hoac RST tu trinh duyet khi F5 lien tuc.
                    # Nho vay ESP32 se ko bao gio chu dong goi close() truoc -> ko bi dinh TIME_WAIT 2 phut!
                    try:
                        conn.settimeout(2.0)
                        conn.recv(1)
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
                    # Don dep RAM quyet liet ngay sau khi dong socket de ngan phan manh Heap
                    gc.collect()
            except Exception as e:
                # Bat tat ca cac loi critical (ke ca MemoryError) de ngan luong Web Server bi chet
                print("Web server critical thread error:", e)
                gc.collect()
                utime.sleep_ms(100)

    def _handle(self, conn, wifi_manager):
        """Parse HTTP request header va dieu huong den handler phu hop."""
        import time
        now = time.time()
        if not hasattr(self, "_rate_limit"):
            self._rate_limit = (now, 0)
        
        rl_time, rl_count = self._rate_limit
        if now - rl_time > 1.0:
            self._rate_limit = (now, 1)
        else:
            if rl_count > 15:
                # Anti-DDoS: Drop instantly if >15 reqs/sec
                try:
                    conn.sendall(b"HTTP/1.1 429 Too Many Requests\r\nConnection: close\r\n\r\n")
                except Exception:
                    pass
                return
            self._rate_limit = (rl_time, rl_count + 1)
            
        try:
            buf = conn.recv(1024)
            if not buf:
                return
            
            # 2. Giới hạn họng ăn (Payload Cap): Chống spam header làm tràn RAM
            total_read = len(buf)
            while b"\r\n\r\n" not in buf:
                if total_read > 2048:
                    print("[WEB] Blocked: HTTP Header > 2KB (OOM Prevention)")
                    return
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf += chunk
                total_read += len(chunk)

            idx = buf.find(b"\r\n\r\n")
            header_part = buf[:idx].decode("utf-8")
            parts = header_part.split(" ", 2)
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) > 1 else "/"

            # Parse If-None-Match va Accept-Encoding headers
            if_none_match = None
            accept_gzip = False
            lines = header_part.split("\r\n")
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    kl = k.strip().lower()
                    if kl == "if-none-match":
                        if_none_match = v.strip()
                    elif kl == "accept-encoding" and "gzip" in v.lower():
                        accept_gzip = True

            if path == "/api/upload":
                conn.settimeout(120.0)
                self._handle_upload(conn, buf)
            elif method == "POST":
                self._handle_post(conn, buf, path, wifi_manager)
            elif path == "/api/stats":
                self._serve_api_cached(conn, path, lambda: self._build_stats(wifi_manager))
            elif path == "/api/ui":
                # Stage 2: Stream full UI bundle (chi khi client chua co hoac version cu)
                self._stream_file(conn, "web/app.html", if_none_match, accept_gzip)
            elif path == "/api/safelist":
                res = list(self.dns.custom_safelist) if (self.dns and hasattr(self.dns, "custom_safelist")) else []
                self._send_json(conn, res)
            elif path == "/favicon.ico":
                conn.sendall(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
            elif path.startswith("/api/"):
                self._send_json(conn, {"error": "not found"})
            elif path == "/setup":
                self._stream_file(conn, "web/setup.html", if_none_match, accept_gzip)
            else:
                # Stage 1: Bootstrap loader (~1KB)
                self._stream_file(conn, "web/index.html", if_none_match, accept_gzip)
        except Exception as e:
            print("Handle error:", e)




# Attach extensions to WebServer
try:
    import server_api
    server_api.attach(WebServer)
except ImportError as e:
    print("Warning: server_api module not found", e)

try:
    import server_static
    server_static.attach(WebServer)
except ImportError as e:
    print("Warning: server_static module not found", e)
