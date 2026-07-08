# Development

## Prerequisites

- Python 3.10+
- `pyserial` (for upload tool)
  ```bash
  pip install pyserial
  ```

## Project Structure

```
├── firmware/         # ESP32 MicroPython code
│   ├── boot.py       Entry point
│   ├── dns.py        DNS proxy + blocking logic
│   ├── server.py     Web server + API
│   ├── stats.py      Query statistics
│   ├── wifi.py       WiFi connection manager
│   ├── config.py     Config read/write
│   ├── ddns.py       No-IP DDNS updater
│   └── blocked.bin   Generated hash file (230K entries)
├── tools/
│   ├── process_blocked.py       Build blocked.bin from lists
│   └── generate_blocked_bin.ps1 Download + generate (Windows)
├── tests/
│   └── test_core.py             15 unit tests
└── docs/
    ├── architecture.md          Blocking pipeline, hash, dedup
    ├── api.md                   API reference
    └── development.md           This file
```

## Running Tests

```bash
python tests/test_core.py
```

Tests verify:
- FNV-1a 64-bit correctness (deterministic, avalanche, collision-free on sample)
- Domain parsing (hosts format, AdGuard format, plain)
- Subdomain dedup (5 edge cases including deep nesting)
- blocked.bin integrity (sorted, aligned, no duplicate hashes)
- SAFELIST domains are not blocked
- Known ad/tracker domains ARE blocked

## Regenerating blocked.bin

```bash
# Download latest lists + generate
powershell -f tools/generate_blocked_bin.ps1

# Or manually:
# 1. Place .txt blocklist files in a temp directory
# 2. Run:
python tools/process_blocked.py <input_dir> <output_dir>
```

## Uploading to ESP32

### Serial (first time or recovery)

Dùng Thonny IDE hoặc `rshell`/`ampy` để upload từng file lên ESP32:

```bash
# Ví dụ với ampy
ampy --port COM3 put firmware/boot.py
ampy --port COM3 put firmware/dns.py
ampy --port COM3 put firmware/stats.py
ampy --port COM3 put firmware/server.py
ampy --port COM3 put firmware/wifi.py
ampy --port COM3 put firmware/config.py
ampy --port COM3 put firmware/ddns.py
ampy --port COM3 put firmware/blocked.bin
```

### HTTP (blocked.bin update only)

```bash
# Upload via curl (replace IP with your ESP32's address)
curl --data-binary @firmware/blocked.bin http://192.168.1.234/api/upload
curl -X POST http://192.168.1.234/api/reboot
```

## Blocklist Sources

| Source | URL | Format | Domains |
|--------|-----|--------|---------|
| HaGeZi Multi PRO | https://github.com/hagezi/dns-blocklists | AdBlock | ~232K |
| HostsVN | https://github.com/bigdargon/hostsVN | Hosts | ~18K |

## Notes

- The ESP32 has **no PSRAM** — all data comes from flash. blocked.bin is
  binary-searched on flash, never loaded into RAM.
- FNV-1a 64-bit was chosen over 32-bit after collision analysis showed
  ~6 expected collisions at 243K domains.
- Subdomain dedup is safe: if `doubleclick.net` is blocked, every DNS
  query to `*.doubleclick.net` returns `0.0.0.0` anyway.
- IPv6 AAAA queries are intercepted and return `::1` (16 zero bytes).
- The ESP32-D0WD-V3 has 2 cores @ 240 MHz, ~520 KB SRAM (GC heap ~134 KB),
  and 4 MB flash (2 MB LittleFS partition).
- Boot sequence: factory reset check → WiFi connect (30s timeout, static IP
  192.168.1.234) → DNS + web threads → main loop with crash recovery
  (try/except + machine.reset()).
