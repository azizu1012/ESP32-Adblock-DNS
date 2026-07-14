# ESP32 AdBlocker DNS Agent Guide

## Dual-Environment Architecture
The project is split into two isolated domains:
1. **`ESP32-Adb-Cplusplus/` [PRIMARY / PRODUCTION]**: The high-performance ESP-IDF C++ implementation. Uses FreeRTOS, LwIP raw sockets, and `mmap` over SPIFFS. This is the main target for all new features and bug fixes.
2. **`ESP32-Adb-Python/` [LEGACY / PROTOTYPE]**: The legacy MicroPython implementation. Contains Python scripts (`.py`) uploaded via serial. Preserved for reference and R&D.

Do NOT mix logic, commands, or toolchains between these two folders.

---

## 1. [PRIMARY] C++ (ESP-IDF) Guidelines

### Developer Commands & Toolchain
- **Environment Setup**: You must use the locally isolated ESP-IDF toolchain. Before running any `idf.py` commands, set the tools path and export the environment:
  ```powershell
  $env:IDF_TOOLS_PATH="D:\AI_Projects\ESP32-Side-PRJ\ESP32-Adb-Cplusplus\.espressif"
  .\esp-idf\export.ps1
  ```
- **Build / Flash / Monitor**: `idf.py build`, `idf.py -p COM3 flash monitor` from inside the `ESP32-Adb-Cplusplus/` folder.
  - **CRITICAL HARDWARE QUIRK (COM3)**: Due to CP2102 USB driver buffer overflows and LDO hardware limitations on this specific board, flashing a large payload (like the 1.5MB SPIFFS) at the default `460800` baud rate will cause a silent memory corruption and lead to a `POWERON_RESET` loop at runtime. **You MUST ALWAYS flash this board at a slow baud rate: `idf.py -p COM3 -b 57600 flash`.**
- **Dependencies**: Managed via `idf_component.yml`.
- **VSCode Source Control**: `build/` and `.espressif/` are ignored. 

### C++ Architecture & Quirks
- **FreeRTOS Dual-Core**: 
  - `dns_server_task` MUST be pinned to Core 0 (Network priority).
  - `web_server_task` MUST be pinned to Core 1 (App priority).
- **Thread Safety**: Any modification to shared variables (like total_queries, active_clients) MUST acquire `stats_mutex` via `xSemaphoreTake(stats_mutex, portMAX_DELAY)`.
- **Memory Mapping (mmap)**: The 1.2MB `blocked.bin` Bloom Filter is mapped directly from SPIFFS to virtual memory via VFS. Do NOT attempt to read it into a dynamically allocated buffer. Use `mapped_data` pointer arithmetic.
- **cJSON**: JSON serialization for the API is handled by `cJSON`. Always remember to call `cJSON_Delete(root)` to avoid Memory Leaks.
- **Hardware Timers**: Uptime calculation uses `esp_timer_get_time()` (in microseconds). Do NOT use standard `time()` as it will jump upon NTP synchronization.
- **Crash Logging**: On boot, the system checks `esp_reset_reason()`. If an unexpected crash occurs (Panic, WDT, Brownout), the reason is appended to `/spiffs/crash.log`. Always check this log to determine *what* caused a restart.

---

## 2. [LEGACY] Python (MicroPython) Guidelines

### Developer Commands & Toolchain
- **Virtual Environment**: Always use the local virtual environment: `& ".venv/Scripts/python.exe"` (from workspace root).
- **Run Tests**: `& ".venv/Scripts/python.exe" ESP32-Adb-Python/tests/test_core.py`

### Operational Gotchas (Crucial for MicroPython)
- **Interrupting the Loop**: Send Ctrl+C (`\x03`) multiple times to stop the running script before writing files.
- **Watchdog Timer (WDT)**: 30s hardware WDT. Blockages over 30s trigger a reboot.
- **Garbage Collection (GC)**: Heap is ~134KB. `gc.collect()` must be executed frequently, especially in loop iterations.
- **NTP Sync & Uptime Overflow**: Do NOT use `time.time()`. Always use native `utime.ticks_ms()`.
- **LED Heartbeat & IRQ Constraints**: Do NOT use hardware Timer callback for complex heartbeat patterns, it causes silent memory allocation errors. Must run on its own thread.
- **TCP Delayed ACK Penalty**: Concatenate the HTTP header and the first chunk of the body in a single `socket.sendall()` to bypass the 200ms ACK penalty on Windows/iOS.

---

## 3. Shared Architecture & UI Quirks

- **Upload blocked.bin**: `blocked.bin` is 1.2MB. **Do NOT upload blocked.bin over serial**. Always upload it over WiFi via a POST request to `/api/upload`. **CRITICAL**: The chunk buffer in the HTTP upload handler MUST be allocated on the Heap (`malloc`), not the Stack. The Web Server task only has 8KB of stack; using local stack arrays will cause an immediate `Stack Overflow`.
- **Byte-level API Caching**: Heavy JSON endpoints like `/api/stats` MUST implement a 1.5-second TTL cache for the raw output string. Re-generating the `cJSON` tree on every request causes severe Heap fragmentation and will crash the server under heavy polling or F5 spamming.
- **HTTP Caching (ETag & 304 Not Modified)**: Static HTML files (`index.html`) must use ETag caching. When the browser sends `If-None-Match`, immediately respond with `304 Not Modified` to prevent Flash read overhead.
- **3-Stage Progressive Web Loading & GZIP**: DO NOT serve a large UI HTML file directly. Architecture requires: (1) 1KB Bootstrap loader (`index.html`), (2) Version check (`/api/ui/version`), (3) Gzip-compressed bundle (`app.html.gz`) cached in browser `localStorage`.
  - **Tooling**: After modifying `ESP32-Adb-Python/firmware/web/app.html`, you MUST run `python ESP32-Adb-Python/tools/compress_ui.py` to generate the new `app.html.gz` before flashing.
- **Web UI TCP Exhaustion & Smart Polling (Lazy Load)**: Traditional `setInterval()` causes TCP PCB exhaustion. UI MUST implement Context-Aware Lazy Loader: (1) Recursive `setTimeout`, (2) Listen to `visibilitychange` to halt polling, (3) Throttled intervals (10s -> 30s) when AFK, (4) Deep hibernate (0 polling) after 5 minutes AFK.
- **DNS Blocking Layers**: Static SAFELIST → Dynamic Safelist (GCT) → heuristic (ad.*) → keyword → Blocked Bloom Filter.
- **Blocked Bloom Filter (BBF)**: Fixed 1.2MB bitmap. Lookups use a pre-allocated buffer (Python) or mmap pointer (C++).
- **Graduated Consensus Trust (GCT)**: Auditing thread queries AdGuard, Control D, Mullvad, Google DNS. If 3/4 agree it's clean, whitelist temporarily with graduated TTL (5 mins -> 1 hr -> 24 hrs).
- **IPv6 AAAA Queries**: Intercepted at layer 4 and returned as `::` (16 zero bytes) using binary response formatting.
