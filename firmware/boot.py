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


def led_heartbeat_thread():
    """Nhịp tim sinh học kép (Lub-Dub) chạy ngầm trên luồng riêng, không nghẽn luồng chính."""
    import random
    while True:
        try:
            # Nhịp nghỉ ngẫu nhiên 4-7 giây làm thiết bị sinh động
            time.sleep(random.randint(4, 7))
            
            # Nhịp 1 (Lub): tắt nhanh 50ms rồi bật lại
            led.value(0)
            time.sleep(0.05)
            led.value(1)
            
            # Giãn cách 120ms
            time.sleep(0.12)
            
            # Nhịp 2 (Dub): tắt nhanh 50ms rồi bật lại mặc định
            led.value(0)
            time.sleep(0.05)
            led.value(1)
        except Exception:
            pass


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


def main():
    WiFiManager.set_hostname()
    wifi = WiFiManager()
    cfg = ConfigManager.load()
    stats = Stats()

    has_cfg = bool(cfg.get("ssid"))

    if has_cfg:
        if not wifi.connect(cfg):
            print("WiFi failed on boot, but config exists. Rebooting in 5s to retry...")
            for _ in range(50):
                led.value(not led.value())
                time.sleep(0.1)
            machine.reset()

        # Nếu kết nối thành công:
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
        
        # Khởi chạy luồng nhịp tim ngầm độc lập
        _thread.start_new_thread(led_heartbeat_thread, ())

        wdt = WDT(timeout=30_000)
        ddns = DDNSUpdater()
        
        while True:
            try:
                # ═══════════════════════════════════════════════
                # CRITICAL PATH: DNS Forwarding — BẤT KHẢ XÂM PHẠM
                # Dù mọi thứ khác có cháy, lõi xoay DNS PHẢI sống
                # ═══════════════════════════════════════════════
                try:
                    if dns.poll():
                        blink_off(100)
                except Exception as dns_err:
                    print("DNS poll error:", dns_err)

                # ═══════════════════════════════════════════════
                # NON-CRITICAL PATH: Thống kê, DDNS, nút bấm
                # Crash ở đây KHÔNG ĐƯỢC kéo DNS chết theo
                # ═══════════════════════════════════════════════
                try:
                    handle_boot_button()
                except Exception:
                    pass

                try:
                    if not wifi.is_connected():
                        print("WiFi lost, saving stats and rebooting...")
                        stats.save()
                        for _ in range(20):
                            led.value(not led.value())
                            time.sleep(0.1)
                        machine.reset()
                except Exception:
                    pass

                try:
                    dns.tick(wifi)
                except Exception as e:
                    print("DNS tick error:", e)

                try:
                    stats.tick()
                except Exception as e:
                    print("Stats tick error:", e)

                try:
                    ddns.tick(cfg)
                except Exception as e:
                    print("DDNS tick error:", e)

                wdt.feed()
                gc.collect()
            except MemoryError:
                print("Main thread MemoryError! Recovering...")
                gc.collect()
                time.sleep(0.5)
            except Exception as e:
                # KHÔNG reboot! Chỉ log lỗi và tiếp tục chạy DNS
                print("Main loop non-fatal error:", e)
                gc.collect()
                time.sleep(1)
    else:
        # Chỉ vào AP mode khi hoàn toàn không có file cấu hình
        led.value(1)
        ap_ip = wifi.start_ap()
        web = WebServer(stats, ip=ap_ip)
        web.serve(wifi)


if __name__ == "__main__":
    main()
