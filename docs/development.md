# Development

## Prerequisites

- Python 3.10+
- `pyserial` (for serial uploading)
  ```bash
  pip install pyserial
  ```

## Project Structure

```text
├── firmware/         # ESP32 MicroPython source code
│   ├── boot.py       Entry point & main loop
│   ├── dns.py        DNS proxy, Bloom Filter checking, and GCT thread
│   ├── server.py     Web server, API endpoints, and streaming upload
│   ├── stats.py      Rolling query statistics and persistence
│   ├── wifi.py       WiFi connection and AP manager
│   ├── config.py     JSON configuration load/save
│   ├── ddns.py       No-IP DDNS updater
│   └── blocked.bin   1.2MB compiled Blocked Bloom Filter
├── tools/
│   ├── process_blocked.py       Compile blocklists into Bloom Filter bin
│   ├── generate_blocked_bin.ps1 Automated download, compilation, and WiFi push
│   └── upload_serial.py         Optimized serial Python code uploader
├── tests/
│   └── test_core.py             15 unit tests
└── docs/
    ├── architecture.md          Pipeline layers, Bloom Filter, GCT mechanics
    ├── api.md                   API Reference
    └── development.md           This file
```

## Running Tests

```bash
python tests/test_core.py
```

Tests verify:
- FNV-1a 64-bit hashing correctness (deterministic, avalanche properties).
- Domain parsing (hosts format, AdGuard format, plain domains).
- Subdomain deduplication (5 edge cases including deep nesting).
- `blocked.bin` integrity (size alignment, footer extraction, and byte order).
- SAFELIST domains are bypassed successfully.
- Known blacklisted domains are blocked correctly.

## Regenerating blocked.bin

```bash
# Automated: download lists, generate, and prompt to upload via WiFi
powershell -f tools/generate_blocked_bin.ps1

# Manual compilation:
python tools/process_blocked.py <input_dir> <output_dir>
```

## Uploading to ESP32

### 1. Serial (Python Code Only - 5s)
Use the optimized serial uploader script to push the Python codebase over serial:
```bash
python tools/upload_serial.py COM3
```

### 2. WiFi (blocked.bin Only - 2s)
Always upload `blocked.bin` over WiFi. Uploading it over serial is slow and discouraged.
```bash
curl -X POST -T firmware/blocked.bin http://<ESP32_IP>/api/upload
curl -X POST http://<ESP32_IP>/api/reboot
```

## Architecture Notes

- **Zero Memory Allocation on DNS Queries**: `blocked.bin` lookups use a pre-allocated static 64-byte buffer to avoid triggering the garbage collector on the main DNS query loop.
- **Self-Healing**: If a domain is blocked by the Bloom Filter but is actually clean, GCT verification audits it in the background and dynamic-whitelists it temporarily.
- **IPv6 AAAA Queries**: Intercepted and returned as `::` (16 zero bytes) to prevent client delays when AAAA queries fail to resolve.
- **Hardware Specs**: The ESP32-D0WD-V3 has 2 cores @ 240 MHz, ~520 KB SRAM (GC heap configured to ~132 KB), and 4 MB raw flash (2 MB LittleFS partition).
