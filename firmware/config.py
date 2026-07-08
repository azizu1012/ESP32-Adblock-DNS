"""Đọc/ghi file cấu hình WiFi dạng JSON.

File: wifi_config.json
Keys: ssid, password, ip, gateway, subnet, noip_user|pass|host
"""
import json
import os


class ConfigManager:
    FILE = "wifi_config.json"

    @classmethod
    def load(cls):
        """Đọc file config JSON, trả về dict rỗng nếu không tồn tại."""
        try:
            with open(cls.FILE) as f:
                return json.load(f)
        except:
            return {}

    @classmethod
    def save(cls, data):
        """Ghi dict config xuống file JSON."""
        with open(cls.FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def delete(cls):
        """Xoá file config (factory reset)."""
        try:
            os.remove(cls.FILE)
        except:
            pass
