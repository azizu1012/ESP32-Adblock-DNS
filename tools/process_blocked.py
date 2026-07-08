import sys, struct, os


def fnv1a_64(b):
    h = 0xCBF29CE484222325
    p = 0x100000001B3
    for byte in b:
        h = ((h ^ byte) * p) & 0xFFFFFFFFFFFFFFFF
    return h


def parse_domains(path):
    doms = set()
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#") or line.startswith("!") or line.startswith("::1"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                d = parts[1]
                if d not in ("localhost", "localhost.localdomain"):
                    doms.add(d)
            elif "||" in line and "^" in line:
                start = line.find("||") + 2
                end = line.find("^", start)
                if end > start:
                    d = line[start:end]
                    if "." in d:
                        doms.add(d)
            elif "." in line:
                d = line.split()[0] if " " in line else line
                if d.count(".") >= 1 and not any(c in d for c in "/@"):
                    doms.add(d)
    return doms


def dedup_by_parent(domains):
    keep = set()
    for d in sorted(domains, key=lambda x: x.count(".")):
        parts = d.split(".")
        has_parent = any(".".join(parts[i:]) in keep for i in range(1, len(parts) - 1))
        if not has_parent:
            keep.add(d)
    return keep


def generate(tmp_dir, out_dir=None):
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(__file__), "..", "firmware")
    out_path = os.path.join(out_dir, "blocked.bin")

    all_d = set()
    for fname in os.listdir(tmp_dir):
        p = os.path.join(tmp_dir, fname)
        if os.path.isfile(p) and not fname.startswith("."):
            doms = parse_domains(p)
            print(f"  {fname}: {len(doms)} domains")
            all_d.update(doms)

    print(f"Total unique domains: {len(all_d)}")
    all_d = dedup_by_parent(all_d)
    print(f"After subdomain dedup: {len(all_d)}")

    hashes = set()
    for d in all_d:
        hashes.add(fnv1a_64(d.encode("utf-8")))
    coll = len(hashes) - len(all_d)
    print(f"Unique hashes: {len(hashes)}{' (' + str(coll) + ' collisions)' if coll else ', zero collisions'}")

    sh = sorted(hashes)
    with open(out_path, "wb") as f:
        for h in sh:
            f.write(struct.pack("<Q", h))
    kb = len(sh) * 8 / 1024
    print(f"Written: {kb:.1f} KB / {len(sh)} entries -> {out_path}")


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
