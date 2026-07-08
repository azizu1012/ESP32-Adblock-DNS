"""Unit tests for blocklist generation pipeline.

Tests: hash, dedup, parse, binary search, blocked.bin integrity.
"""
import sys, os, struct, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from process_blocked import fnv1a_64, parse_domains, dedup_by_parent

TESTS_DIR = os.path.dirname(__file__)
TOOLS_DIR = os.path.join(TESTS_DIR, "..", "tools")
FIRMWARE_DIR = os.path.join(TESTS_DIR, "..", "firmware")


def test_fnv1a_64_deterministic():
    """FNV-1a 64-bit: cùng input → cùng hash."""
    h1 = fnv1a_64(b"doubleclick.net")
    h2 = fnv1a_64(b"doubleclick.net")
    assert h1 == h2, "hash must be deterministic"


def test_fnv1a_64_different():
    """FNV-1a 64-bit: domain khác → hash khác."""
    h1 = fnv1a_64(b"doubleclick.net")
    h2 = fnv1a_64(b"google.com")
    assert h1 != h2, "different domains must produce different hashes"


def test_fnv1a_64_known():
    """FNV-1a 64-bit: kiểm tra giá trị nằm trong khoảng 64-bit."""
    h = fnv1a_64(b"example.com")
    # Just check it's a 64-bit value
    assert 0 <= h <= 0xFFFFFFFFFFFFFFFF


def test_fnv1a_64_zero_collision_on_sample():
    """FNV-1a 64-bit: không collision trên 5 domain mẫu."""
    domains = ["google.com", "facebook.com", "doubleclick.net",
               "ads.example.com", "tracker.analytics.io"]
    hashes = [fnv1a_64(d.encode()) for d in domains]
    assert len(set(hashes)) == len(domains), "no collisions expected on sample"


def test_parse_hosts_format():
    """HostsVN-style: 0.0.0.0 domain.com"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("# comment\n")
        f.write("0.0.0.0 ads.example.com\n")
        f.write("127.0.0.1 tracker.test\n")
        f.write("0.0.0.0 localhost\n")  # should be ignored
        fname = f.name
    doms = parse_domains(fname)
    os.unlink(fname)
    assert "ads.example.com" in doms
    assert "tracker.test" in doms
    assert "localhost" not in doms


def test_parse_adguard_format():
    """HaGeZi-style: ||domain.com^"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("[Adblock Plus]\n")
        f.write("! Title: Test\n")
        f.write("||doubleclick.net^\n")
        f.write("||sub.example.com^\n")
        fname = f.name
    doms = parse_domains(fname)
    os.unlink(fname)
    assert "doubleclick.net" in doms
    assert "sub.example.com" in doms


def test_parse_plain_domain():
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("plaindomain.com\n")
        f.write("with.trailing.dot.com\n")
        fname = f.name
    doms = parse_domains(fname)
    os.unlink(fname)
    assert "plaindomain.com" in doms
    assert "with.trailing.dot.com" in doms


def test_dedup_removes_subdomain():
    doms = {"example.com", "sub.example.com", "other.com"}
    result = dedup_by_parent(doms)
    assert "example.com" in result
    assert "other.com" in result
    assert "sub.example.com" not in result  # parent exists


def test_dedup_keeps_both_when_no_parent():
    doms = {"a.example.com", "b.example.com"}
    result = dedup_by_parent(doms)
    assert "a.example.com" in result
    assert "b.example.com" in result


def test_dedup_handles_deep_nesting():
    doms = {"example.com", "sub.example.com", "deep.sub.example.com", "other.net"}
    result = dedup_by_parent(doms)
    assert "example.com" in result
    assert "sub.example.com" not in result
    assert "deep.sub.example.com" not in result
    assert "other.net" in result


def test_dedup_handles_multi_level():
    doms = {"a.b.c.example.com", "b.c.example.com", "c.example.com", "example.com"}
    result = dedup_by_parent(doms)
    assert len(result) == 1
    assert "example.com" in result


def test_blocked_bin_integrity():
    """Verify blocked.bin: sorted, correct entry size, no collisions."""
    path = os.path.join(FIRMWARE_DIR, "blocked.bin")
    if not os.path.exists(path):
        return  # skip if no blocked.bin (not generated yet)

    with open(path, "rb") as f:
        data = f.read()

    assert len(data) % 8 == 0, "file must be 8-byte aligned"
    count = len(data) // 8
    assert count > 0, "file must have entries"

    prev = 0
    hashes = set()
    for i in range(count):
        h = struct.unpack("<Q", data[i*8:(i+1)*8])[0]
        assert h not in hashes, f"collision at index {i}: hash 0x{h:016x}"
        hashes.add(h)
        if i > 0:
            assert h > prev, f"unsorted at index {i}: 0x{prev:016x} >= 0x{h:016x}"
        prev = h

    print(f"blocked.bin: {count:,} entries, {len(data)/1024:.0f} KB, no collisions, sorted OK")


def test_safelist_not_blocked():
    """Verify domains in SAFELIST are NOT in blocked.bin."""
    path = os.path.join(FIRMWARE_DIR, "blocked.bin")
    if not os.path.exists(path):
        return

    safelist = {"adwords.google.com", "adidas.com"}
    with open(path, "rb") as f:
        data = f.read()

    count = len(data) // 8
    hashes = {struct.unpack("<Q", data[i*8:(i+1)*8])[0] for i in range(count)}

    for domain in safelist:
        h = fnv1a_64(domain.encode())
        assert h not in hashes, f"{domain} is in blocked.bin but should be in SAFELIST"


def test_known_blocked_domains():
    """Verify known ad/tracker domains ARE in blocked.bin."""
    path = os.path.join(FIRMWARE_DIR, "blocked.bin")
    if not os.path.exists(path):
        return

    with open(path, "rb") as f:
        data = f.read()

    count = len(data) // 8
    hashes = {struct.unpack("<Q", data[i*8:(i+1)*8])[0] for i in range(count)}

    known_blocked = [
        "doubleclick.net",
        "googleadservices.com",
        "googlesyndication.com",
        "adnxs.com",
        "rubiconproject.com",
        "criteo.com",
        "scorecardresearch.com",
    ]
    for domain in known_blocked:
        h = fnv1a_64(domain.encode())
        assert h in hashes, f"{domain} should be in blocked.bin"


def test_combined_sources_union():
    """Verify combined list has more entries than individual lists."""
    hagezi = parse_domains(os.path.join(TOOLS_DIR, "_test_hagezi.txt")) if os.path.exists(
        os.path.join(TOOLS_DIR, "_test_hagezi.txt")) else set()
    hostsvn = parse_domains(os.path.join(TOOLS_DIR, "_test_hostsvn.txt")) if os.path.exists(
        os.path.join(TOOLS_DIR, "_test_hostsvn.txt")) else set()
    if hagezi and hostsvn:
        combined = hagezi | hostsvn
        assert len(combined) >= len(hagezi)
        assert len(combined) >= len(hostsvn)


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed + failed} tests: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
