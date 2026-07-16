# Troubleshooting & Upgrades (C++ ESP-IDF)

This document outlines the major upgrades and operational challenges resolved during the C++ (ESP-IDF) port of the ESP32 AdBlock DNS.

## New Features & Functional Upgrades

- **Native FreeRTOS Dual-Core Architecture**: Shifted from Python's single-thread Global Interpreter Lock (GIL) to a true dual-core FreeRTOS application. The Web Server and WiFi run on Core 0, while the DNS proxy runs fully unblocked on Core 1.
- **Zero RAM Bloom Filter Lookups**: Leverages standard C file I/O (`fopen`, `fseek`, `fread`) to read the 1.2MB Bloom Filter directly from the SPIFFS partition in 64-byte chunks, allowing ultra-fast validation without allocating heap memory.
- **Thread-Safe Telemetry (`StatsTracker`)**: Real-time traffic statistics (Active Clients, Blocked Count, CPU Temp) are synchronized using FreeRTOS Mutexes (`SemaphoreHandle_t`), ensuring no data races or heap corruption.
- **Hardware Temperature Polling**: Uses the ESP32 ROM `temprature_sens_read()` to fetch internal CPU temperature natively without depending on heavy external drivers.

## Operational Challenges & Solutions

### A. HTTP Header Overflow (`Header fields are too long`)
- **Challenge**: The default ESP-IDF `esp_http_server` configuration restricts the maximum HTTP request header length to a very small size (typically 512 bytes). Modern web browsers sending multiple cookies and `Accept-Encoding` headers exceeded this limit, causing the server to immediately reject the connection and the web UI to break.
- **Solution**: Increased `CONFIG_HTTPD_MAX_REQ_HDR_LEN` to `4096` in `sdkconfig.defaults`. This allows large headers to pass through to the `web_server.cpp` component seamlessly.

### B. Float Precision Artifacts in JSON (Temperature)
- **Challenge**: Storing CPU temperature as an IEEE 754 float in C++ led to formatting artifacts when serialized via `cJSON` (e.g., `53.9000015258789°C`).
- **Solution**: Removed float calculations from the backend. The `StatsTracker` multiplies the value and stores it as a fixed-point integer (e.g., `539` for `53.9°C`). The frontend formats it neatly, keeping the JSON payloads small and precise.

### C. Active Clients Integer Underflow
- **Challenge**: The Active Clients counter in `StatsTracker` dropped to 1 or exhibited bizarre behavior because the eviction logic decremented the counter improperly when purging stale IPs.
- **Solution**: Fixed the eviction mapping and array management to ensure atomic increments and decrements via Mutex locking.

### D. Delayed Uptime & Watchdog Resets
- **Challenge**: The initial ESP-IDF implementation included a heavy 20-minute blocking delay for DNS upstream checks on startup, which starved the FreeRTOS idle task and could trigger hardware watchdog resets.
- **Solution**: Refactored the `DNS_Optimizer` task to use an initial 5-second asynchronous delay, followed by a continuous 5-minute loop utilizing non-blocking `vTaskDelay`. This keeps the system responsive immediately after boot.

### E. LwIP TCP Exhaustion & Hibernation
- **Challenge**: Similar to the Python version, polling the `/api/stats` endpoint via standard `setInterval()` without backoff logic would drain the LwIP TCP Protocol Control Blocks (PCBs) if users abandoned background tabs.
- **Solution**: Implemented a recursive timeout and Context-Aware Lazy Loader in the frontend that stops polling entirely if the tab is hidden (`visibilitychange`), preserving the ESP-IDF socket pool strictly for active clients and incoming DNS traffic.

### F. Crash Logger Memory Leak & Offline Time Sync
- **Challenge**: The system initially dropped crash logs (Panic, WDT) if it couldn't sync NTP time within 60 seconds (common when powered by unstable sources with no WiFi). Fixing this by appending `[TIME NOT SYNCED]` introduced a severe edge case: reading thousands of unsynced log lines into a dynamic `std::vector` during log rotation on the next boot caused a heap exhaustion (OOM) Death Loop.
- **Solution**: 
  1. Implemented a 60-second guard rail (`timeinfo.tm_year >= (2020 - 1900)`) to safely tag offline crashes without dropping them.
  2. Modified the `rotate_crash_logs()` parser to safely skip time-parsing on `[TIME NOT SYNCED]` strings.
  3. Enforced a strict 50-line maximum cap (`valid_lines.size() <= 50`) on the RAM vector during rotation, instantly purging the oldest entry. This protects the 150KB FreeRTOS heap from unbounded growth and ensures complete immunity to offline crash loops.
