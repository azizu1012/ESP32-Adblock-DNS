import sys, struct, os

def fnv1a_32(b):
    h = 0x811C9DC5
    for byte in b:
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h

def parse_domains(path):
    doms = set()
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#") or line.startswith("!") or line.startswith("::1"):
                continue
            # hosts format: 0.0.0.0 domain.com
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                d = parts[1]
                if d not in ("localhost", "localhost.localdomain"):
                    doms.add(d)
            # AdGuard format: ||domain.com^
            elif "||" in line and "^" in line:
                start = line.find("||") + 2
                end = line.find("^", start)
                if end > start:
                    d = line[start:end]
                    if "." in d:
                        doms.add(d)
            # plain domain
            elif "." in line:
                d = line.split()[0] if " " in line else line
                if d.count(".") >= 1 and not any(c in d for c in "/@"):
                    doms.add(d)
    return doms

tmp_dir = sys.argv[1]
out_path = os.path.join("D:\\AI_Projects\\ESP32-Side-PRJ\\firmware", "blocked.bin")

all_d = set()
for fname in os.listdir(tmp_dir):
    p = os.path.join(tmp_dir, fname)
    if os.path.isfile(p):
        doms = parse_domains(p)
        print(f"  {fname}: {len(doms)} domains")
        all_d.update(doms)

print(f"Total unique domains: {len(all_d)}")
hashes = set()
for d in all_d:
    hashes.add(fnv1a_32(d.encode("utf-8")))
print(f"Unique hashes: {len(hashes)} ({(len(hashes) - len(all_d))} collisions)")
sh = sorted(hashes)
with open(out_path, "wb") as f:
    for h in sh:
        f.write(struct.pack("<I", h))
kb = len(sh) * 4 / 1024
print(f"Written: {kb:.1f} KB / {len(sh)} entries -> {out_path}")
