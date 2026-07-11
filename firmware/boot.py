"""Entry point: WiFi connect, DNS + Web threads, LED heartbeat.

Boot sequence:
1. Kiểm tra nút BOOT giữ 3s → factory reset
2. Đọc wifi_config.json → kết nối WiFi
3. Thành công: chạy DNS proxy + web server trên luồng riêng
4. Thất bại: bật chế độ AP để cấu hình
"""
import time
import utime
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
# Biến toàn cục theo dõi sức khoẻ DNS (Watchdog)
dns_last_tick = 0

def led_state_thread(stats):
    """Đèn LED thông minh 3 lớp đồng thời:
    1. Cấp cứu (Dead/Booting): Chớp ngẫu nhiên liên tục (Ghi đè tất cả)
    2. LAN Activity (Allowed/Blocked): Chớp phản hồi ngay lập tức
    3. Nhịp tim (Lub-Dub): Đập định kỳ 2-4s dưới nền (không cần chờ Idle)"""
    import random
    import utime
    
    last_total = stats.total
    last_blocked = stats.blocked
    next_heartbeat = utime.ticks_ms() + 2000
    
    while True:
        try:
            now = utime.ticks_ms()
            
            # 1. Trạng thái cấp cứu (Booting hoặc DNS treo > 3s)
            if dns_last_tick == 0 or utime.ticks_diff(now, dns_last_tick) > 3000:
                led.value(0)
                utime.sleep_ms(random.randint(20, 80))
                led.value(1)
                utime.sleep_ms(random.randint(20, 80))
                next_heartbeat = utime.ticks_ms() + 2000 # Reset timer
                continue
                
            current_total = stats.total
            current_blocked = stats.blocked
            
            # 2. Xử lý Traffic (LAN Activity / Blocked) ngay lập tức
            if current_total > last_total:
                if current_blocked > last_blocked:
                    # Bị chặn -> Sập nguồn 300ms
                    led.value(0)
                    utime.sleep_ms(300)
                    led.value(1)
                else:
                    # Chạy qua -> Chớp LAN 20ms
                    diff = min(3, current_total - last_total)
                    for _ in range(diff):
                        led.value(0)
                        utime.sleep_ms(20)
                        led.value(1)
                        utime.sleep_ms(80)
                        
                last_total = current_total
                last_blocked = current_blocked
                continue
                
            # 3. Trạng thái nhịp tim (Lub-Dub Heartbeat) định kỳ
            if utime.ticks_diff(now, next_heartbeat) >= 0:
                # Lub
                led.value(0); utime.sleep_ms(50); led.value(1)
                utime.sleep_ms(120)
                # Dub
                led.value(0); utime.sleep_ms(50); led.value(1)
                
                next_heartbeat = utime.ticks_ms() + random.randint(2000, 4000)
                continue
                
            # 4. Chờ (Polling rate 50ms cho LED)
            led.value(1)
            utime.sleep_ms(50)
            
        except Exception:
            try:
                import utime
                utime.sleep_ms(1000)
            except:
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
        
        # Khởi chạy LED UX Monitor liên kết chặt chẽ với DNS Stats
        _thread.start_new_thread(led_state_thread, (stats,))

        wdt = WDT(timeout=30_000)
        ddns = DDNSUpdater()
        
        wifi_lost_ticks = 0
        
        while True:
            try:
                # ═══════════════════════════════════════════════
                # CRITICAL PATH: DNS Forwarding — BẤT KHẢ XÂM PHẠM
                # Dù mọi thứ khác có cháy, lõi xoay DNS PHẢI sống
                # ═══════════════════════════════════════════════
                try:
                    global dns_last_tick
                    dns_last_tick = utime.ticks_ms()
                    dns.poll()
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
                        if wifi_lost_ticks == 0:
                            wifi_lost_ticks = utime.ticks_ms()
                        elif utime.ticks_diff(utime.ticks_ms(), wifi_lost_ticks) > 60000:
                            # Mất mạng liên tục quá 60 giây -> Restart để gỡ lỗi WiFi
                            print("WiFi lost for > 60s, saving stats and rebooting...")
                            stats.save()
                            machine.reset()
                    else:
                        wifi_lost_ticks = 0
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
