"""Entry point: WiFi connect, DNS + Web threads, LED heartbeat.

Boot sequence:
1. Check BOOT button hold (3s) → factory reset
2. Load wifi_config.json → connect to WiFi
3. On success: start DNS proxy + web server in threads
4. On failure: start AP mode for setup
"""
import time
import machine
from machine import Pin, Timer
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
    led.value(0)


def blink(duration=70):
    led.value(1)
    led_timer.init(period=duration, mode=Timer.ONE_SHOT, callback=led_off)


def handle_boot_button():
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

    ddns = DDNSUpdater()
    last_hb = time.time()
    while True:
        handle_boot_button()
        now = time.time()
        if now - last_hb >= 5:
            last_hb = now
            blink(30)
        if dns.poll():
            blink()
        stats.tick()
        ddns.tick(cfg)
else:
    led.value(1)
    ap_ip = wifi.start_ap()
    web = WebServer(None, ip=ap_ip)
    web.serve(wifi)
