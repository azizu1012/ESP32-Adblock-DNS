"""WiFi connection manager.

Hỗ trợ static IP, DHCP với auto-assign, và chế độ AP setup.
Auto-assign lưu IP nhận từ DHCP làm static ngay lần kết nối đầu.
"""
import network
import time
import machine
from config import ConfigManager


class WiFiManager:
    CONFIG_SSID = "ESP32-AdBlocker-Config"

    def __init__(self):
        """Bật WiFi STA interface."""
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)

    @staticmethod
    def set_hostname(name="esp32-adblocker"):
        """Đặt hostname DHCP (dùng try/except vì API khác nhau giữa các bản MicroPython)."""
        try:
            network.hostname(name)
        except:
            try:
                network.WLAN(network.STA_IF).config(dhcp_hostname=name)
            except:
                pass

    def connect(self, cfg):
        """Kết nối WiFi: dùng static IP nếu có, fallback DHCP, timeout 30s."""
        ssid = cfg.get("ssid")
        password = cfg.get("password", "")
        static_ip = cfg.get("ip")
        gateway = cfg.get("gateway")
        subnet = cfg.get("subnet", "255.255.255.0")

        if not ssid:
            return False

        if static_ip and gateway:
            self.wlan.ifconfig((static_ip, subnet, gateway, "1.1.1.1"))
            print(f"Static IP: {static_ip}")

        print(f"Connecting to {ssid}...")
        self.wlan.connect(ssid, password)

        for _ in range(60):
            if self.wlan.isconnected():
                break
            time.sleep(0.5)

        if self.wlan.isconnected():
            ip_info = self.wlan.ifconfig()
            print(f"Connected: {ip_info}")
            if not static_ip:
                self._auto_assign_static(ssid, password, ip_info, subnet)
            return True

        print("Wi-Fi failed")
        return False

    def _auto_assign_static(self, ssid, password, ip_info, subnet):
        """Tự gán IP tĩnh (xxx.xxx.xxx.234) từ DHCP lease nhận được, reset để áp dụng."""
        parts = ip_info[0].split(".")
        new_ip = ".".join(parts[:3]) + ".234"
        gateway = ip_info[2]
        print(f"Auto-assigning {new_ip}")
        ConfigManager.save({
            "ssid": ssid, "password": password,
            "ip": new_ip, "gateway": gateway, "subnet": subnet,
        })
        time.sleep(1)
        machine.reset()

    def start_ap(self):
        """Bật Access Point để cấu hình lần đầu."""
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=self.CONFIG_SSID, authmode=network.AUTH_OPEN)
        print(f"AP started: {self.CONFIG_SSID}")
        return ap.ifconfig()[0]

    def is_connected(self):
        """Kiểm tra trạng thái kết nối WiFi."""
        return self.wlan.isconnected()

    def ifconfig(self):
        """Trả về (ip, subnet, gateway, dns)."""
        return self.wlan.ifconfig()
