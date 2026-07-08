import socket
import time
import urllib.request
import json
import random

ESP_IP = "192.168.1.234"
DNS_PORT = 53
NUM_REQUESTS = 500

# Mix of domains: allowed, blocked (static/hash), and local bypass
DOMAINS = [
    "google.com", "facebook.com", "github.com", "wikipedia.org", "youtube.com",
    "doubleclick.net", "ads.yahoo.com", "adservice.google.com", "telemetry.parsec.app",
    "printer.local", "router.local", "mydevice.arpa", "builds.parsec.app"
]

def make_dns_query(domain):
    tid = random.randint(0, 65535).to_bytes(2, "big")
    flags = b"\x01\x00"  # Standard query with recursion desired
    counts = b"\x00\x01\x00\x00\x00\x00\x00\x00"
    qname = b""
    for part in domain.split("."):
        qname += bytes([len(part)]) + part.encode()
    qname += b"\x00"
    qtype_qclass = b"\x00\x01\x00\x01"  # Type A, Class IN
    return tid + flags + counts + qname + qtype_qclass

def get_esp_stats():
    try:
        url = f"http://{ESP_IP}/api/stats"
        with urllib.request.urlopen(url, timeout=2.0) as req:
            return json.loads(req.read().decode())
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"=== Starting Load Test on ESP32 ({ESP_IP}) ===")
    
    # 1. Fetch baseline RAM
    baseline = get_esp_stats()
    if "error" in baseline:
        print(f"Error connecting to ESP32: {baseline['error']}")
        return
    
    print(f"Baseline RAM: Free={baseline['free_ram']//1024}KB, Alloc={baseline['alloc_ram']//1024}KB, Total={baseline['total_ram']//1024}KB")
    print(f"Sending {NUM_REQUESTS} DNS requests...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    
    success = 0
    timeouts = 0
    t0 = time.time()
    
    ram_track = []
    
    for i in range(1, NUM_REQUESTS + 1):
        domain = random.choice(DOMAINS)
        packet = make_dns_query(domain)
        
        t_sent = time.time()
        try:
            sock.sendto(packet, (ESP_IP, DNS_PORT))
            resp, _ = sock.recvfrom(512)
            if resp:
                success += 1
        except socket.timeout:
            timeouts += 1
            
        # Every 50 requests, query ESP32 stats to monitor memory usage live
        if i % 50 == 0:
            stats = get_esp_stats()
            if "free_ram" in stats:
                ram_track.append(stats["free_ram"])
                print(f"  Progress: {i}/{NUM_REQUESTS} requests | Free RAM: {stats['free_ram']//1024}KB")
            time.sleep(0.05) # Brief pause to allow ESP32 threads to cycle

    total_time = time.time() - t0
    print("\n=== Benchmark Results ===")
    print(f"Total Requests: {NUM_REQUESTS}")
    print(f"Successful Resolves: {success} ({success/NUM_REQUESTS*100:.1f}%)")
    print(f"Timeouts/Dropped: {timeouts} ({timeouts/NUM_REQUESTS*100:.1f}%)")
    print(f"Average Request Rate: {NUM_REQUESTS/total_time:.1f} req/sec")
    print(f"Total Duration: {total_time:.2f}s")
    
    # 3. Fetch final stats
    time.sleep(1.0) # Wait a second for GC to catch up
    final = get_esp_stats()
    
    if "free_ram" in final:
        print(f"\nMemory Stability Summary:")
        print(f"  - Baseline Free RAM: {baseline['free_ram']//1024}KB")
        if ram_track:
            print(f"  - Minimum Free RAM during test: {min(ram_track)//1024}KB")
            print(f"  - Maximum Free RAM during test: {max(ram_track)//1024}KB")
        print(f"  - Final Free RAM (Post-Test): {final['free_ram']//1024}KB")
        diff = final['free_ram'] - baseline['free_ram']
        print(f"  - RAM Delta: {diff/1024:+.1f}KB")
        
        if final['free_ram'] >= baseline['free_ram'] * 0.9:
            print("\n[VERDICT] RAM is completely stable! Garbage collection is recycling heap successfully.")
        else:
            print("\n[VERDICT] Warning: RAM consumption remains high. Potential minor memory fragmentation.")
    else:
        print("Could not retrieve final memory stats.")

if __name__ == "__main__":
    main()
