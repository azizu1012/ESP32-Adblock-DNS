# ESP32 AdBlocker DNS Agent Guide

## Developer Commands & Toolchain
- **Virtual Environment**: Always use the local virtual environment:
  - Windows: `& ".venv/Scripts/python.exe"`
  - Commands must run from the workspace root `D:\AI_Projects\ESP32-Side-PRJ`.
- **Run Tests**:
  - `& ".venv/Scripts/python.exe" tests/test_core.py`
- **Upload Code**:
  - `& ".venv/Scripts/python.exe" tools/upload_serial.py COM3`

## Operational Gotchas (Crucial for Serial REPL)
- **Interrupting the Loop**: The ESP32 runs a continuous DNS poll loop. Before trying to enter raw REPL (`\x01`) or write files via serial, you **must** send Ctrl+C (`\x03`) multiple times to stop the running script. Otherwise, the port will hang and timeout.
- **Watchdog Timer (WDT)**: The firmware utilizes a 30s hardware watchdog (`machine.WDT`). Any blockages in the main thread for over 30s will trigger a hardware reboot.
- **Garbage Collection (GC)**: The GC heap is limited to ~134KB. `gc.collect()` must be executed frequently, especially in loop iterations and before/after file writes.
- **Upload blocked.bin**: `blocked.bin` is 1.2MB. **Do NOT upload blocked.bin over serial** as it is extremely slow (~3 minutes). Always upload it over WiFi via a POST request to `/api/upload` (e.g. using `curl -X POST -T blocked.bin http://<IP>/api/upload`), which takes under 20 seconds.
- **NTP Sync & Uptime Overflow**: Do NOT use `time.time()` as a fallback for calculating system `uptime` or `ticks_ms` on the ESP32. When the WiFi connects, the ESP32's time will jump from epoch 2000 to the current year 2026 via NTP sync. This sudden 26-year leap creates an integer overflow in `ticks_diff()`, crashing the `uptime` property and defaulting it to `0`. Always use native `utime.ticks_ms()` which counts raw CPU hardware clock ticks independent of wall-clock NTP adjustments.

## Architecture Quirks
- **Thread Safety**: 
  - The Web server (`server.py`) runs in a separate thread via `_thread.start_new_thread`.
  - The DNS server (`dns.py`) runs on the main thread via `poll()`.
  - All shared statistics are stored in `Stats` (`stats.py`) and **must** acquire `self.lock` (`_thread.allocate_lock()`) during modifications or serialization to prevent heap corruption crashes.
- **DNS Blocking Layers**: Whitelist/blacklist checking goes through: Static SAFELIST → Dynamic Safelist (GCT) → heuristic (ad.*) → keyword → Blocked Bloom Filter.
- **Blocked Bloom Filter (BBF)**: Stored as a fixed 1.2MB bitmap inside `blocked.bin` (18750 blocks of 64 bytes). Lookups are performed in a single 64-byte file read using a pre-allocated buffer (`f.readinto(self._bloom_buf)`) to avoid dynamic memory allocation. The exact count of domains is stored as a 4-byte integer footer at the end of the file.
- **Graduated Consensus Trust (GCT)**: An auditing thread (`_verify_worker`) queries three public adblocking DNS servers (AdGuard, Control D, Mullvad) and Google DNS in the background when a local Bloom Filter block triggers. If all three adblockers agree a domain is clean, the domain is whitelisted temporarily on a probationary dynamic safelist with graduated TTL levels (5 mins -> 1 hour -> 24 hours).
- **Suspicious Activity Demotion**: If a domain on the dynamic safelist is queried more than 30 times in 1 minute, it is flagged as suspicious and instantly demoted/kicked out of the safelist.
- **IPv6 AAAA Queries**: Intercepted at layer 4 and returned as `::` (16 zero bytes) using the binary response formatting in `_block_response`.

