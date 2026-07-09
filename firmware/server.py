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

                try:
                    # Thiet lap timeout doc Header cuc ngan (200ms) de tránh treo luong khi socket bi client ngat/cham
                    conn.settimeout(0.2)
                    self._handle(conn, wifi_manager)
                except Exception as e:
                    print("HTTP serve error:", e)
                finally:
                    try:
                        conn.close()
                    except:
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
                except:
                    pass
                return
            self._rate_limit = (rl_time, rl_count + 1)
            
        try:
            buf = conn.recv(1024)
            if not buf:
                return
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf += chunk

            idx = buf.find(b"\r\n\r\n")
            header_part = buf[:idx].decode("utf-8")
            path = header_part.split(" ")[1] if " " in header_part else "/"
            method = header_part.split(" ")[0] if " " in header_part else "GET"

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
            elif path == "/api/stats/recent":
                self._serve_api_cached(conn, path, lambda: self.stats.to_recent_list() if self.stats else [])
            elif path == "/api/stats/top":
                self._serve_api_cached(conn, path, lambda: self.stats.to_top_list() if self.stats else [])
            elif path == "/api/ui/version":
                # Stage 1: Tra ve version cua UI bundle (~30 bytes) de client kiem tra cache
                try:
                    st = os.stat("web/app.html")
                    v = f"{st[6]}-{st[8] if len(st) > 8 else 0}"
                except:
                    v = "0"
                self._send_json(conn, {"v": v})
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

    def _handle_post(self, conn, data, path, wifi_manager):
        """Xu ly POST request: config wifi, reboot, reset, dhcp."""
        request = data.decode("utf-8")
        if path == "/api/config/wifi":
            body = self._parse_body(request)
            ssid = body.get("ssid", "")
            password = body.get("password", "")
            if ssid:
                from config import ConfigManager
                cfg = ConfigManager.load()
                cfg["ssid"] = ssid
                cfg["password"] = password
                if body.get("noip_user"):
                    cfg["noip_user"] = body["noip_user"]
                if body.get("noip_pass"):
                    cfg["noip_pass"] = body["noip_pass"]
                if body.get("noip_host"):
                    cfg["noip_host"] = body["noip_host"]
                ConfigManager.save(cfg)
                self._send_json(conn, {"ok": True, "message": "Saved. Rebooting..."})
                import machine
                time.sleep(1)
                machine.reset()
                return
            self._send_json(conn, {"ok": False, "error": "ssid required"})
        elif path == "/api/reboot":
            self._send_json(conn, {"ok": True, "message": "Rebooting..."})
            import machine
            time.sleep(0.5)
            machine.reset()
        elif path == "/api/config/reset":
            from config import ConfigManager
            ConfigManager.delete()
            self._send_json(conn, {"ok": True, "message": "Reset. Rebooting..."})
            import machine
            time.sleep(1)
            machine.reset()
        elif path == "/api/config/dhcp":
            from config import ConfigManager
            cfg = ConfigManager.load()
            cfg["ip"] = ""
            cfg["gateway"] = ""
            ConfigManager.save(cfg)
            self._send_json(conn, {"ok": True, "message": "DHCP mode. Rebooting..."})
            import machine
            time.sleep(1)
            machine.reset()
        elif path == "/api/safelist/add":
            if not self.dns:
                self._send_json(conn, {"ok": False, "error": "dns server not initialized"})
                return
            body = self._parse_body(request)
            domain = body.get("domain", "")
            if domain:
                ok = self.dns.add_custom_safelist(domain)
                self._send_json(conn, {"ok": ok})
            else:
                self._send_json(conn, {"ok": False, "error": "domain is required"})
        elif path == "/api/safelist/remove":
            if not self.dns:
                self._send_json(conn, {"ok": False, "error": "dns server not initialized"})
                return
            body = self._parse_body(request)
            domain = body.get("domain", "")
            if domain:
                ok = self.dns.remove_custom_safelist(domain)
                self._send_json(conn, {"ok": ok})
            else:
                self._send_json(conn, {"ok": False, "error": "domain is required"})
        else:
            self._send_json(conn, {"ok": False, "error": "unknown endpoint"})

    def _handle_upload(self, conn, data):
        """Nhan file blocked.bin moi qua HTTP, ghi truc tiep vao flash (stream)."""
        try:
            header_end = data.find(b"\r\n\r\n")
            if header_end == -1:
                self._send_json(conn, {"ok": False, "error": "bad request"})
                return

            header_part = data[:header_end].decode("utf-8")
            cl = 0
            for line in header_part.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    cl = int(line.split(":")[1].strip())
                    break

            if cl < 1024:
                self._send_json(conn, {"ok": False, "error": "file too small"})
                return

            body_start = header_end + 4
            written = len(data) - body_start

            import machine, gc
            with open("blocked.bin", "wb") as f:
                f.write(data[body_start:])
                while written < cl:
                    remaining = cl - written
                    chunk = conn.recv(min(1024, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if written % 8192 == 0:
                        f.flush()
                        gc.collect()
                        machine.idle()

            self._send_json(conn, {"ok": True, "message": "Upload OK (%d bytes)" % cl})
        except Exception as e:
            self._send_json(conn, {"ok": False, "error": str(e)})

    @staticmethod
    def _parse_body(request):
        """Giai nen body JSON tu HTTP request."""
        parts = request.split("\r\n\r\n", 1)
        if len(parts) < 2:
            return {}
        try:
            return json.loads(parts[1])
        except:
            return {}

    def _build_stats(self, wifi_manager):
        """Xay dung dict stats JSON, them cpu_temp va IP."""
        if self.stats is None:
            d = {"total": 0, "blocked": 0, "allowed": 0, "ratio": 0,
                 "uptime": 0, "free_ram": 0, "alloc_ram": 0, "total_ram": 0,
                 "last_blocked": "", "recent": [], "cpu_temp": None, "ip": "",
                 "top": [], "flash_free": 0, "flash_total": 0, "flash_chip": 0,
                 "blocklist_entries": 0, "cpu_freq": 0, "core_count": 0,
                 "upstream": "1.1.1.1", "upstream_rtt": 0}
            if wifi_manager and wifi_manager.is_connected():
                try:
                    d["ip"] = wifi_manager.ifconfig()[0]
                except:
                    pass
            return d
        d = self.stats.to_dict()
        d["cpu_temp"] = self._get_cpu_temp()
        d["ip"] = ""
        if wifi_manager and wifi_manager.is_connected():
            try:
                d["ip"] = wifi_manager.ifconfig()[0]
            except:
                pass

        # Calculate active clients in last 10 minutes (600s)
        active_clients = 1
        try:
            self.stats.lock.acquire()
            now = time.time()
            cutoff = now - 600
            count = 0
            to_delete = []
            for ip, t in self.stats.client_ips.items():
                if t > cutoff:
                    count += 1
                else:
                    to_delete.append(ip)
            for ip in to_delete:
                del self.stats.client_ips[ip]
            if count > 0:
                active_clients = count
        except:
            pass
        finally:
            try:
                self.stats.lock.release()
            except:
                pass
        d["active_clients"] = active_clients

        # Expose dynamic safelist (GCT)
        d["safelist_dyn"] = []
        if self.dns:
            try:
                d["safelist_dyn"] = self.dns.get_safelist_dyn()
            except:
                pass

        return d

    @staticmethod
    def _get_cpu_temp():
        """Doc nhiet do CPU tu cam bien trong ESP32, tra ve C."""
        try:
            import esp32
            raw = esp32.raw_temperature()
            if raw < 50 or raw > 200:
                return None
            return round((raw - 32) / 1.8, 1)
        except:
            return None

    def _serve_api_cached(self, conn, endpoint, builder_func, ttl=1.5):
        """Global Shared State Cache: Xuat ra toan bo client cung 1 luc tu chung 1 bo dem."""
        import gc
        import time
        now = time.time()
        
        if not hasattr(self, "_api_cache"):
            self._api_cache = {}
            
        # 1. Kiem tra cache de dung chung bo nho byte raw
        if endpoint in self._api_cache:
            cached_time, cached_bytes = self._api_cache[endpoint]
            if now - cached_time < ttl:
                try:
                    conn.settimeout(1.0)
                    conn.sendall(cached_bytes)
                except:
                    pass
                return

        # 2. Neu het han, tao moi va dump json
        gc.collect()
        data = builder_func()
        body = json.dumps(data)
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
        )
        response_bytes = header.encode() + body.encode()
        
        # 3. Luu vao cache toan cuc
        self._api_cache[endpoint] = (now, response_bytes)
        
        try:
            conn.settimeout(1.0)
            conn.sendall(response_bytes)
        except:
            pass

    @staticmethod
    def _send_json(conn, data):
        """Gui HTTP response dang JSON - toi uu phan tach Header/Body de tranh ton RAM."""
        import gc
        try:
            # Dat timeout 1s cho viec truyen tai payload JSON an toan
            conn.settimeout(1.0)
        except:
            pass
        gc.collect() # Giai phong dung luong truoc khi khoi tao chuoi JSON lon
        body = json.dumps(data)
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
        )
        # Combine header and body to avoid TCP Delayed ACK (200ms latency on some OSes)
        conn.sendall(header.encode() + body.encode())
    @staticmethod
    def _stream_file(conn, path, if_none_match=None, accept_gzip=False):
        """Stream file HTML tu flash, uu tien file .gz nen san neu trinh duyet ho tro.
        
        Gzip pre-compression giam 23KB -> ~5KB, giai phong socket nhanh hon 4x.
        ETag caching tra ve 304 ngay lap tuc khi file chua doi.
        """
        import gc
        import os
        try:
            conn.settimeout(2.0)
        except:
            pass
        gc.collect()

        # Kiem tra file .gz nen san co ton tai va trinh duyet co ho tro gzip khong
        gz_path = path + ".gz"
        use_gzip = False
        if accept_gzip:
            try:
                os.stat(gz_path)
                use_gzip = True
            except OSError:
                pass

        # Stat file goc de tinh ETag (luon dua tren file goc, khong phai file .gz)
        try:
            stat = os.stat(path)
            size = stat[6]
            mtime = stat[8] if len(stat) > 8 else 0
        except OSError:
            conn.sendall(
                b"HTTP/1.1 404 Not Found\r\nContent-Type:text/plain\r\n"
                b"Connection:close\r\nContent-Length:13\r\n\r\n404 Not Found"
            )
            return

        # ETag dua tren kich thuoc va thoi gian sua doi cua file goc
        etag = f'"{ size}-{mtime}"'

        # Neu ETag trung khop, tra ve 304 ngay lap tuc
        if if_none_match == etag:
            resp = (
                "HTTP/1.1 304 Not Modified\r\n"
                f"ETag: {etag}\r\n"
                "Cache-Control: no-cache, must-revalidate\r\n"
                "Connection: close\r\n\r\n"
            )
            conn.sendall(resp.encode())
            return

        # Xac dinh file thuc te se stream (nen hoac goc)
        if use_gzip:
            gz_stat = os.stat(gz_path)
            send_size = gz_stat[6]
            send_path = gz_path
        else:
            send_size = size
            send_path = path

        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Cache-Control: no-cache, must-revalidate\r\n"
            f"ETag: {etag}\r\n"
            + ("Content-Encoding: gzip\r\n" if use_gzip else "")
            + "Connection: close\r\n"
            f"Content-Length: {send_size}\r\n"
            "\r\n"
        )
        # Combine header and the first chunk to avoid TCP Delayed ACK
        with open(send_path, "rb") as f:
            first_chunk = f.read(1024)
            conn.sendall(header.encode() + first_chunk)
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                conn.sendall(chunk)

    @staticmethod
    def _redirect(conn, path="/"):
        """Gui HTTP redirect 302 - toi uu phan tach Header/Body."""
        body = f"<html><body><script>window.location='{path}'</script></body></html>"
        header = (
            "HTTP/1.1 302 Found\r\n"
            f"Location: {path}\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
        )
        conn.sendall(header.encode())
        conn.sendall(body.encode())
