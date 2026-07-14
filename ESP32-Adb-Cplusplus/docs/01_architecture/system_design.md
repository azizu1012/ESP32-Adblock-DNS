# ESP32 AdBlocker Architecture

This document details the internal architecture, memory management, and optimizations that allow a massive 230K+ domain blocklist to run efficiently on an ESP32 with only ~132KB of available RAM.

---

## 1. DNS Blocking Pipeline

Each DNS query passes through five specialized layers. The first match wins, and the query is resolved or blocked immediately.

```text
[Incoming DNS Query]
       │
       ▼
 1. Local Bypass (.local, .arpa) ──(Match)──▶ [ALLOW: Zero Latency]
       │
    (No Match)
       │
       ▼
 2. Static Safelist ───────────────(Match)──▶ [ALLOW: Essential Domain]
       │
    (No Match)
       │
       ▼
 3. Dynamic Safelist (GCT) ────────(Match)──▶ [ALLOW: If < 30 req/min]
       │                                     (Abuse > 30) ──▶ [Demote from Safelist]
    (No Match)
       │
       ▼
 4. Heuristics (ad12.*, ads.*) ────(Match)──▶ [BLOCK: Heuristic]
       │
    (No Match)
       │
       ▼
 5. Keywords (telemetry, etc.) ────(Match)──▶ [BLOCK: Keyword]
       │
    (No Match)
       │
       ▼
 6. Blocked Bloom Filter ──────────(Match)──▶ [BLOCK: Hash Match]
       │
    (No Match)
       │
       ▼
[Resolve Upstream DNS]
```

### Layer Details
1. **Local Network Bypass**: Bypasses checks for `.local` (mDNS) and `.arpa` (Reverse DNS). Ensures smart-home devices communicate with zero CPU overhead.
2. **Static Safelist**: Exact string matching for a predefined tuple of essential domains.
3. **Dynamic Safelist (GCT)**: Thread-safe dictionary of domains rescued by the background Consensus Trust daemon. Includes automatic abuse protection (demotion if >30 requests/minute).
4. **Heuristics**: Checks if the first label starts with `ad` followed by an empty string, `s`, or numbers (e.g., `ads.`, `ad12.`).
5. **Keywords**: Scans for known tracking keywords (`telemetry`, `analytics`, etc.).
6. **Blocked Bloom Filter (BBF)**: Performs a single 64-byte flash read to check membership in the 1.2MB bitmap.

---

## 2. Blocked Bloom Filter (BBF) Design

To fit 230K+ domains into the ESP32's tiny 2MB filesystem with **zero RAM overhead**, the system uses a blocked Bloom Filter architecture.

```text
CLIENT               ESP32 (dns_server.cpp)                    FLASH (blocked.bin)
  │                        │                                   │
  ├── Query "ad.com" ─────▶│                                   │
  │                        ├── 1. FNV-1a Hash (64-bit)         │
  │                        ├── 2. Calc block_idx & bit_pos     │
  │                        │                                   │
  │                        ├── 3. f.seek(block_idx * 64) ─────▶│
  │                        ├── 4. f.readinto(buffer, 64) ─────▶│
  │                        │◀── 5. Returns 64 Bytes (512 bits)─┤
  │                        │                                   │
  │                        ├── 6. Check 8 bit positions        │
  │◀── Blocked (0.0.0.0) ──┤                                   │
```

1. **Partitioning**: The 1.2MB filter is divided into **18,750 blocks** of **64 bytes (512 bits)** each.
2. **Double Hashing**: Using the Kirsch-Mitzenmacher technique, 8 orthogonal bit positions inside the 512-bit block are mapped.
3. **Single Read Seek**: The ESP32 seeks directly to the calculated block and reads 64 bytes into a pre-allocated `bytearray(64)`. This achieves `< 1ms` lookup time with **zero memory allocation**.

---

## 3. Web Server & UI Architecture

To serve a rich React-like UI without exhausting the ESP32's limited LwIP socket pool (max 8 concurrent connections), the system employs a **3-Stage Progressive Loading** architecture combined with network-level TCP tuning.

```text
BROWSER                                      ESP32 SERVER
   │                                              │
   │  ================ STAGE 1 ================   │
   │  GET / (Bootstrap Loader)                    │
   ├─────────────────────────────────────────────▶│
   │◀─────────────────────────────────────────────┤
   │  200 OK (index.html, 1KB) [Conn: close]      │
   │                                              │
   │  ================ STAGE 2 ================   │
   │  GET /api/ui/version                         │
   ├─────────────────────────────────────────────▶│
   │◀─────────────────────────────────────────────┤
   │  {"v": "23330-36"}                           │
   │                                              │
   │  [If missing or outdated in localStorage]    │
   │  GET /api/ui (Accept-Encoding: gzip)         │
   ├─────────────────────────────────────────────▶│
   │◀─────────────────────────────────────────────┤
   │  200 OK (app.html.gz, 6KB)                   │
   │  * Browser saves to localStorage *           │
   │                                              │
   │  ================ STAGE 3 ================   │
   │  GET /api/stats (Poll every 3s)              │
   ├─────────────────────────────────────────────▶│
   │◀─────────────────────────────────────────────┤
   │  {"total": 1500...} (~400 bytes)             │
```

### TCP Delayed ACK Mitigation
On Windows and iOS, HTTP clients wait ~200ms to send an ACK for the HTTP Header before accepting the HTTP Body (TCP Delayed ACK). To bypass this latency penalty on the ESP32:
```C++
# BAD: Triggers 200ms latency on Windows/iOS
conn.sendall(header.encode())
conn.sendall(body.encode())

# GOOD: Combined payload, sub-50ms latency
conn.sendall(header.encode() + body.encode())
```

### Global Shared State Caching
To survive aggressive concurrent requests (e.g., F5 spamming or multiple open tabs) and prevent `MemoryError` induced crashes on the main thread:
1. **Byte-level Response Caching**: Heavy endpoints like `/api/stats` generate the JSON exactly once and cache the entire HTTP Response (Header + Body) as raw `bytes` for 1.5 seconds.
2. **Zero-Allocation Distribution**: If 100 requests arrive within the TTL window, the ESP32 pumps the cached binary buffer directly into the LwIP sockets. This requires zero `json.dumps()` overhead and prevents TCP PCB exhaustion without starving the DNS core.

### Smart Lazy Load 2.0 (TCP Exhaustion Mitigation)
Traditional `setInterval()` polling in the browser can rapidly exhaust the ESP32's LwIP TCP Protocol Control Blocks (PCBs) if a user leaves a tab open in the background (causing `ERR_CONNECTION_TIMED_OUT` as delayed FIN packets stack up). 
To prevent this, the UI employs a 4-tier progressive hibernation engine:
1. **1-to-1 Connection Lock**: Uses recursive `setTimeout` that only fires *after* the previous HTTP request has fully resolved. This mathematically guarantees that a single client IP can only consume a maximum of 1 socket at any given moment.
2. **Exponential Backoff**: If a network error occurs (e.g., server resets), the polling interval exponentially backs off (3s -> 6s -> 12s -> 24s -> 30s) to prevent client spamming during the ESP32's boot sequence.
3. **Throttled AFK Detection**: Tracks user mouse/keyboard interaction via a 1s-throttled event listener. 
   - 0-1 mins AFK: 3s polling.
   - 1-3 mins AFK: 10s polling.
   - 3-5 mins AFK: 30s polling.
4. **Deep Hibernation**: If the tab is hidden (via `visibilitychange`) OR the user is AFK for over 5 minutes, the polling timer is completely destroyed (`clearTimeout`). The browser consumes 0 CPU and the ESP32 is completely freed from UI processing. The UI instantly wakes up and resumes polling the moment the user interacts with the page again.

---

## 4. Graduated Consensus Trust (GCT)

GCT is an automated self-healing layer designed to bypass false positives in upstream blocklists without user intervention.

1. **Consensus Queue**: When a domain triggers the BBF, it's added to a background queue.
2. **Polling**: A background thread queries Google DNS against AdGuard, Control D, and Mullvad. If the adblockers agree the domain is clean, it is whitelisted.
3. **Graduated TTL**:
   - *Level 0*: 5 minutes whitelisting.
   - *Level 1*: 1 hour whitelisting.
   - *Level 2*: 24 hours whitelisting.

---

## 5. Memory Optimizations & Resilience

- **Garbage Collection (GC)**: The MicroC++ heap is strictly limited. The web server and DNS proxy manually invoke `gc.collect()` at strategic intervals.
- **Strict RAM Pruning**: Real-time traffic statistics (`stats.recent` and `stats.top`) are ruthlessly pruned to a maximum length of 30-50 items to guarantee abundant heap space. Compression (e.g., DEFLATE) is intentionally avoided to prevent memory spiking (buffer allocation) and GC thrashing.
- **WiFi Resilience & Uptime Integrity**: IoT environments suffer from frequent packet loss and momentary WiFi drops. Instead of abruptly rebooting the ESP32 upon WiFi loss, the firmware implements a **60-second Non-Blocking Grace Period**. It patiently waits for the network to self-heal without interrupting the core loop or resetting the device's persistent Uptime metrics.
- **Streaming Uploads**: The `/api/upload` endpoint streams incoming binary files to LittleFS in 1KB chunks and runs `gc.collect()` every 8KB. This prevents `MemoryError` when uploading the 1.2MB blocklist.
- **Defensive TCP Accept Loop**: The server implements an outer `try-except` loop to catch `ENOBUFS` or `MemoryError` when clients spam requests. It backs off for 100ms and recovers the socket, preventing background thread death.

---

## 5.5 Hardware UX (LED State Machine)

The ESP32 uses its single onboard blue LED as a non-blocking asynchronous state machine to visually communicate the device's real-time health and network activity to the user without sacrificing CPU performance.

1. **Emergency/Boot (Random Strobe)**: If the core DNS loop crashes or fails to tick for > 3 seconds, or the device is actively booting, the LED strobes randomly like an emergency light. This completely overrides all other behaviors.
2. **Heartbeat (Lub-Dub)**: A background timer continuously executes a double-pulse heartbeat ("Lub-Dub") every 2-4 seconds. This assures the user the device is alive, even when idle.
3. **LAN Activity (20ms Pulse)**: Every permitted DNS query instantly interrupts the heartbeat sleep cycle and triggers a rapid 20ms pulse, simulating an Ethernet port activity light.
4. **Blocked Warning (300ms Dark)**: If a query is blocked by the ad-blocker, the LED immediately powers off for 300ms, providing a distinct visual "kill" feedback.

This state machine operates concurrently via `utime.ticks_ms()`, meaning the heartbeat and LAN activity happen perfectly in parallel without the need for strict idle-time periods.

---

## 6. DNS Upstream Optimization (The Triad Strategy)

To maintain high availability and low latency despite ISP throttling, router reboots, or DNS server outages, the ESP32 employs a three-pronged "Triad" self-healing optimization strategy, combined with seamless background transitions.

### 6.1 The Triad Triggers
1. **Periodic Maintenance (2 Hours)**: 
   - Every 2 hours, the ESP32 proactively measures the latency of top global DNS providers (1.1.1.1, 8.8.8.8, 9.9.9.9, etc.) along with the local DHCP-assigned DNS. It locks onto the fastest one to adapt to long-term BGP routing shifts.
2. **Reactive Congestion Control (RTT > 85ms)**: 
   - An Exponential Moving Average (EMA) tracks the Round-Trip Time (RTT) of every successful query.
   - If the EMA RTT stays above 85ms (and at least 2 minutes have passed since the last optimization), the ESP32 detects network congestion and immediately hunts for a better server.
3. **Fail-Fast Dead-Peer Detection (5 Consecutive Timeouts)**: 
   - If a DNS upstream completely drops packets or goes offline, the RTT algorithm cannot update (since it only measures successful queries).
   - A background garbage collector (`_cleanup_pending_queries`) tracks queries older than 2000ms. If 5 queries timeout consecutively without a single successful response in between, the ESP32 declares the upstream "dead" and immediately failovers.

### 6.2 Seamless Dual-Core Transitions (Zero-Downtime)
When any of the Triad triggers fire, the ESP32 executes the DNS optimization using its Dual-Core architecture:
- **Background Worker**: The `optimize_upstream` function is offloaded to a background RTOS thread. This thread performs blocking socket pings (`_measure_rtt`) across 5-6 servers for ~1.5 seconds.
- **Uninterrupted Main Loop**: During this 1.5s window, the main thread continues resolving DNS queries using the *old* upstream IP. Because DNS is connectionless (UDP), this works perfectly.
- **Atomic Swap**: Once the background thread identifies the new optimal server, it atomically overwrites `self.upstream_ip`. The very next query received by the main loop is instantly routed to the new server, while responses from the old server (still in transit) are gracefully accepted and returned to the client. This guarantees a 0ms interruption to the user's internet experience.

---

## 7. Codebase Modularization (Monkey Patching)

To maintain a clean and maintainable codebase without incurring memory penalties on the ESP32, the firmware utilizes a unique **Direct Modularization** pattern via Monkey Patching. 

```C++
# In dns_bloom.py
def attach(cls):
    cls._get_bloom_bit = _get_bloom_bit
    cls.is_blocked_bloom = is_blocked_bloom

# In dns_server.cpp
import dns_bloom
dns_bloom.attach(DNSServer)
```

- **Avoids God Files**: Large classes like `DNSServer` and `WebServer` are split into multiple smaller files (`dns_bloom.py`, `dns_gct.py`, `server_api.py`, etc.).
- **Zero RAM Overhead**: Instead of using deep object-oriented inheritance (which creates large RAM footprints per instance), the `attach()` method binds functions directly to the main class namespace at compile time. 
- **Preserves `self` Context**: Functions act seamlessly as native methods, preserving full access to `self` state like `self.lock` or `self.stats`.

---

## 8. Micro-Optimizations (Global-to-Local Binding)

Because MicroC++ interprets code on a relatively slow microcontroller (160MHz - 240MHz), dictionary lookups in tight loops (like the `poll()` function that runs thousands of times per second) can degrade performance.

To squeeze maximum performance out of the ESP32 without changing logic:
1. **Tick Lookups**: Functions like `time.ticks_ms` or `struct.unpack` require two dictionary lookups (first finding `time` in globals, then `ticks_ms` in `time`'s attributes).
2. **Local Caching**: The firmware binds these frequently used global functions to module-level local variables (`_ticks_ms = time.ticks_ms`). 
3. **Result**: This Global-to-Local binding yields a measurable ~15-20% speedup inside the `poll()` execution path, allowing the DNS server to handle higher concurrent QPS (Queries Per Second) without saturating the CPU.
