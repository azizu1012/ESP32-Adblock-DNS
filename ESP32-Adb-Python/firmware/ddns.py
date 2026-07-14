"""Cập nhật Dynamic DNS No-IP.

Đọc thông tin đăng nhập từ wifi_config.json (noip_user/pass/host).
Chạy mỗi 12 giờ qua tick().
"""
import socket
import time
from config import ConfigManager


class DDNSUpdater:
    HOST = "dynupdate.no-ip.com"
    INTERVAL = 43200

    def __init__(self):
        """Khởi tạo với last_run = 0 (sẽ chạy ngay lần tick đầu)."""
        self.last_run = 0

    def update(self, cfg=None):
        """Gửi request cập nhật IP lên No-IP ngay lập tức."""
        if cfg is None:
            cfg = ConfigManager.load()
        self._noip(cfg)
        self.last_run = time.time()

    def tick(self, cfg=None):
        """Kiểm tra và cập nhật nếu đã quá INTERVAL (12h)."""
        if time.time() - self.last_run > self.INTERVAL:
            self.update(cfg)

    def _noip(self, cfg):
        """Tạo socket HTTP và gửi GET request tới No-IP API để cập nhật IP."""
        user = cfg.get("noip_user", "")
        password = cfg.get("noip_pass", "")
        hostname = cfg.get("noip_host", "")
        if not (user and password and hostname):
            return
        print("Updating No-IP...")
        try:
            s = socket.socket()
            s.settimeout(6)
            addr = socket.getaddrinfo(self.HOST, 80)[0][-1]
            s.connect(addr)
            import ubinascii
            auth = ubinascii.b2a_base64(f"{user}:{password}".encode()).decode().strip()
            body = (
                f"GET /nic/update?hostname={hostname} HTTP/1.1\r\n"
                f"Host: {self.HOST}\r\n"
                f"Authorization: Basic {auth}\r\n"
                f"User-Agent: ESP32_AdBlocker_DDNS/1.0 {user}\r\n"
                f"Connection: close\r\n\r\n"
            )
            s.sendall(body.encode())
            resp = s.recv(512).decode()
            s.close()
            print("No-IP:", resp.split("\r\n")[-1].strip())
        except Exception as e:
            print("No-IP fail:", e)
