# API Reference

The web server runs on port 80. All POST bodies are `application/x-www-form-urlencoded` or JSON (for `/api/config/wifi`). Responses are JSON.

The dashboard polls `/api/stats` every 3 seconds to fetch live metrics.

## `GET /` — Dashboard

Returns the dashboard HTML. Auto-refreshes every 3 seconds with `/api/stats`.

## `GET /api/stats` — Stats JSON

Returns lightweight counters, system metrics, and categorical counts (excluding lists to optimize memory and network footprint).

```json
{
  "total": 1520,
  "blocked": 534,
  "allowed": 986,
  "ratio": 35.1,
  "uptime": 84720,
  "free_ram": 87776,
  "alloc_ram": 38048,
  "total_ram": 125824,
  "last_blocked": "doubleclick.net",
  "categories": {
    "ads": 48,
    "tracking": 32,
    "telemetry": 143,
    "analytics": 41,
    "privacy": 3,
    "malware": 0,
    "experiment": 18
  },
  "flash_free": 640000,
  "flash_total": 2097152,
  "flash_chip": 4194304,
  "blocklist_entries": 230003,
  "cpu_freq": 160,
  "core_count": 2,
  "upstream": "8.8.4.4",
  "upstream_rtt": 35.0,
  "active_clients": 4
}
```

### Fields:
- `flash_free` — Free filesystem bytes.
- `flash_total` — Total filesystem bytes.
- `flash_chip` — Raw chip flash size.
- `blocklist_entries` — Number of entries mapped inside the Bloom Filter.
- `cpu_freq` — CPU frequency in MHz.
- `core_count` — Number of CPU cores.
- `active_clients` — Unique active client IPs in the last 10 minutes (using a dedicated memory dictionary).

## `GET /api/stats/recent` — Recent Queries JSON

Returns the 50 most recent DNS queries.

```json
[
  ["doubleclick.net", true, ["ads", "tracking"], 2, "hash", "192.168.1.43"],
  ["google.com", false, [], 5, "", "192.168.1.174"]
]
```

### Fields:
- Array containing `[domain, is_blocked, categories[], age_in_seconds, layer_name, client_ip]`.

## `GET /api/stats/top` — Top Blocked JSON

Returns the top 10 most blocked domains.

```json
[
  {"d": "doubleclick.net", "c": 47, "g": ["tracking", "ads"]},
  {"d": "scorecardresearch.com", "c": 23, "g": ["tracking"]}
]
```

## `GET /setup` — Setup page

WiFi + No-IP DDNS configuration form.

## `POST /api/upload` — Upload blocked.bin

```text
Content-Type: application/octet-stream
Body: binary file data (raw)

Response: {"ok": true, "message": "Upload OK (1200004 bytes)"}
```

Streams the binary file directly to LittleFS and triggers garbage collection (`gc.collect()`) every 8KB to avoid MemoryError crashes on the ESP32's limited heap. After upload, reboot the device to reload the Bloom Filter.

## `POST /api/reboot` — Soft reboot

```json
{"ok": true, "message": "Rebooting..."}
```

Triggers `machine.reset()` with a 500ms delay.

## `POST /api/config/wifi` — Save config

```json
{
  "ssid": "MyWiFi",
  "password": "secret",
  "noip_user": "user@example.com",
  "noip_pass": "secret",
  "noip_host": "mydomain.no-ip.org"
}
```

Saves configuration details and triggers a reboot.

## `POST /api/config/reset` — Factory reset

Deletes `wifi_config.json` and reboots into Access Point (AP) setup mode.

## `POST /api/config/dhcp` — Switch to DHCP

Clears static IP configurations and reboots to request a DHCP lease.
