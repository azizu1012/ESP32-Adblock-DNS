# Architecture

## Blocking Pipeline

Each DNS query passes through five layers. The first match wins. Each query reports which layer handled it (displayed on the web dashboard).

```text
Local Bypass (.local/.arpa) ➔ Static SAFELIST ➔ Dynamic Safelist (GCT) ➔ Heuristics ➔ Keywords ➔ Blocked Bloom Filter
```

### 1. Local Network Bypass
`dns.py:231-233` — Bypasses blocking checks entirely for domains ending in `.local` (mDNS) or `.arpa` (Reverse DNS & Service Discovery). This ensures local devices (printers, Chromecast, AirPlay) discover each other with zero latency and zero CPU load on the ESP32.
Returns `(False, None)`.

### 2. Static SAFELIST
`dns.py:236-237` — Tuple of whitelisted domains. Checked first using exact matching via `domain in SAFELIST`.
Returns `(False, None)`.

### 3. Dynamic Safelist (GCT)
`dns.py:239-246` — Thread-safe dictionary containing whitelisted domains rescued by the **Graduated Consensus Trust (GCT)** daemon. If the domain is within its probation lifetime, the query is passed. If the client queries a domain in this list more than 30 times in 1 minute, it is instantly demoted (removed from the safelist) to prevent abuse.
Returns `(False, None)`.

### 4. Heuristics
`dns.py:248-256` — Checks if the first label of the domain starts with `ad` followed by an empty suffix, `s`, a number, or `s` + number.
Returns `(True, "heuristic")`.
- *Matches*: `ads.example.com`, `ad12.example.com`
- *Misses*: `adventure.example.com`

### 5. Keywords
`dns.py:258-261` — Scans domain labels for known tracking keywords (`telemetry`, `analytics`, `doubleclick`, etc.).
Returns `(True, "keyword")`.

### 6. Blocked Bloom Filter (BBF)
`dns.py:263-267` — Last resort. Performs a single 64-byte read from `blocked.bin` to check membership in the Blocked Bloom Filter. If all 8 mapped bits inside the retrieved block are set to `1`, the domain is blocked.
Returns `(True, "hash")`.

---

## Blocked Bloom Filter (BBF) Design

To fit 230K+ domains into the ESP32's tiny 2MB filesystem with zero RAM index overhead, we use a **Blocked Bloom Filter**:

1.  **Block Partitioning**: The filter bitmap is divided into **18,750 blocks** of **64 bytes (512 bits)** each, totaling exactly 1,200,000 bytes.
2.  **FNV-1a 64-bit Hashing**: The domain is hashed using the 64-bit FNV-1a algorithm:
    -   The 32 MSBs of the hash select the block index: `block_idx = h_high % 18,750`.
    -   The 32 LSBs of the hash (`h_low`) are used as the seed for bit position mapping.
3.  **Double Hashing**: Using the Kirsch-Mitzenmacher technique, 8 orthogonal bit positions inside the 512-bit block are mapped using:
    `bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512` (for $i$ from 0 to 7).
4.  **Single Read Seek**: The ESP32 seeks directly to `block_idx * 64` and reads 64 bytes into a pre-allocated buffer (`f.readinto(self._bloom_buf)`). This achieves under **1ms lookup time** with zero memory allocation.
5.  **Domain Count**: The exact number of blocked domains is written as a 4-byte packed integer at the end of `blocked.bin` (total file size: 1,200,004 bytes).

---

## Graduated Consensus Trust (GCT)

GCT is an automated self-healing layer designed to bypass false positives in upstream blocklists:

-   **Consensus Verification Queue**: When a domain triggers a Bloom Filter block, it is added to a thread-safe verification queue. A background thread processes queries asynchronously without blocking user DNS queries.
-   **Consensus Check**: The worker queries **Google DNS (8.8.8.8)** and checks if all three public adblocking DNS providers (**AdGuard, Control D, Mullvad**) agree the domain is clean.
-   **Graduated TTL Promotion**:
    -   *Level 0*: 5 minutes whitelisting.
    -   *Level 1*: 1 hour whitelisting.
    -   *Level 2*: 24 hours whitelisting.
    -   Each time a domain is queried after its TTL expires, it undergoes a recheck. If it passes, it is promoted to the next level. If it fails, it is immediately evicted.
-   **Suspicious Activity Demotion**: If a whitelisted domain is queried more than 30 times in 1 minute, it is demoted to prevent malware from abusing the whitelisting mechanism.

---

## Memory & Streaming Optimizations

-   **Garbage Collection (GC)**: MicroPython's heap is limited to ~132KB. The web server (`server.py`) and DNS proxy (`dns.py`) frequently call `gc.collect()` to free discarded objects.
-   **Streaming File Upload**: The `/api/upload` endpoint streams incoming files directly to LittleFS in 1KB chunks and runs `gc.collect()` every 8KB, allowing memory-safe transfers of files larger than the entire available RAM.
-   **Locking**: A lock (`_thread.allocate_lock()`) ensures thread safety between the Web Server thread (`server.py`) and the main DNS thread (`dns.py`) when modifying statistics or the dynamic safelist.
