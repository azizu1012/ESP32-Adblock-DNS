# ESP-IDF C++ Development Guide

This guide covers how to build, flash, and maintain the C++ version of the ESP32 AdBlocker.

## Prerequisites

1. Install **ESP-IDF v5.2+** on your system.
2. The project contains a local isolated ESP-IDF environment at `.espressif/` and a virtual environment.

## 1. Environment Activation

Before running any builds, you must activate the local ESP-IDF environment in your terminal (PowerShell example):
```powershell
$env:IDF_TOOLS_PATH="D:\AI_Projects\ESP32-Side-PRJ\ESP32-Adb-Cplusplus\.espressif"
.\esp-idf\export.ps1
```

## 2. Building the Firmware

To compile the C++ source code, FreeRTOS, and the LwIP network stack into a single binary:
```powershell
idf.py build
```
This will generate `esp32_adblock_dns.bin` in the `build/` directory.

## 3. SPIFFS Filesystem Image

The Web Interface (`app.html.gz`, `setup.html`) must be flashed to the SPIFFS data partition. The build system is configured via `CMakeLists.txt` to automatically invoke `spiffsgen.py` to pack the `/firmware/web/` directory into a binary image (`spiffs.bin`) during the standard build process.

## 4. Flashing to ESP32

Connect your ESP32 via USB. To flash the compiled firmware, partition table, and SPIFFS image:
```powershell
idf.py -p COM3 flash
```
*(Replace `COM3` with your actual serial port)*.

## 5. Serial Monitor

To view debug logs (ESP_LOGI, ESP_LOGE) from the running C++ application:
```powershell
idf.py -p COM3 monitor
```
Press `Ctrl + ]` to exit the monitor.

## 6. Updating the Adblock Database (`blocked.bin`)

Do **NOT** flash `blocked.bin` over Serial because 1.2MB takes >3 minutes.
Instead, use the included PowerShell script from the C++ toolchain:
```powershell
# Navigate to the tools directory
cd ../ESP32-Adb-C++/tools

# Run the generator and provide the ESP32's IP when prompted
.\generate_blocked_bin.ps1
```
The script will download the latest AdGuard/HostsVN lists, compile them into the binary Bloom Filter format, and HTTP POST them to the C++ server via `/api/upload` in under 20 seconds.
