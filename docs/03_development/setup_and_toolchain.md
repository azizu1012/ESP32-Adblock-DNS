# Setup & Toolchain

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
│   ├── dns.py        DNS proxy and Event Loop
│   ├── dns_bloom.py  Bloom Filter hash & file scanning
│   ├── dns_gct.py    Graduated Consensus Trust daemon
│   ├── dns_upstream.py Upstream RTT measurement & failover
│   ├── server.py     Web server TCP Socket & Core
│   ├── server_api.py JSON API endpoints logic
│   ├── server_static.py HTML streaming and gzip/ETag logic
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
    ├── 01_architecture/
    ├── 02_api/
    ├── 03_development/
    └── 04_reports/
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

## Toolchain Pipeline

The `tools/` directory contains a robust 3-stage automated pipeline to generate the `blocked.bin` database and flash the firmware:

### 1. `generate_blocked_bin.ps1` (Automation Script)
A PowerShell script that automates the downloading of raw text blocklists (HaGeZi Multi PRO and HostsVN) from their respective repositories via `curl`. It handles temporary directories and automatically passes the downloaded files to the Python processor.

### 2. `process_blocked.py` (Data Crunching & Hashing)
A Python script that acts as the core compiler. It reads the raw text blocklists, parses various adblock syntax formats, and strictly deduplicates them (e.g. discarding subdomains if the root domain is already blocked). Finally, it hashes the 230K+ unique domains using the FNV-1a 64-bit algorithm and writes them out into a highly optimized 1.2MB Blocked Bloom Filter file (`blocked.bin`).

### 3. `upload_serial.py` (Firmware Uploader & Optimizer)
A Python script that deploys the codebase to the ESP32 via serial (USB). It safely stops the running DNS script via raw REPL, automatically compresses HTML files (like `app.html`) into `.gz` format to save 75% flash space, and transfers files in safe 512-byte chunks to avoid UART buffer overflows. After the transfer, it automatically resets the ESP32.

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
