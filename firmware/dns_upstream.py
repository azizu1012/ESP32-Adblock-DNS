import time
import socket
import gc
import _thread

def _measure_rtt(self, ip, timeout_ms=300):
    """Đo độ trễ RTT tới một IP bằng cách gửi DNS query cho google.com."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_ms / 1000.0)
    try:
        t0 = time.ticks_us()
        q = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01'
        sock.sendto(q, (ip, 53))
        resp, _ = sock.recvfrom(512)
        if resp and resp[:2] == b'\xaa\xbb':
            dt_us = time.ticks_diff(time.ticks_us(), t0)
            return round(dt_us / 1000.0, 1)
    except:
        pass
    finally:
        sock.close()
    return 999999

def _optimize_worker(self, wifi_manager):
    """Luồng ngầm đo độ trễ tới nhiều DNS server và chọn upstream tối ưu nhất."""
    if wifi_manager:
        self.wifi = wifi_manager
    else:
        wifi_manager = self.wifi

    candidates = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "1.0.0.1", "8.8.4.4"]
    if wifi_manager and wifi_manager.is_connected():
        try:
            dhcp_dns = wifi_manager.ifconfig()[3]
            if dhcp_dns and dhcp_dns != "0.0.0.0" and dhcp_dns not in candidates:
                candidates.insert(0, dhcp_dns)
        except:
            pass

    best_ip = self.upstream_ip
    best_rtt = 999999
    print(f"[DNS] Optimizing upstream among {candidates}...")
    for ip in candidates:
        r1 = self._measure_rtt(ip, 300)
        if r1 < 999999:
            r2 = self._measure_rtt(ip, 300)
            rtt = (r1 + r2) // 2
        else:
            rtt = 999999
        print(f"  - DNS {ip}: {rtt if rtt < 999999 else 'timeout'} ms")
        if rtt < best_rtt:
            best_rtt = rtt
            best_ip = ip

    if best_rtt < 999999:
        self.upstream_ip = best_ip
        self.upstream_rtt = best_rtt
        self.stats.upstream_ip = best_ip
        self.stats.upstream_rtt = best_rtt
        print(f"[DNS] Best upstream selected: {best_ip} ({best_rtt} ms)")
    else:
        self.upstream_ip = "1.1.1.1"
        self.upstream_rtt = 0
        self.stats.upstream_ip = "1.1.1.1"
        self.stats.upstream_rtt = 0
        print("[DNS] No responsive upstream, fallback to 1.1.1.1")
    
    self.last_opt_ticks = time.ticks_ms()
    self._is_optimizing = False
    gc.collect()

def optimize_upstream(self, wifi_manager=None):
    """Kích hoạt luồng ngầm tối ưu hóa DNS mà không gây block."""
    if self._is_optimizing:
        return
    self._is_optimizing = True
    try:
        _thread.start_new_thread(self._optimize_worker, (wifi_manager,))
    except Exception as e:
        print(f"[DNS] Failed to start optimize thread: {e}")
        self._is_optimizing = False

def attach(cls):
    cls._measure_rtt = _measure_rtt
    cls._optimize_worker = _optimize_worker
    cls.optimize_upstream = optimize_upstream
