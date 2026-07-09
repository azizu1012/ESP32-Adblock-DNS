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


def led_on(t):
    """Bật LED — callback timer."""
    led.value(1)


def blink_off(duration=150):
    """Tắt LED trong `duration` ms, dùng timer one-shot rồi bật lại."""
    led.value(0)
    led_timer.init(period=duration, mode=Timer.ONE_SHOT, callback=led_on)


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

    dns = DNSServer(stats)
    try:
        dns.optimize_upstream(wifi)
    except Exception as e:
        print("Initial optimize error:", e)

    web = WebServer(stats, dns)
    _thread.start_new_thread(web.serve, (wifi,))
    dns.start()
    print("System ready!")
    led.value(1) # LED luôn sáng mặc định

    wdt = WDT(timeout=30_000)
    ddns = DDNSUpdater()
    last_hb = time.time()
    while True:
        try:
            handle_boot_button()
            now = time.time()
            if now - last_hb >= 10:
                last_hb = now
                blink_off(60) # Nháy tắt 60ms làm nhịp heartbeat
            try:
                if dns.poll():
                    blink_off(100) # Tắt hẳn 100ms khi có truy vấn bị chặn
            except Exception as inner:
                print("DNS poll error:", inner)
            if not wifi.is_connected():
                print("WiFi lost, reconnecting...")
                if wifi.connect(cfg):
                    try:
                        dns.optimize_upstream(wifi)
                    except:
                        pass
            dns.tick(wifi)
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
    web = WebServer(stats, ip=ap_ip)
    web.serve(wifi)
