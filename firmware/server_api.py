"""
server_api.py
Chứa toàn bộ logic xử lý các HTTP API Endpoints (GET, POST) cho Web Server.
Được module hóa qua kỹ thuật Monkey Patching để giảm tải RAM cho WebServer class.
Chịu trách nhiệm render JSON stats, cấu hình WiFi, DDNS, Upload Blocked DB, v.v.
"""
import json
import time

def _handle_post(self, conn, data, path, wifi_manager):
    """
    Xử lý các request POST: lưu cấu hình WiFi, DDNS, Reboot, Factory Reset.
    Bóc tách payload JSON từ HTTP body để tương tác với ConfigManager.
    """
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

def _parse_body(request):
    """Giai nen body JSON tu HTTP request."""
    parts = request.split("\r\n\r\n", 1)
    if len(parts) < 2:
        return {}
    try:
        return json.loads(parts[1])
    except Exception:
        return {}

def _build_stats(self, wifi_manager):
    """Xay dung dict stats JSON, them cpu_temp va IP."""
    if self.stats is None:
        d = {"v": "0", "total": 0, "blocked": 0, "allowed": 0, "ratio": 0,
             "uptime": 0, "free_ram": 0, "alloc_ram": 0, "total_ram": 0,
             "last_blocked": "", "recent": [], "cpu_temp": None, "ip": "",
             "top": [], "flash_free": 0, "flash_total": 0, "flash_chip": 0,
             "blocklist_entries": 0, "cpu_freq": 0, "core_count": 0,
             "upstream": "1.1.1.1", "upstream_rtt": 0}
        if wifi_manager and wifi_manager.is_connected():
            try:
                d["ip"] = wifi_manager.ifconfig()[0]
            except Exception:
                pass
        return d
    d = self.stats.to_dict()
    import os
    try:
        try:
            st = os.stat("web/app.html")
        except OSError:
            st = os.stat("web/app.html.gz")
        d["v"] = f"{st[6]}-{st[8] if len(st) > 8 else 0}"
    except Exception:
        d["v"] = "0"

    d["cpu_temp"] = self._get_cpu_temp()
    d["ip"] = ""
    if wifi_manager and wifi_manager.is_connected():
        try:
            d["ip"] = wifi_manager.ifconfig()[0]
        except Exception:
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
    except Exception:
        pass
    finally:
        try:
            self.stats.lock.release()
        except Exception:
            pass
    d["active_clients"] = active_clients

    # Expose dynamic safelist (GCT)
    d["safelist_dyn"] = []
    if self.dns:
        try:
            d["safelist_dyn"] = self.dns.get_safelist_dyn()
        except Exception:
            pass

    # Gộp recent + top vào cùng 1 response để giảm 3 TCP connections -> 1
    try:
        d["recent"] = self.stats.to_recent_list() if self.stats else []
    except Exception:
        d["recent"] = []
    try:
        d["top"] = self.stats.to_top_list() if self.stats else []
    except Exception:
        d["top"] = []

    return d

def _get_cpu_temp():
    """Doc nhiet do CPU tu cam bien trong ESP32, tra ve C."""
    try:
        import esp32
        raw = esp32.raw_temperature()
        if raw < 50 or raw > 200:
            return None
        return round((raw - 32) / 1.8, 1)
    except Exception:
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
            except Exception:
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
    except Exception:
        pass

def _send_json(conn, data):
    """Gui HTTP response dang JSON - toi uu phan tach Header/Body de tranh ton RAM."""
    import gc
    try:
        # Dat timeout 1s cho viec truyen tai payload JSON an toan
        conn.settimeout(1.0)
    except Exception:
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

def attach(cls):
    cls._handle_post = _handle_post
    cls._handle_upload = _handle_upload
    cls._parse_body = staticmethod(_parse_body)
    cls._build_stats = _build_stats
    cls._get_cpu_temp = staticmethod(_get_cpu_temp)
    cls._serve_api_cached = _serve_api_cached
    cls._send_json = staticmethod(_send_json)
