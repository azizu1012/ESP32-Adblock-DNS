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
        """Mo socket TCP, bind, listen voi timeout 1s."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(2)
        self.sock.settimeout(1.0)
        print(f"Web server on port {self.port}")

    def serve(self, wifi_manager=None):
        """Vong lap chinh: chap nhan ket noi, xu ly request, dong."""
        self.start()
        while True:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                continue
            try:
                conn.settimeout(2.0)
                self._handle(conn, wifi_manager)
            except Exception as e:
                print("HTTP serve error:", e)
            finally:
                try:
                    conn.close()
                except:
                    pass

    def _handle(self, conn, wifi_manager):
        """Parse HTTP request header va dieu huong den handler phu hop."""
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

            if path == "/api/upload":
                conn.settimeout(120.0)
                self._handle_upload(conn, buf)
            elif method == "POST":
                self._handle_post(conn, buf, path, wifi_manager)
            elif path == "/api/stats":
                self._send_json(conn, self._build_stats(wifi_manager))
            elif path == "/api/safelist":
                res = list(self.dns.custom_safelist) if (self.dns and hasattr(self.dns, "custom_safelist")) else []
                self._send_json(conn, res)
            elif path.startswith("/api/"):
                self._send_json(conn, {"error": "not found"})
            elif path == "/setup":
                self._stream_file(conn, "web/setup.html")
            else:
                self._stream_file(conn, "web/index.html")
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
            now = time.time()
            ips = set()
            for r in self.stats.recent:
                if len(r) > 4 and now - r[3] < 600:
                    ips.add(r[4])
            if ips:
                active_clients = len(ips)
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

    @staticmethod
    def _send_json(conn, data):
        """Gui HTTP response dang JSON."""
        body = json.dumps(data)
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )
        conn.sendall(resp.encode())

    @staticmethod
    def _stream_file(conn, path):
        """Stream file HTML tu flash toi socket bang buffer 4KB pre-allocated.

        Khong bao gio allocate toan bo file vao RAM.
        Peak RAM usage: chi 4KB buffer + header nho.
        """
        import gc
        gc.collect()
        try:
            size = os.stat(path)[6]
        except OSError:
            body = b"404 Not Found"
            conn.sendall(
                b"HTTP/1.1 404 Not Found\r\nContent-Type:text/plain\r\n"
                b"Connection:close\r\nContent-Length:13\r\n\r\n404 Not Found"
            )
            return

        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Connection: close\r\n"
            f"Content-Length: {size}\r\n"
            "\r\n"
        )
        conn.sendall(header.encode())

        # Pre-allocate buffer mot lan duy nhat, tai su dung xuyen suot
        buf = bytearray(4096)
        with open(path, "rb") as f:
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                conn.sendall(buf if n == 4096 else buf[:n])

    @staticmethod
    def _redirect(conn, path="/"):
        """Gui HTTP redirect 302."""
        body = f"<html><body><script>window.location='{path}'</script></body></html>"
        resp = (
            "HTTP/1.1 302 Found\r\n"
            f"Location: {path}\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )
        conn.sendall(resp.encode())
