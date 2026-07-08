import socket
import struct
import gc
import os
import time
import select
from machine import Pin, reset, Timer

led = Pin(2, Pin.OUT)
boot_btn = Pin(0, Pin.IN, Pin.PULL_UP)

led_timer = Timer(0)

UPSTREAM_DNS_IPV4 = '1.1.1.1'
DNS_PORT = 53
LISTEN_PORT = 53 # Standard DNS Port
BLOCKED_BIN = 'blocked.bin'
CONFIG_FILE = 'wifi_config.json'

DUCKDNS_DOMAIN = 'esp32adblocker'
DUCKDNS_TOKEN = 'af25ae49-bce2-4ca5-b417-8600c2650669'

def get_noip_credentials():
    try:
        with open(CONFIG_FILE, 'r') as f:
            import json
            cfg = json.load(f)
            return cfg.get('noip_user', ''), cfg.get('noip_pass', ''), cfg.get('noip_host', '')
    except:
        return '', '', ''

def turn_off_led(t):
    led.value(0)

def trigger_led_blink():
    led.value(1)
    led_timer.init(period=70, mode=Timer.ONE_SHOT, callback=turn_off_led)

def monitor_boot_button():
    if boot_btn.value() == 0:
        print("BOOT button pressed, verifying factory reset...")
        press_start = time.time()
        is_reset_trigger = True
        
        while time.time() - press_start < 3.0:
            if boot_btn.value() == 1:
                is_reset_trigger = False
                break
            led.value(not led.value())
            time.sleep(0.1)
            
        if is_reset_trigger:
            print("Factory reset triggered! Clearing Wi-Fi config...")
            try:
                os.remove(CONFIG_FILE)
            except:
                pass
            for _ in range(10):
                led.value(1); time.sleep(0.05)
                led.value(0); time.sleep(0.05)
            reset()
        else:
            led.value(0)

def fnv1a_32(s_bytes):
    h = 0x811c9dc5
    for b in s_bytes:
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    return h

def is_blocked_by_hash(domain_hash):
    try:
        with open(BLOCKED_BIN, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()
            total_elements = file_size // 4
            
            low = 0
            high = total_elements - 1
            
            while low <= high:
                mid = (low + high) // 2
                f.seek(mid * 4)
                val_bytes = f.read(4)
                if not val_bytes or len(val_bytes) < 4:
                    break
                val = struct.unpack('<I', val_bytes)[0]
                
                if val == domain_hash:
                    return True
                elif val < domain_hash:
                    low = mid + 1
                else:
                    high = mid - 1
    except Exception as e:
        print("Error checking blocked.bin:", e)
    return False

def is_blocked_by_rules(domain):
    if "adwords.google.com" in domain or "adidas.com" in domain:
        return False
        
    parts = domain.split('.')
    if not parts:
        return False
        
    first_part = parts[0]
    
    if first_part.startswith('ad'):
        suffix = first_part[2:]
        if not suffix or suffix == 's' or suffix.isdigit() or (suffix.startswith('s') and suffix[1:].isdigit()):
            return True
            
    keywords = ("telemetry", "analytics", "adserver", "adsystem", "doubleclick", "adcolony", "applovin", "popunder")
    for part in parts:
        if part in keywords:
            return True
            
    return False

def parse_domain(data):
    try:
        offset = 12
        labels = []
        while True:
            length = data[offset]
            if length == 0:
                break
            offset += 1
            labels.append(data[offset:offset+length].decode().lower())
            offset += length
        return '.'.join(labels)
    except:
        return None

def build_blocked_response(request_data):
    tx_id = request_data[0:2]
    flags = b'\x81\x80'
    counts = b'\x00\x01\x00\x01\x00\x00\x00\x00'
    
    offset = 12
    while True:
        length = request_data[offset]
        if length == 0:
            offset += 1
            break
        offset += 1 + length
        
    question_sec = request_data[12:offset+4]
    
    ans_name = b'\xc0\x0c'
    ans_class = b'\x00\x01'
    ans_ttl = b'\x00\x00\x01\x2c'
    
    ans_type = b'\x00\x01'
    ans_rdlength = b'\x00\x04'
    ans_rdata = b'\x00\x00\x00\x00'
        
    response = tx_id + flags + counts + question_sec + ans_name + ans_type + ans_class + ans_ttl + ans_rdlength + ans_rdata
    return response

# DuckDNS IP WAN Update
def run_duckdns_update():
    print("Updating DuckDNS DDNS...")
    try:
        s = socket.socket()
        s.settimeout(6)
        addr = socket.getaddrinfo('www.duckdns.org', 80)[0][-1]
        s.connect(addr)
        req = "GET /update?domains=" + DUCKDNS_DOMAIN + "&token=" + DUCKDNS_TOKEN + " HTTP/1.1\r\nHost: www.duckdns.org\r\nUser-Agent: ESP32\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode())
        resp = s.recv(512).decode()
        s.close()
        status = resp.split('\r\n')[-1].strip()
        print("DuckDNS update result:", status)
    except Exception as e:
        print("DuckDNS update failed:", e)

# No-IP DDNS Update & Auto-Renew Simulation
def run_noip_update():
    user, password, hostname = get_noip_credentials()
    if user and password and hostname:
        print("Updating No-IP DDNS...")
        try:
            s = socket.socket()
            s.settimeout(6)
            addr = socket.getaddrinfo('dynupdate.no-ip.com', 80)[0][-1]
            s.connect(addr)
            
            import ubinascii
            auth_str = ubinascii.b2a_base64(f"{user}:{password}".encode()).decode().strip()
            
            req = (
                f"GET /nic/update?hostname={hostname} HTTP/1.1\r\n"
                f"Host: dynupdate.no-ip.com\r\n"
                f"Authorization: Basic {auth_str}\r\n"
                f"User-Agent: ESP32_AdBlocker_DDNS/1.0 {user}\r\n"
                f"Connection: close\r\n\r\n"
            )
            s.sendall(req.encode())
            resp = s.recv(512).decode()
            s.close()
            status = resp.split('\r\n')[-1].strip()
            print("No-IP DDNS update result:", status)
        except Exception as e:
            print("No-IP DDNS update failed:", e)

def start_dns_server():
    run_duckdns_update()
    run_noip_update()
    
    # Setup DNS Server Socket on Port 53
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setblocking(False)
    s.bind(('0.0.0.0', LISTEN_PORT))
    
    upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    upstream_sock.settimeout(2.0)
    
    print("DNS AdBlocker Server listening on Port " + str(LISTEN_PORT) + " (IPv4)...")
    
    last_ddns_check = time.time()
    
    while True:
        try:
            monitor_boot_button()
            
            # Periodically renew DDNS every 12 hours (43200 seconds)
            if time.time() - last_ddns_check > 43200:
                run_duckdns_update()
                run_noip_update()
                last_ddns_check = time.time()
            
            readable, _, _ = select.select([s], [], [], 1.0)
            if not readable:
                continue
                
            request, addr = s.recvfrom(512)
            if len(request) < 12:
                continue
                
            trigger_led_blink()
            
            domain = parse_domain(request)
            if domain:
                is_blocked = False
                
                # Rule-based string parsing
                if is_blocked_by_rules(domain):
                    is_blocked = True
                else:
                    # HostsVN hash lookup
                    domain_hash = fnv1a_32(domain.encode('utf-8'))
                    if is_blocked_by_hash(domain_hash):
                        is_blocked = True
                
                if is_blocked:
                    print(f"[BLOCKED] {domain}")
                    response = build_blocked_response(request)
                    s.sendto(response, addr)
                else:
                    try:
                        upstream_sock.sendto(request, (UPSTREAM_DNS_IPV4, DNS_PORT))
                        response, _ = upstream_sock.recvfrom(1024)
                        s.sendto(response, addr)
                    except Exception as err:
                        print("Upstream DNS query error:", err)
            else:
                try:
                    upstream_sock.sendto(request, (UPSTREAM_DNS_IPV4, DNS_PORT))
                    response, _ = upstream_sock.recvfrom(1024)
                    s.sendto(response, addr)
                except:
                    pass
            
            gc.collect()
        except Exception as e:
            print("DNS loop error:", e)
            led.value(0)

wlan = network.WLAN(network.STA_IF)
if wlan.isconnected():
    start_dns_server()
else:
    print("Wi-Fi is not connected. DNS Server will not run.")
