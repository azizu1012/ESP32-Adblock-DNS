# API Reference

The web server runs on port 80. All POST bodies are `application/x-www-form-urlencoded` or JSON (for `/api/config/wifi`). Responses are JSON.

The dashboard polls `/api/stats` every 3 seconds to fetch live metrics.

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
    ["google.com", false, "", 5, ""],
    ["legit-site.com", false, "", 1, "safelist"]
  ],
  "top": [
    {"d": "doubleclick.net", "c": 47, "g": "tracking"},
    {"d": "scorecardresearch.com", "c": 23, "g": "tracking"}
  ],
  "flash_free": 640000,
  "flash_total": 2097152,
  "flash_chip": 4194304,
  "blocklist_entries": 230003,
  "cpu_freq": 240,
  "core_count": 2
}
```

### Fields:
- `recent[][2]` — Category string (empty if passed).
- `recent[][3]` — Age in seconds since the query occurred.
- `recent[][4]` — Blocking layer name (`"safelist"`, `"heuristic"`, `"keyword"`, `"hash"`, or `""`).
- `flash_free` — Free filesystem bytes (increased by 640KB due to Blocked Bloom Filter savings).
- `flash_total` — Total filesystem bytes.
- `flash_chip` — Raw chip flash size.
- `blocklist_entries` — Number of entries mapped inside the Bloom Filter (read from the footer).
- `cpu_freq` — CPU frequency in MHz.
- `core_count` — Number of CPU cores.

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
