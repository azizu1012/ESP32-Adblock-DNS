# ESP32 AdBlocker DNS

A high-performance, network-wide ad and tracker blocker running on the ESP32 with MicroPython.

## Advanced Features

- **230K+ Unique Blocked Domains** — Compiled from HaGeZi Multi PRO + HostsVN, subdomain-deduplicated down to exactly 230,003 unique entries.
- **Blocked Bloom Filter (BBF)** — Replaces slow binary file searches with a fixed **1.2MB** bitmap (18,750 blocks of 64 bytes). Lookups are performed in **under 1ms** with exactly **one flash read** and **zero dynamic RAM allocation** using a pre-allocated static buffer.
- **Graduated Consensus Trust (GCT)** — An autonomous self-healing framework. When a domain triggers a block, GCT audits it in a background thread using a 3/3 consensus of public DNS upstreams (AdGuard, Control D, Mullvad) against Google DNS. If clean, the domain is whitelisted on a probationary dynamic safelist with graduated trust lifetimes (5 mins ➔ 1 hour ➔ 24 hours).
- **Suspicious Client Demotion** — Actively monitors client query rates on dynamic whitelisted domains. If queries exceed 30 requests/minute, the domain is instantly demoted and locked back into the blacklist to prevent exploit/malware beacons.
- **Local Network Discovery Bypass** — Instantly bypasses blocking and computation for `.local` (mDNS) and `.arpa` (Reverse DNS & Service Discovery) requests to ensure smart-home services (AirPlay, Chromecast, printers) run with zero latency.
- **Dynamic Load-Aware Latency Optimization** — Passive latency measurement rotates upstream DNS to the fastest, lowest-latency responder (Cloudflare, Google, etc.) dynamically.
- **Streaming Web Uploader** — Uploads the 1.2MB `blocked.bin` database over WiFi in under 20 seconds. Memory-safe streaming runs garbage collection (`gc.collect()`) every 8KB to run smoothly on the ESP32's limited 132KB heap.

## Quick Start

### 1. Flash MicroPython to ESP32
```bash
esptool.py --chip esp32 --port COM3 erase_flash
esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 firmware.bin
```

### 2. Upload Python Code (Serial)
```bash
# Uploads Python files in 5 seconds
python tools/upload_serial.py COM3
```

### 3. Generate Blocklist & Upload (WiFi)
```powershell
# 1. Compile blocked.bin locally
powershell -f tools/generate_blocked_bin.ps1

# 2. Upload blocked.bin over WiFi (2 seconds)
curl -X POST -T firmware/blocked.bin http://<ESP32_IP>/api/upload

# 3. Reboot the device
curl -X POST http://<ESP32_IP>/api/reboot
```

## Hardware Specifications

| Component | Spec |
|-----------|------|
| MCU | ESP32-D0WD-V3 (Dual-core 240 MHz, no PSRAM) |
| Flash | 4MB chip (2MB LittleFS partition) |
| RAM | ~520KB total (GC heap configured to ~132KB) |
| LED Indicator | GPIO 2 (blinks every 5s on heartbeat; flashes on DNS block) |
| BOOT Button | GPIO 0 (hold 3s to erase config and factory reset) |

## Project Structure

```text
firmware/      → MicroPython source code running on the ESP32
tools/         → Bloom Filter generator, serial uploader, and compilation scripts
tests/         → Local unit tests validating Bloom Filter, dedup, and FNV-1a logic
docs/          → Deep-dive architectural docs, API specs, and development guides
```

## Further Reading

- [Architecture Reference](docs/architecture.md) — Pipeling, Blocked Bloom Filter, GCT, and memory tuning
- [API Reference](docs/api.md) — REST API endpoints for stats, configs, and uploads
- [Development Guide](docs/development.md) — Local testing and validation workflows
