import time
import socket
import struct

def _enqueue_verification(self, domain):
    """Thêm domain vào hàng đợi kiểm chứng ngầm GCT nếu chưa có."""
    with self.lock:
        if domain not in self.verify_queue:
            if len(self.verify_queue) < 20:
                self.verify_queue.append(domain)

def _dns_query_raw(self, domain, server_ip, timeout=1.5):
    """Gửi gói tin DNS UDP thô để xác minh trạng thái domain ở luồng phụ."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        header = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        parts = domain.split('.')
        qname = b''
        for part in parts:
            qname += bytes([len(part)]) + part.encode()
        qname += b'\x00'
        footer = b'\x00\x01\x00\x01'
        query = header + qname + footer

        sock.sendto(query, (server_ip, 53))
        resp, _ = sock.recvfrom(512)
        if len(resp) > 12:
            ancount = struct.unpack(">H", resp[6:8])[0]
            if ancount > 0:
                ip = resp[-4:]
                if ip != b'\x00\x00\x00\x00' and ip != b'\x7f\x00\x00\x01':
                    return True
        return False
    except:
        return False
    finally:
        sock.close()

def _verify_worker(self):
    """Luồng phụ liên tục kiểm chứng hàng đợi bằng cơ chế đồng thuận 3/3."""
    while True:
        if not getattr(self, "verify_queue", None):
            time.sleep(2)
            continue

        domain = None
        with self.lock:
            if self.verify_queue:
                domain = self.verify_queue.pop(0)

        if not domain:
            continue

        g_ok = self._dns_query_raw(domain, "8.8.8.8")
        if not g_ok:
            continue

        adg_ok = self._dns_query_raw(domain, "94.140.14.14")
        ctd_ok = self._dns_query_raw(domain, "76.76.2.2")
        mul_ok = self._dns_query_raw(domain, "194.242.2.12")

        if adg_ok and ctd_ok and mul_ok:
            self._heal_domain(domain)
        else:
            with self.lock:
                if domain in self.safelist_dyn:
                    del self.safelist_dyn[domain]
                    print(f"[GCT] Re-blocked real ad: {domain}")

def _heal_domain(self, domain):
    """Đưa domain vào diện tạm tha và thăng hạng cấp độ tin cậy."""
    with self.lock:
        level = 0
        ttl = 300
        if domain in self.safelist_dyn:
            _, old_level, _ = self.safelist_dyn[domain]
            if old_level == 0:
                level = 1
                ttl = 3600
            elif old_level >= 1:
                level = 2
                ttl = 86400
        
        self.safelist_dyn[domain] = (time.time() + ttl, level, time.time())
        print(f"[GCT] Self-healed {domain}: level={level}, ttl={ttl}s")

def attach(cls):
    cls._enqueue_verification = _enqueue_verification
    cls._dns_query_raw = _dns_query_raw
    cls._verify_worker = _verify_worker
    cls._heal_domain = _heal_domain
