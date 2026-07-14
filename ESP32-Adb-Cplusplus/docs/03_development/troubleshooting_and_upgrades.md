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
- **Challenge**: When uploading C++ or HTML files larger than 12KB over raw REPL (`boot.py`, `web_server.cpp`, `index.html`), transmitting the file as a single line command overflowed the ESP32's internal UART buffer, leading to random data truncation and boot syntax errors (`SyntaxError: invalid syntax`).
- **Solution**: Refactored the serial uploader `tools/upload_serial.py` to upload files in **512-byte binary chunks** with raw command feedback verification. This completely solved data truncation issues.

### B. Aggressive Browser Caching & BLK Badges
- **Challenge**: The absence of caching HTTP headers caused browsers to cache the old `index.html` template. When the API was upgraded to return category lists (e.g. `['analytics']` or `['ads', 'tracking']`), the cached JS template failed to map the list variables to `catMap`, falling back to rendering default `BLK` badges.
- **Solution**: Added `Cache-Control: no-cache, no-store, must-revalidate` HTTP headers to all JSON stats endpoints and HTML streaming routines in `web_server.cpp`, enforcing clean loads on browser visits.

### C. NTP Time Sync & Uptime Calculation Overflow
- **Challenge**: The uptime counter in `stats.py` relied on a fallback `ticks_ms` implementation using `time.time() * 1000` when imported from `time`. Upon connecting to WiFi, the ESP32 synchronized its system clock with NTP, causing a massive time leap of 26 years. This sudden jump caused an `OverflowError` in MicroC++'s 31-bit integer space during `ticks_diff()` calculations, rendering the uptime output as a static `0h 0m 0s`.
- **Solution**: Replaced the library imports in `stats.py` to use `utime` instead of `time`. The native `utime.ticks_ms()` and `utime.ticks_diff()` functions use the ESP32's hardware-level tick counters which tick continuously from boot, completely immune to NTP network time adjustments. A robust PC fallback was maintained to prevent tests from failing locally.

### D. MicroC++ Hardware Timer IRQ Memory Allocation Limits
- **Challenge**: Attempting to implement a complex, randomized double-blink (lub-dub) LED heartbeat by re-initializing hardware timers (`timer.init()`) inside a timer callback function caused a silent crash of the timer. MicroC++ hardware timer callbacks run in a strict Interrupt Request (IRQ) context where dynamic memory allocation is forbidden. Re-initializing the timer inside the callback context violates this rule, causing the timer to halt silently without raising console tracebacks.
- **Solution**: Decoupled the heartbeat from hardware timers. The heartbeat logic is now run in a separate background thread (`led_heartbeat_thread`) using `_thread.start_new_thread()` and standard `time.sleep()`. This is completely safe, does not allocate memory in IRQ contexts, and ensures the main DNS loop remains 100% non-blocking. Single-shot indicator blinks (`blink_off()`) for blocked DNS queries remain safe to use on hardware timers as they are initialized from the main thread outside IRQ context.

### E. Web Server Memory Exhaustion via Cache Bypass (DDoS)
- **Challenge**: Rapidly refreshing (F5 spamming) or Hard Reloading (`Ctrl+F5`) the web interface creates multiple parallel TCP connection requests without `If-None-Match` caching headers. In MicroC++'s single-threaded context, streaming large static HTML templates (like `app.html.gz` at 23KB) repeatedly led to heap fragmentation, I/O blockage, and TCP window exhaustion, causing the LwIP network stack to crash (Out-of-Memory).
- **Solution**: Implemented a **Global Token Bucket Rate Limiter** directly inside the Web Server thread (`web_server.cpp`). The server tracks a global request counter bounded to a 1-second window. If the volume exceeds 15 requests/sec, it immediately drops the sockets and returns `HTTP/1.1 429 Too Many Requests`. This prevents Flash read loops and saves RAM.

### F. Silent OOM Leaks in Statistics Dictionaries
- **Challenge**: The dictionaries `self.top` (tracks blocked domains) and `self.client_ips` in `stats.py` were historically unbounded. If a malicious user or script queried thousands of unique random subdomains (e.g., `ad1.com`, `ad2.com`), the dictionary would grow infinitely, inevitably consuming the tiny 130KB heap and causing a fatal `MemoryError`.
- **Solution**: Implemented **Hard Boundaries and Eviction Policies** in `stats.py`. `self.top` is strictly capped at 200 entries (evicting the lowest count domain if full). `self.client_ips` is capped at 50 entries (evicting the oldest timestamp). This guarantees bounded RAM usage under all attack vectors.

### G. UI CSS Grid & Flexbox Overflow on Mobile Devices
- **Challenge**: On small mobile screens, the page was stretching beyond `100vw`, creating an ugly blank white/black space on the right side of the screen. This occurred because CSS Grid containers (`.gc`) and Flexbox items (like the search `<input>`) default to `min-width: auto`. This means they refuse to shrink below the physical intrinsic length of long truncated domains. Furthermore, the UI would look fine on initial load but "break out" after a few seconds when JavaScript dynamically injected the Top/Recent domains. The injected nested flex containers inside `#listR` and `#listT` also lacked `min-width: 0`, and the Whitelist button (`⊕`) was improperly nested inside the same `text-overflow: ellipsis` span, causing bounding failures.
- **Solution**: 
  1. Enforced `min-width: 0;` and `overflow: hidden;` on all main Grid cards (`.gc`), and applied `min-width: 0` to the flex `<input>` search bar. 
  2. Added `min-width: 0` to all dynamically injected flex containers in `app.html` (`renderRecentList` and `renderTop`).
  3. Extracted the `whitelistHtml` button out of the text span into its own `flex-shrink: 0` container. 
  This overrides the default minimum width dynamically, allowing the grid items to shrink and forcing internal long domain texts to cleanly truncate via `text-overflow: ellipsis`, keeping the dashboard perfectly bounded to the screen width permanently.

### H. Codebase Maintainability vs. RAM Overhead (God File Splitting)
- **Challenge**: The `dns_server.cpp` and `web_server.cpp` files had become monolithic "God Files" (over 600 lines each), making maintenance difficult. However, simply modularizing them using standard OOP inheritance (`class DNSServer(DNSBloom, DNSGct)`) would create massive memory overhead on the ESP32 (due to multiple `__dict__` allocations for every inherited class and instance), potentially exhausting the 134KB heap.
- **Solution**: Implemented a **Direct Modularization pattern via Monkey Patching**. Modules like `dns_bloom.py` and `dns_gct.py` define an `attach(cls)` method that binds functions directly to the target class (`DNSServer`) at compile time. This flattened architecture splits the codebase cleanly into small, manageable files while ensuring zero RAM overhead at runtime, as the instantiated object remains a single flat class in memory.
