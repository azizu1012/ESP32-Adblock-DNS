# ESP32 AdBlocker DNS

Network-wide ad/tracker blocker running on ESP32 with MicroPython.

## Features

- **243K blocked domains** — HaGeZi Multi PRO + HostsVN
- **~1MB flash footprint** — FNV-1a 32-bit hash binary search
- **Live dashboard** — dark theme, KPI cards, donut chart, recent/top queries
- **Category labels** — telemetry / tracking / ads / malware (keyword-based)
- **Persistent stats** — 7-day rolling window with per-day cleanup
- **WiFi Manager** — static IP / DHCP / AP setup mode
- **No-IP DDNS** — optional dynamic DNS support
- **BOOT button** — hold 3s for factory reset
- **LED heartbeat** — blinks every 5s; flash on block
- **HTTP upload** — update blocked.bin without serial

## Hardware

| Component | Spec |
|-----------|------|
| MCU | ESP32-D0WD-V3 (single-core) |
| Flash | 4MB (2MB filesystem) |
| RAM | ~166KB total (~155KB free) |
| LED | GPIO 2 (active high) |
| BOOT | GPIO 0 (pull-up) |

## Files

```
firmware/
├── boot.py        Entry point — WiFi, threads, heartbeat
├── dns.py         DNS proxy — heuristic + hash blocking
├── server.py      HTTP server — dashboard, API, setup, upload
├── stats.py       Query stats — persist + 7-day cleanup
├── wifi.py        WiFiManager — connect, AP, static IP
├── config.py      ConfigManager — read/write wifi_config.json
├── ddns.py        No-IP DDNS updater (optional)
├── blocked.bin    243K domain hashes (generated)
scripts/
├── DNS_On.bat     Set laptop DNS to ESP32
├── DNS_Off.bat    Restore DHCP DNS
tools/
├── process_blocked.py       Build blocked.bin from blocklists
├── generate_blocked_bin.ps1 Download + generate script
├── upload_fix.py            Serial upload tool
└── ...debug/utility scripts
```

## Setup

### 1. Flash MicroPython

Download latest **ESP32_GENERIC** .bin from [micropython.org](https://micropython.org/download/ESP32_GENERIC/).

```bash
esptool.py --chip esp32 --port COM3 erase_flash
esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 firmware.bin
```

### 2. Upload firmware

```bash
python tools/upload_fix.py
```

The ESP32 boots in AP mode (`ESP32-AdBlocker-Config`). Connect to it, open `http://192.168.4.1`, enter WiFi credentials.

### 3. Update blocklist

```bash
# Generate new blocked.bin
powershell -f tools/generate_blocked_bin.ps1

# Upload via HTTP
curl --data-binary @firmware/blocked.bin http://192.168.1.234/api/upload
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/api/stats` | JSON stats |
| GET | `/setup` | WiFi setup page |
| POST | `/api/upload` | Upload blocked.bin |
| POST | `/api/config/wifi` | Save WiFi config |
| POST | `/api/config/reset` | Factory reset |
| POST | `/api/config/dhcp` | Switch to DHCP |

## Dashboard

Auto-refreshes every 3s. Shows:
- **KPI cards**: total queries, blocked, allowed, ratio
- **Donut chart**: block vs allowed
- **System info**: RAM, CPU temp, uptime, IP
- **Recent queries**: last 10 with BLOCK/PASS + category badge
- **Top blocked**: most-blocked domains (persistent across reboots)

## License

MIT
