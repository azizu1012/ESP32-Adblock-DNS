# Architecture

## Blocking Pipeline

Each DNS query passes through four layers. The first match wins. Each query
now reports which layer blocked it (displayed as a badge on the dashboard).

```
SAFELIST  →  Heuristic  →  Keyword  →  Hash (blocked.bin)
```

### 1. SAFELIST
`dns.py:22` — Tuple of whitelisted domains. Exact match via `domain in SAFELIST`.  
Always checked first so whitelisted domains skip all blocking.  
Returns `(False, None)`.

### 2. Heuristic (`ad.*` pattern)
`dns.py:97-101` — If the first label starts with `ad` and the suffix is
empty, `s`, a number, or `s` + number, the domain is blocked.  
Returns `(True, "heuristic")`.

Matches: `ads.example.com`, `ad12.example.com`  
Misses: `adventure.example.com` (`ad` prefix but `venture` doesn't match pattern)

### 3. Keyword matching
`dns.py:102-103` — Any label containing known tracking keywords
(`telemetry`, `analytics`, `doubleclick`, etc.) triggers a block.  
Returns `(True, "keyword")`.

### 4. Binary search on blocked.bin
Last resort. Computes FNV-1a 64-bit hash of the domain, binary-searches
the sorted 8-byte entries in `blocked.bin`. Zero collisions guaranteed
for all practical purposes (expected collision rate: 1.4e-9 at 230K entries).  
Returns `(True, "hash")`.

### IPv6 AAAA handling
`dns.py:140-155` — `_block_response()` detects query type by reading bytes
at offset `[offset : offset + 2]`. If `qtype == b"\\x00\\x1c"` (AAAA),
the answer is 16 zero bytes (`::1`). Otherwise it returns `0.0.0.0` (A).

## Hash

**FNV-1a 64-bit** — chosen for speed (no crypto overhead), small code footprint
(3 arithmetic ops per byte), and 64-bit space guarantees.

```python
h = 0xCBF29CE484222325
for b in data:
    h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
```

Compared to 32-bit (6 expected collisions at 243K domains), 64-bit eliminates
false positives entirely.

## Subdomain Deduplication

The `dedup_by_parent()` function removes domains that are subdomains of
another blocked domain (`process_blocked.py:38-44`).  

Example: if both `doubleclick.net` and `ads.doubleclick.net` are in the
blocklist, only `doubleclick.net` is kept because blocking the parent
effectively blocks all subdomains at the DNS level.

At 243,090 unique domains from combined sources, dedup removes 13,087
redundant entries (5.4%), leaving **230,003 hashes**.

## Stats

Stats persist to `stats.json` with a 7-day rolling window.

- Each blocked domain stores `{c: count, d: day_number}`
- On load/save, entries with `day < today - 7` are pruned
- Recent queries: last 100 kept, trimmed to 20 for API response
- Recent tuples: `(domain, blocked_bool, layer_str_or_None, timestamp)`
- Category labels computed on-the-fly via keyword rules (`stats.py:12-31`)
- Stats auto-save every 30s (if dirty). On crash, stats are saved before
  `machine.reset()` (`boot.py:88`).

## Blocking Layer Reporting

Each query result in the `recent` array includes a `layer` field (index 4):
- `"safelist"` — passed safelist (allowed)
- `"heuristic"` — blocked by ad.* heuristic
- `"keyword"` — blocked by keyword match
- `"hash"` — blocked by binary search on blocked.bin
- `""` — not blocked (passed through)

## Dashboard

The live dashboard (`GET /`) includes:
- **KPI cards**: Total, Blocked, Allowed, Block Ratio, Blocked Domains count
- **Donut chart**: Blocked vs Allowed
- **System Info**: RAM (GC heap) with % usage bar, Flash (FS) with % usage bar,
  CPU freq + core count, CPU temp, uptime, IP address
- **Recent Queries**: last 10 with block/pass badge, category badge, layer badge, timestamp
- **Top Blocked**: top 10 blocked domains with category badge and count bar

## Crash Recovery

`boot.py:74-90` — The main loop is wrapped in `try/except`. On any exception:
1. Print the exception via `sys.print_exception()`
2. Save stats to flash (`stats.save()`)
3. Wait 3 seconds
4. Call `machine.reset()` to reboot

WiFi timeout was increased from 12s to 30s (`wifi.py:46`, `range(60)` at 0.5s interval).

## Hardware Limits

| Parameter | Value |
|-----------|-------|
| MCU | ESP32-D0WD-V3 (rev v3.1) |
| Cores | 2 (Xtensa LX6) |
| CPU freq | 240 MHz |
| SRAM | ~520 KB total (GC heap ~134 KB at runtime) |
| Flash chip | 4,194,304 bytes (4 MB) |
| Filesystem | ~2 MB LittleFS partition |
| PSRAM | None |
| WiFi | 2.4 GHz b/g/n, static IP 192.168.1.234 |

## Filesystem Layout (2 MB partition)

```
~56 KB   firmware (.py files)
~1.8 MB  blocked.bin (230K × 8 bytes)
~20 KB   stats.json (7-day window, typical)
~1 KB    wifi_config.json
-------------------
~1.9 MB  used, ~100 KB free
```
