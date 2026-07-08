"""Sinh blocked.bin từ danh sách blocklist dạng hosts hoặc AdBlock.

Quy trình:
1. Parse nhiều file blocklist → tập domain duy nhất
2. Dedup subdomain (nếu cha đã block thì bỏ con)
3. Tính FNV-1a 64-bit hash cho mỗi domain
4. Sắp xếp hash, ghi ra file nhị phân (8 byte/entry)

Usage:
  python tools/process_blocked.py <input_dir> [<output_dir>]
"""
import sys, struct, os


def fnv1a_64(b):
    """Tính FNV-1a 64-bit hash cho bytes đầu vào."""
    h = 0xCBF29CE484222325
    p = 0x100000001B3
    for byte in b:
        h = ((h ^ byte) * p) & 0xFFFFFFFFFFFFFFFF
    return h


def parse_domains(path):
    """Parse file blocklist: hosts format (0.0.0.0 x), AdGuard format (||x^), hoặc domain thuần."""
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
    """Loại bỏ subdomain nếu parent domain đã có trong danh sách.
    
    VD: 'ads.doubleclick.net' bị loại nếu 'doubleclick.net' đã block.
    """
    keep = set()
    for d in sorted(domains, key=lambda x: x.count(".")):
        parts = d.split(".")
        has_parent = any(".".join(parts[i:]) in keep for i in range(1, len(parts) - 1))
        if not has_parent:
            keep.add(d)
    return keep


def generate(tmp_dir, out_dir=None):
    """Đọc tất cả file .txt trong tmp_dir, parse, dedup, hash, ghi blocked.bin dạng Blocked Bloom Filter."""
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

    NUM_BLOCKS = 18750
    BLOCK_SIZE = 64  # 64 bytes = 512 bits
    bitmap = bytearray(NUM_BLOCKS * BLOCK_SIZE)

    for d in all_d:
        h = fnv1a_64(d.encode("utf-8"))
        block_idx = (h >> 32) % NUM_BLOCKS
        h_low = h & 0xFFFFFFFF
        for i in range(8):
            bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512
            byte_pos = block_idx * BLOCK_SIZE + (bit_pos // 8)
            bit_mask = 1 << (bit_pos % 8)
            bitmap[byte_pos] |= bit_mask

    with open(out_path, "wb") as f:
        f.write(bitmap)
        f.write(struct.pack("<I", len(all_d)))
    print(f"Written Blocked Bloom Filter: {len(bitmap)/1024:.1f} KB / {len(all_d)} domains -> {out_path}")



if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
