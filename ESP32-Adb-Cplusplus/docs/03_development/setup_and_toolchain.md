# Setup & Toolchain (C++ ESP-IDF)

## Prerequisites

- ESP-IDF v5.2 or later
- Python 3.10+ (for ESP-IDF tools and `generate_blocked_bin.ps1`)
- CMake and Ninja (included with ESP-IDF)

## Project Structure

```text
├── components/          # C++ Core Modules
│   ├── dns_server/      # FreeRTOS DNS Proxy & Bloom Filter & Optimizer
│   ├── sys_manager/     # WiFi, LED, StatsTracker & Shared State
│   └── web_server/      # LwIP Web API & SPIFFS Static File Server
├── main/
│   ├── main.cpp         # Entry point (app_main)
│   └── CMakeLists.txt   # Main CMake config
├── esp-idf/             # ESP-IDF SDK (git submodule)
├── build/               # Generated binaries
├── sdkconfig            # ESP-IDF Configuration (LwIP, FreeRTOS, Flash)
├── partitions.csv       # Custom Partition Table (App 1.5MB, SPIFFS 1.5MB)
└── docs/                # Project Documentation
```

## Toolchain Pipeline

The C++ version uses the native ESP-IDF toolchain for compilation, alongside a Python/PowerShell pipeline for generating the blocklist database.

### 1. `generate_blocked_bin.ps1` (Database Generator)
A PowerShell script (borrowed from the Python version) that automates the downloading of raw text blocklists (HaGeZi Multi PRO and HostsVN). It strictly deduplicates them and hashes the 230K+ unique domains using the FNV-1a algorithm into a 1.2MB Blocked Bloom Filter file (`blocked.bin`).

### 2. ESP-IDF `idf.py build` (C++ Compiler)
Compiles the C++ source code into an ELF binary using Xtensa GCC. Also compiles the custom `partitions.csv` and generates the SPIFFS image automatically during the build process (by packing the `../ESP32-Adb-Python/firmware/web/` folder and `blocked.bin` into `spiffs.bin`).

### 3. ESP-IDF `idf.py flash` (Serial Uploader)
Flashes the compiled Bootloader, App binary, Partition Table, and SPIFFS image to the ESP32 via serial (USB) at 57600 baud rate (due to hardware quirks).

## Building and Flashing

### 1. Initial Setup
Open the ESP-IDF Command Prompt (or run `export.ps1` in PowerShell):
```powershell
$env:IDF_TOOLS_PATH="D:\AI_Projects\ESP32-Side-PRJ\ESP32-Adb-Cplusplus\.espressif"
.\esp-idf\export.ps1
```

### 2. Full Build & Flash
Use `idf.py` to compile the firmware and flash it to the ESP32:
```bash
idf.py build flash -p COM3 -b 57600
```
*Note: This command automatically packs the `spiffs.bin` and uploads it alongside the app binary.*

### 3. Serial Monitor
To view the real-time C++ FreeRTOS logs (ESP_LOGI, ESP_LOGE):
```bash
idf.py monitor -p COM3
```

## Regenerating blocked.bin (Over-The-Air)

If you only want to update the blocklist database without recompiling the C++ firmware, you can push the new `blocked.bin` over WiFi:

```bash
# 1. Download and generate new blocked.bin
powershell -f ../ESP32-Adb-Python/tools/generate_blocked_bin.ps1

# 2. Upload to ESP32 via REST API (takes ~2 seconds)
curl -X POST -T ../ESP32-Adb-Python/firmware/blocked.bin http://<ESP32_IP>/api/upload

# 3. Reboot the ESP32 to load the new Bloom Filter into memory
curl -X POST http://<ESP32_IP>/api/reboot
```
