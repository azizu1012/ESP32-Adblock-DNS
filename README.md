# ESP32 AdBlocker DNS

Network-wide ad/tracker blocker running on ESP32 with MicroPython.

## Features

- **230K unique blocked domains** — HaGeZi Multi PRO + HostsVN, subdomain-deduplicated
- **Zero collision** — FNV-1a **64-bit** hash binary search — no false positives
- **Live dashboard** — dark theme, KPI cards, donut chart, recent/top queries
- **Laag** — 4 blocking layers: SAFELIST → heuristic (ad.*) → keyword → hash
- **Persistent stats** — 7-day rolling window with per-day cleanup
- **WiFi Manager** — static IP / DHCP / AP setup mode with auto-assign
- **No-IP DDNS** — optional dynamic DNS (12h interval)
- **BOOT button** — hold 3s for factory reset
- **LED heartbeat** — blinks every 5s; flash on block
- **HTTP upload** — update blocked.bin without serial

## Quick Start

```bash
# 1. Flash MicroPython to ESP32
esptool.py --chip esp32 --port COM3 erase_flash
esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 firmware.bin

# 2. Upload firmware (serial)
python tools/upload_fix.py

# 3. Open http://192.168.4.1 — configure WiFi
# 4. Generate + upload blocklist
powershell -f tools/generate_blocked_bin.ps1
curl --data-binary @firmware/blocked.bin http://192.168.1.234/api/upload
curl -X POST http://192.168.1.234/api/reboot
```

## Hardware

| Component | Spec |
|-----------|------|
| MCU | ESP32-D0WD-V3 (dual-core 240 MHz, **no PSRAM**) |
| Flash | 4MB chip (2MB filesystem) |
| RAM | ~520KB total (GC heap ~134KB) |
| LED | GPIO 2 (active high) |
| BOOT | GPIO 0 (pull-up) |

## Project Structure

```
firmware/      → MicroPython code for the ESP32
tools/         → blocked.bin generator + uploader
tests/         → 15 unit tests (hash, dedup, parse, integrity)
docs/          → architecture, API, development guide
```

## Further Reading

- [Architecture](docs/architecture.md) — blocking pipeline, hash choice, dedup
- [API Reference](docs/api.md) — all endpoints with examples
- [Development Guide](docs/development.md) — setup, tests, building

## License

MIT
