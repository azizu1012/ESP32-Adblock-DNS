"""Entry point: WiFi connect, DNS + Web threads, LED heartbeat.

Boot sequence:
1. Kiểm tra nút BOOT giữ 3s → factory reset
2. Đọc wifi_config.json → kết nối WiFi
3. Thành công: chạy DNS proxy + web server trên luồng riêng
4. Thất bại: bật chế độ AP để cấu hình
"""
import time
import gc
import machine
from machine import Pin, Timer, WDT
import _thread
from config import ConfigManager
from wifi import WiFiManager
from stats import Stats
from dns import DNSServer
from server import WebServer
from ddns import DDNSUpdater

led = Pin(2, Pin.OUT)
boot_btn = Pin(0, Pin.IN, Pin.PULL_UP)
led_timer = Timer(0)


def led_off(t):
    """Tắt LED — callback timer."""
    led.value(0)


def blink(duration=70):
    """Nhấp nháy LED trong `duration` ms, dùng timer one-shot."""
    led.value(1)
    led_timer.init(period=duration, mode=Timer.ONE_SHOT, callback=led_off)


def handle_boot_button():
    """Kiểm tra nút BOOT: giữ 3 giây → xoá config + reset."""
    if boot_btn.value() == 0:
        print("BOOT pressed")
        start = time.time()
        hold = True
        while time.time() - start < 3.0:
            if boot_btn.value() == 1:
                hold = False
                break
            led.value(not led.value())
            time.sleep(0.1)
        if hold:
            ConfigManager.delete()
            for _ in range(10):
                led.value(1)
                time.sleep(0.05)
                led.value(0)
                time.sleep(0.05)
            machine.reset()
        led.value(0)


WiFiManager.set_hostname()
wifi = WiFiManager()
cfg = ConfigManager.load()
stats = Stats()

if cfg.get("ssid") and wifi.connect(cfg):

    web = WebServer(stats)
    _thread.start_new_thread(web.serve, (wifi,))

    dns = DNSServer(stats)
    dns.start()
    print("System ready!")

    wdt = WDT(timeout=30_000)
    ddns = DDNSUpdater()
    last_hb = time.time()
    while True:
        try:
            handle_boot_button()
            now = time.time()
            if now - last_hb >= 5:
                last_hb = now
                blink(30)
            try:
                if dns.poll():
                    blink()
            except Exception as inner:
                print("DNS poll error:", inner)
            if not wifi.is_connected():
                print("WiFi lost, reconnecting...")
                wifi.connect(cfg)
            stats.tick()
            ddns.tick(cfg)
            wdt.feed()
            gc.collect()
        except Exception as e:
            import sys
            sys.print_exception(e)
            stats.save()
            time.sleep(3)
            machine.reset()
else:
    led.value(1)
    ap_ip = wifi.start_ap()
    web = WebServer(None, ip=ap_ip)
    web.serve(wifi)
