import json
import os


class ConfigManager:
    FILE = "wifi_config.json"

    @classmethod
    def load(cls):
        try:
            with open(cls.FILE) as f:
                return json.load(f)
        except:
            return {}

    @classmethod
    def save(cls, data):
        with open(cls.FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def delete(cls):
        try:
            os.remove(cls.FILE)
        except:
            pass
