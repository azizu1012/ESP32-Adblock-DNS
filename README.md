<div align="center">
  <h1>🛡️ ESP32 AdBlocker DNS</h1>
  <p><b>A high-performance, network-wide ad and tracker blocker built for MicroPython on the ESP32.</b></p>

  <p>
    <a href="https://micropython.org"><img src="https://img.shields.io/badge/MicroPython-1.22+-blue.svg?logo=micropython" alt="MicroPython"></a>
    <a href="#"><img src="https://img.shields.io/badge/Hardware-ESP32-red.svg" alt="Hardware"></a>
    <a href="#"><img src="https://img.shields.io/badge/Domains-230K+-success.svg" alt="Domains"></a>
  </p>
</div>

---

ESP32 AdBlocker is a lightweight DNS sinkhole designed to run entirely on a low-cost ESP32 microcontroller. It blocks ads, trackers, and telemetry across your entire home network using a highly optimized Bloom Filter and progressive Web UI.

## ✨ Key Features

- **Massive Blocklist**: Blocks **230,000+** unique domains (HaGeZi + HostsVN) using a 1.2MB Blocked Bloom Filter (BBF).
- **Sub-Millisecond Resolution**: Domain lookup takes `< 1ms` with zero dynamic RAM allocation, directly from flash.
- **Autonomous Self-Healing**: Uses **Graduated Consensus Trust (GCT)** to automatically whitelist false positives by polling upstream adblockers.
- **Ultra-Fast Web UI**: A beautiful, 3-stage progressive loading dashboard with Gzip compression and TCP latency mitigation.
- **OTA Updates**: Stream and update the 1.2MB blocklist over WiFi in under 20 seconds.

> 📖 **Read the full technical breakdown in our [Architecture Reference](docs/architecture.md)**.

## 🚀 Quick Start

### 1. Flash MicroPython
Flash MicroPython v1.22+ to your ESP32:
```bash
esptool.py --chip esp32 --port COM3 erase_flash
esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 firmware.bin
```

### 2. Upload Firmware
Upload the project files via serial (takes ~5 seconds):
```bash
python tools/upload_serial.py COM3
```

### 3. Generate & Upload Blocklist
Generate the binary blocklist locally and upload it to the ESP32 over WiFi:
```powershell
# Compile blocked.bin
powershell -f tools/generate_blocked_bin.ps1

# Upload via API
curl -X POST -T firmware/blocked.bin http://<ESP32_IP>/api/upload

# Reboot to apply
curl -X POST http://<ESP32_IP>/api/reboot
```

## 🛠️ Hardware Requirements

- **MCU**: ESP32-D0WD-V3 (Dual-core 240 MHz, no PSRAM required)
- **Flash**: 4MB chip (2MB LittleFS partition)
- **RAM**: ~132KB GC heap is sufficient

## 📚 Documentation

Explore the `docs/` folder for in-depth information:
- [Architecture & Optimizations](docs/architecture.md)
- [REST API Reference](docs/api.md)
- [Development & Testing Guide](docs/development.md)
