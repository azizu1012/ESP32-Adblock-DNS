# API Reference

The web server runs on port 80. All POST bodies are `application/x-www-form-urlencoded`
or JSON (for `/api/config/wifi`). Responses are JSON.

Additional fields (not shown in example below) are added automatically — see the
JSON response for the full set. The dashboard polls `/api/stats` every 3 seconds.

## `GET /` — Dashboard

Returns the dashboard HTML. Auto-refreshes every 3 seconds with `/api/stats`.

## `GET /api/stats` — Stats JSON

```json
{
  "total": 1520,
  "blocked": 534,
  "allowed": 986,
  "ratio": 35.1,
  "uptime": 84720,
  "free_ram": 102400,
  "alloc_ram": 64000,
  "total_ram": 166400,
  "last_blocked": "doubleclick.net",
  "recent": [
    ["doubleclick.net", true, "tracking", 2, "hash"],
    ["google.com", false, "", 5, ""]
  ],
  "top": [
    {"d": "doubleclick.net", "c": 47, "g": "tracking"},
    {"d": "scorecardresearch.com", "c": 23, "g": "tracking"}
  ],
  "flash_free": 102400,
  "flash_total": 1048576,
  "flash_chip": 4194304,
  "blocklist_entries": 230003,
  "cpu_freq": 240,
  "core_count": 2
}
```

Fields:
- `recent[][2]` — category string (empty if passed)
- `recent[][3]` — age in seconds since query
- `recent[][4]` — blocking layer name (`"heuristic"`, `"keyword"`, `"hash"`, or `""`)
- `flash_free` — free filesystem bytes
- `flash_total` — total filesystem bytes
- `flash_chip` — raw chip flash size (typically 4,194,304)
- `blocklist_entries` — number of entries in blocked.bin
- `cpu_freq` — CPU frequency in MHz
- `core_count` — number of CPU cores (2 for ESP32)

## `GET /setup` — Setup page

WiFi + No-IP DDNS configuration form.

## `POST /api/upload` — Upload blocked.bin

```
Content-Type: application/octet-stream
Body: binary file data (raw)

Response: {"ok": true, "message": "Upload OK (1840024 bytes)"}
```

Streaming write to flash; no RAM accumulation. File is written
atomically via `open("blocked.bin", "wb")`. After upload, reboot
for the DNS server to pick up the new blocklist.

## `POST /api/reboot` — Soft reboot

```json
{"ok": true, "message": "Rebooting..."}
```

Triggers `machine.reset()` with 500ms delay.

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

All No-IP fields are optional. On success, saves and reboots.

## `POST /api/config/reset` — Factory reset

Deletes `wifi_config.json`, reboots into AP mode.

## `POST /api/config/dhcp` — Switch to DHCP

Clears static IP config, reboots to obtain DHCP lease.
