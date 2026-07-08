import urllib.request
import struct

# FNV-1a 32-bit — matching dns.py
def fnv1a_32(s_bytes):
    h = 0x811C9DC5
    for b in s_bytes:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h

SOURCES = [
    ("HostsVN (ads + scam)", "https://raw.githubusercontent.com/bigdargon/hostsVN/master/hosts"),
    ("StevenBlack (ads + tracking)", "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"),
    ("AdGuard DNS filter", "https://raw.githubusercontent.com/AdguardTeam/AdguardSDNSFilter/master/Filters/filter.txt"),
]

def extract_domains(url, label):
    print(f"Downloading {label}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read().decode("utf-8", errors="ignore")
    domains = set()
    for line in data.splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#") or line.startswith("::1") or line.startswith("!"):
            continue
        if line.startswith("0.0.0.0 ") or line.startswith("127.0.0.1 ") or line.startswith("0.0.0.0\t") or line.startswith("127.0.0.1\t"):
            parts = line.split()
            if len(parts) >= 2:
                d = parts[1]
                if d not in ("localhost", "localhost.localdomain"):
                    domains.add(d)
        elif "||" in line and "^" in line:
            # AdGuard syntax: ||domain.com^
            start = line.find("||") + 2
            end = line.find("^", start)
            if end > start:
                d = line[start:end]
                if "." in d:
                    domains.add(d)
        elif "." in line and not line.startswith("0") and not line.startswith("127"):
            # Plain domain line
            d = line.split()[0] if " " in line else line
            if "." in d and not d.startswith("#"):
                domains.add(d)
    print(f"  -> {len(domains)} domains")
    return domains

def generate_bin():
    all_domains = set()
    for label, url in SOURCES:
        doms = extract_domains(url, label)
        all_domains.update(doms)
    print(f"\nTotal unique domains: {len(all_domains)}")
    print("Hashing with FNV-1a 32-bit...")
    hashes = set()
    for dom in all_domains:
        hashes.add(fnv1a_32(dom.encode("utf-8")))
    print(f"Unique hashes: {len(hashes)}")
    sorted_h = sorted(hashes)
    out_path = "D:\\AI_Projects\\ESP32-Side-PRJ\\firmware\\blocked.bin"
    with open(out_path, "wb") as f:
        for h in sorted_h:
            f.write(struct.pack("<I", h))
    size_kb = len(sorted_h) * 4 / 1024
    print(f"Written: {out_path}")
    print(f"Size: {len(sorted_h)} hashes, {size_kb:.1f} KB")

if __name__ == "__main__":
    generate_bin()
