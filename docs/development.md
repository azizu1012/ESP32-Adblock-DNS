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

## Architecture Notes

- **Zero Memory Allocation on DNS Queries**: `blocked.bin` lookups use a pre-allocated static 64-byte buffer to avoid triggering the garbage collector on the main DNS query loop.
- **Self-Healing**: If a domain is blocked by the Bloom Filter but is actually clean, GCT verification audits it in the background and dynamic-whitelists it temporarily.
- **IPv6 AAAA Queries**: Intercepted and returned as `::` (16 zero bytes) to prevent client delays when AAAA queries fail to resolve.
- **Hardware Specs**: The ESP32-D0WD-V3 has 2 cores @ 240 MHz, ~520 KB SRAM (GC heap configured to ~132 KB), and 4 MB raw flash (2 MB LittleFS partition).

## Upgrades & Operational Challenges Resolved (July 2026)

### 1. New Features & Functional Upgrades
- **4-Tier Local Domain Classifier**: Implemented a self-contained 4-level domain categorization algorithm directly in firmware:
  1. *Tier 1 (Exact Match)*: Quick dict lookup for high-profile domains (e.g., `doubleclick.net` -> `["ads", "tracking"]`, `settings-win.data.microsoft.com` -> `["telemetry"]`).
  2. *Tier 2 (Prefix Match)*: Matches domain prefixes (e.g., starts with `events.telemetry.` -> `["telemetry"]`).
  3. *Tier 3 (Contains Match)*: Matches keywords inside the domain.
  4. *Tier 4 (Fallback)*: Defaults to `["ads"]` for general blocks.
- **7-Category Multi-tag System**: Expanded from 5 generic groups to 7 specific categories (`ADS`, `TRK`, `TEL`, `ANL`, `PRV`, `MAL`, `EXP`), displayed side-by-side on the dashboard.
- **Interactive Custom Whitelist Management**: Integrated quick-whitelisting `⊕` buttons on the dashboard, alongside a full whitelist editor card and GCT probation list tracker at `/setup` writing directly to `safelist.txt` on flash.
- **Active Clients KPI**: Tracks active querying client IPs over a rolling 10-minute window in memory.
- **Smooth Ticking Uptime**: Implemented local JavaScript clock running at 1s intervals, syncing with authoritative ESP32 system uptime every 3s via AJAX.
- **Bonjour/mDNS/DNS-SD Bypass**: Stripped legacy blocked `.arpa` and `.local` entries from persistent `stats.json` history on startup, ensuring local discovery never breaks or shows up in the blocked logs.
- **Organic Heartbeat LED (Lub-Dub)**: Replaced standard timer blinks with an organic double-blink state machine (Lub-Dub) running asynchronously on a hardware timer callback. Heartbeats are triggered at randomized intervals (4 to 7 seconds) to simulate a living device, while blocked DNS queries blink the LED off for 100ms. This is 100% non-blocking, ensuring zero impact on DNS latency.

### 2. Operational Challenges & Solutions

#### A. UART Input Buffer Overflow
- **Challenge**: When uploading Python or HTML files larger than 12KB over raw REPL (`boot.py`, `server.py`, `index.html`), transmitting the file as a single line command overflowed the ESP32's internal UART buffer, leading to random data truncation and boot syntax errors (`SyntaxError: invalid syntax`).
- **Solution**: Refactored the serial uploader `tools/upload_serial.py` to upload files in **512-byte binary chunks** with raw command feedback verification. This completely solved data truncation issues.

#### B. Aggressive Browser Caching & BLK Badges
- **Challenge**: The absence of caching HTTP headers caused browsers to cache the old `index.html` template. When the API was upgraded to return category lists (e.g. `['analytics']` or `['ads', 'tracking']`), the cached JS template failed to map the list variables to `catMap`, falling back to rendering default `BLK` badges.
- **Solution**: Added `Cache-Control: no-cache, no-store, must-revalidate` HTTP headers to all JSON stats endpoints and HTML streaming routines in `server.py`, enforcing clean loads on browser visits.

#### C. NTP Time Sync & Uptime Calculation Overflow
- **Challenge**: The uptime counter in `stats.py` relied on a fallback `ticks_ms` implementation using `time.time() * 1000` when imported from `time`. Upon connecting to WiFi, the ESP32 synchronized its system clock with NTP, causing a massive time leap of 26 years. This sudden jump caused an `OverflowError` in MicroPython's 31-bit integer space during `ticks_diff()` calculations, rendering the uptime output as a static `0h 0m 0s`.
- **Solution**: Replaced the library imports in `stats.py` to use `utime` instead of `time`. The native `utime.ticks_ms()` and `utime.ticks_diff()` functions use the ESP32's hardware-level tick counters which tick continuously from boot, completely immune to NTP network time adjustments. A robust PC fallback was maintained to prevent tests from failing locally.

#### D. MicroPython Hardware Timer IRQ Memory Allocation Limits
- **Challenge**: Attempting to implement a complex, randomized double-blink (lub-dub) LED heartbeat by re-initializing hardware timers (`timer.init()`) inside a timer callback function caused a silent crash of the timer. MicroPython hardware timer callbacks run in a strict Interrupt Request (IRQ) context where dynamic memory allocation is forbidden. Re-initializing the timer inside the callback context violates this rule, causing the timer to halt silently without raising console tracebacks.
- **Solution**: Decoupled the heartbeat from hardware timers. The heartbeat logic is now run in a separate background thread (`led_heartbeat_thread`) using `_thread.start_new_thread()` and standard `time.sleep()`. This is completely safe, does not allocate memory in IRQ contexts, and ensures the main DNS loop remains 100% non-blocking. Single-shot indicator blinks (`blink_off()`) for blocked DNS queries remain safe to use on hardware timers as they are initialized from the main thread outside IRQ context.

#### E. Web Server OOM Crash under F5 Refresh Spam (HTTP Caching & 304 Not Modified)
- **Challenge**: Rapidly refreshing (F5 spamming) the web interface from one or more browsers creates multiple parallel TCP connection requests. In MicroPython's single-threaded, resource-constrained web server context, opening and streaming large static HTML templates (like `index.html` at 20KB) repeatedly leads to heap fragmentation and Out-of-Memory (OOM) crashes in the server thread, causing the web server to freeze or die.
- **Solution**: Implemented HTTP conditional caching via ETag validation. The server generates a unique ETag string based on the file size and modification time of the requested HTML file. On subsequent requests, the browser sends the `If-None-Match` header. If the ETag matches, the server bypasses flash-reading and data-transmission completely, instantly responding with a tiny 100-byte `304 Not Modified` header. This offloads the UI rendering entirely to the browser cache and reduces CPU/RAM load to negligible levels, making the server extremely resilient to rapid refreshes.
