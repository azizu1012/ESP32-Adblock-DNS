"""Dynamic DNS updaters: DuckDNS + No-IP.

Credentials are read from wifi_config.json:
  duckdns_domain, duckdns_token, noip_user|pass|host
Runs every 12 hours via tick().
"""
import socket
import time
from config import ConfigManager


class DDNSUpdater:
    DUCKDNS_HOST = "www.duckdns.org"
    NOIP_HOST = "dynupdate.no-ip.com"
    INTERVAL = 43200

    def __init__(self):
        self.last_run = 0

    def update(self, cfg=None):
        if cfg is None:
            cfg = ConfigManager.load()
        self._duckdns(cfg)
        self._noip(cfg)
        self.last_run = time.time()

    def tick(self, cfg=None):
        if time.time() - self.last_run > self.INTERVAL:
            self.update(cfg)

    def _duckdns(self, cfg):
        domain = cfg.get("duckdns_domain", "")
        token = cfg.get("duckdns_token", "")
        if not (domain and token):
            return
        print("Updating DuckDNS...")
        try:
            s = socket.socket()
            s.settimeout(6)
            addr = socket.getaddrinfo(self.DUCKDNS_HOST, 80)[0][-1]
            s.connect(addr)
            body = f"GET /update?domains={domain}&token={token} HTTP/1.1\r\nHost: {self.DUCKDNS_HOST}\r\nUser-Agent: ESP32\r\nConnection: close\r\n\r\n"
            s.sendall(body.encode())
            resp = s.recv(512).decode()
            s.close()
            print("DuckDNS:", resp.split("\r\n")[-1].strip())
        except Exception as e:
            print("DuckDNS fail:", e)

    def _noip(self, cfg):
        user = cfg.get("noip_user", "")
        password = cfg.get("noip_pass", "")
        hostname = cfg.get("noip_host", "")
        if not (user and password and hostname):
            return
        print("Updating No-IP...")
        try:
            s = socket.socket()
            s.settimeout(6)
            addr = socket.getaddrinfo(self.NOIP_HOST, 80)[0][-1]
            s.connect(addr)
            import ubinascii
            auth = ubinascii.b2a_base64(f"{user}:{password}".encode()).decode().strip()
            body = (
                f"GET /nic/update?hostname={hostname} HTTP/1.1\r\n"
                f"Host: {self.NOIP_HOST}\r\n"
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
