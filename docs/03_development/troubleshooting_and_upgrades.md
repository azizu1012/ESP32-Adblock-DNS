# Troubleshooting & Upgrades

This document outlines the major upgrades and operational challenges resolved during the development of the ESP32 AdBlock DNS.

## New Features & Functional Upgrades

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

## Operational Challenges & Solutions

### A. UART Input Buffer Overflow
- **Challenge**: When uploading Python or HTML files larger than 12KB over raw REPL (`boot.py`, `server.py`, `index.html`), transmitting the file as a single line command overflowed the ESP32's internal UART buffer, leading to random data truncation and boot syntax errors (`SyntaxError: invalid syntax`).
- **Solution**: Refactored the serial uploader `tools/upload_serial.py` to upload files in **512-byte binary chunks** with raw command feedback verification. This completely solved data truncation issues.

### B. Aggressive Browser Caching & BLK Badges
- **Challenge**: The absence of caching HTTP headers caused browsers to cache the old `index.html` template. When the API was upgraded to return category lists (e.g. `['analytics']` or `['ads', 'tracking']`), the cached JS template failed to map the list variables to `catMap`, falling back to rendering default `BLK` badges.
- **Solution**: Added `Cache-Control: no-cache, no-store, must-revalidate` HTTP headers to all JSON stats endpoints and HTML streaming routines in `server.py`, enforcing clean loads on browser visits.

### C. NTP Time Sync & Uptime Calculation Overflow
- **Challenge**: The uptime counter in `stats.py` relied on a fallback `ticks_ms` implementation using `time.time() * 1000` when imported from `time`. Upon connecting to WiFi, the ESP32 synchronized its system clock with NTP, causing a massive time leap of 26 years. This sudden jump caused an `OverflowError` in MicroPython's 31-bit integer space during `ticks_diff()` calculations, rendering the uptime output as a static `0h 0m 0s`.
- **Solution**: Replaced the library imports in `stats.py` to use `utime` instead of `time`. The native `utime.ticks_ms()` and `utime.ticks_diff()` functions use the ESP32's hardware-level tick counters which tick continuously from boot, completely immune to NTP network time adjustments. A robust PC fallback was maintained to prevent tests from failing locally.

### D. MicroPython Hardware Timer IRQ Memory Allocation Limits
- **Challenge**: Attempting to implement a complex, randomized double-blink (lub-dub) LED heartbeat by re-initializing hardware timers (`timer.init()`) inside a timer callback function caused a silent crash of the timer. MicroPython hardware timer callbacks run in a strict Interrupt Request (IRQ) context where dynamic memory allocation is forbidden. Re-initializing the timer inside the callback context violates this rule, causing the timer to halt silently without raising console tracebacks.
- **Solution**: Decoupled the heartbeat from hardware timers. The heartbeat logic is now run in a separate background thread (`led_heartbeat_thread`) using `_thread.start_new_thread()` and standard `time.sleep()`. This is completely safe, does not allocate memory in IRQ contexts, and ensures the main DNS loop remains 100% non-blocking. Single-shot indicator blinks (`blink_off()`) for blocked DNS queries remain safe to use on hardware timers as they are initialized from the main thread outside IRQ context.

### E. Web Server Memory Exhaustion via Cache Bypass (DDoS)
- **Challenge**: Rapidly refreshing (F5 spamming) or Hard Reloading (`Ctrl+F5`) the web interface creates multiple parallel TCP connection requests without `If-None-Match` caching headers. In MicroPython's single-threaded context, streaming large static HTML templates (like `app.html.gz` at 23KB) repeatedly led to heap fragmentation, I/O blockage, and TCP window exhaustion, causing the LwIP network stack to crash (Out-of-Memory).
- **Solution**: Implemented a **Global Token Bucket Rate Limiter** directly inside the Web Server thread (`server.py`). The server tracks a global request counter bounded to a 1-second window. If the volume exceeds 15 requests/sec, it immediately drops the sockets and returns `HTTP/1.1 429 Too Many Requests`. This prevents Flash read loops and saves RAM.

### F. Silent OOM Leaks in Statistics Dictionaries
- **Challenge**: The dictionaries `self.top` (tracks blocked domains) and `self.client_ips` in `stats.py` were historically unbounded. If a malicious user or script queried thousands of unique random subdomains (e.g., `ad1.com`, `ad2.com`), the dictionary would grow infinitely, inevitably consuming the tiny 130KB heap and causing a fatal `MemoryError`.
- **Solution**: Implemented **Hard Boundaries and Eviction Policies** in `stats.py`. `self.top` is strictly capped at 200 entries (evicting the lowest count domain if full). `self.client_ips` is capped at 50 entries (evicting the oldest timestamp). This guarantees bounded RAM usage under all attack vectors.

### G. UI Flexbox Overflow on Mobile Devices
- **Challenge**: On small mobile screens, the "Recent Queries" and "Top Blocked" lists overflowed horizontally, stretching the parent container and breaking the responsive layout. This was caused by CSS Flexbox `min-width: auto` default properties refusing to shrink below the physical length of long domains.
- **Solution**: Appended `min-width: 0` to all flex containers wrapping domains with `text-overflow: ellipsis`. This enabled proper truncation and restored the responsive boundaries of the dashboard layout on mobile phones.
