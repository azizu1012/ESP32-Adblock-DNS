# Architecture

## Blocking Pipeline

Each DNS query passes through four layers. The first match wins.

```
SAFELIST  →  Heuristic  →  Keyword  →  Hash (blocked.bin)
```

### 1. SAFELIST
`dns.py:22` — Tuple of whitelisted domains. Exact match via `domain in SAFELIST`.  
Always checked first so whitelisted domains skip all blocking.

### 2. Heuristic (`ad.*` pattern)
`dns.py:95-98` — If the first label starts with `ad` and the suffix is
empty, `s`, a number, or `s` + number, the domain is blocked.  

Matches: `ads.example.com`, `ad12.example.com`  
Misses: `adventure.example.com` (`ad` prefix but `venture` doesn't match pattern)

### 3. Keyword matching
`dns.py:23-26` — Any label containing known tracking keywords
(`telemetry`, `analytics`, `doubleclick`, etc.) triggers a block.

### 4. Binary search on blocked.bin
Last resort. Computes FNV-1a 64-bit hash of the domain, binary-searches
the sorted 8-byte entries in `blocked.bin`. Zero collisions guaranteed
for all practical purposes (expected collision rate: 1.4e-9 at 230K entries).

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
- Recent queries: last 50 (trimmed to 20 for API response)
- Category labels computed on-the-fly via keyword rules (`stats.py:11-23`)

## Filesystem Layout (2 MB partition)

```
~56 KB   firmware (.py files)
~1.8 MB  blocked.bin (230K × 8 bytes)
~20 KB   stats.json (7-day window, typical)
~1 KB    wifi_config.json
-------------------
~1.9 MB  used, ~100 KB free
```
