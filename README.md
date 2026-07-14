<div align="center">
  <h1>🛡️ ESP32 AdBlocker DNS</h1>
  <p><b>A high-performance, network-wide ad and tracker blocker built for the ESP32.</b></p>

  <p>
    <a href="#"><img src="https://img.shields.io/badge/C%2B%2B-ESP--IDF-blue.svg?logo=cplusplus" alt="C++ (Production)"></a>
    <a href="#"><img src="https://img.shields.io/badge/Python-MicroPython-yellow.svg?logo=python" alt="Python (Prototype)"></a>
    <a href="#"><img src="https://img.shields.io/badge/Hardware-ESP32-red.svg" alt="Hardware"></a>
    <a href="#"><img src="https://img.shields.io/badge/Domains-230K+-success.svg" alt="Domains"></a>
  </p>
</div>

---

ESP32 AdBlocker is a robust, local DNS sinkhole designed to run entirely on a low-cost ESP32 microcontroller. It acts as the primary DNS server for your home network, intercepting and dropping requests to ads, trackers, and telemetry servers at the network level.

## 🏗️ Project Architecture (Dual-Environment)

This project has evolved through a hybrid engineering philosophy, split into two distinct repositories within this workspace:

1. 🚀 **[ESP32-Adb-Cplusplus (Production)](ESP32-Adb-Cplusplus/)**: 
   The production-ready core written in **C++ using ESP-IDF and FreeRTOS**. It leverages True Dual-Core SMP, Static RAM Allocation, and VFS Memory Mapping to handle `300+ req/sec` with **0% packet loss** and absolute stability.
2. 🧪 **[ESP32-Adb-Python (Prototype)](ESP32-Adb-Python/)**: 
   The legacy **MicroPython** prototype. Used extensively for rapid R&D of the Bloom Filter algorithms, Graduated Consensus Trust (GCT) logic, and the React-based Web UI before porting to C++.

> 💡 **Curious about the differences?** Read our deep-dive technical comparison: [C++ vs Python System Architecture](C_vs_Python_Comparison.md)

---

## ✨ Key Technical Features

- **Massive Blocklist (Bloom Filter)**: Blocks **230,000+** unique domains (HaGeZi + HostsVN) using a highly optimized 1.2MB Bloom Filter.
- **Zero-Allocation Lookups**: In C++, domain lookups map the 1.2MB `.bin` directly from SPIFFS flash to virtual memory via `mmap`. Lookups take `< 1ms` without consuming any heap RAM.
- **Autonomous Self-Healing (GCT)**: Uses **Graduated Consensus Trust** to automatically whitelist false positives by silently polling upstream public adblockers (AdGuard, Control D) when an obscure domain is blocked.
- **True Dual-Core Execution**: The DNS UDP resolver is strictly pinned to **Core 0**, while the HTTP Web Server handles heavy JSON API serialization on **Core 1**, completely eradicating network timeouts.
- **Ultra-Fast Web UI**: A beautiful, responsive dashboard leveraging 3-stage progressive loading (Bootstrap -> Version Check -> `localStorage` Gzip Cache) to bypass embedded server constraints.

---

## 🚀 Getting Started (Production C++)

To deploy the production-ready C++ firmware to your ESP32, follow these steps:

### 1. Requirements
- Standard ESP32 (Dual-Core, 240MHz). No external PSRAM required.
- ESP-IDF v5.2+ installed on your system.

### 2. Build & Flash
Navigate to the C++ project folder and build the firmware:
```bash
cd ESP32-Adb-Cplusplus
idf.py build
idf.py -p COM3 flash monitor
```

### 3. Generate & Upload Blocklist
The 1.2MB blocklist is too large to bake into the binary. It must be generated locally and uploaded via Wi-Fi:
```powershell
# 1. Compile blocked.bin from raw host files
cd ESP32-Adb-Python
powershell -f tools/generate_blocked_bin.ps1

# 2. Upload via API to the ESP32 (Takes ~10 seconds)
curl -X POST -T firmware/blocked.bin http://<ESP32_IP>/api/upload

# 3. Reboot the ESP32 to apply the new VFS mapping
curl -X POST http://<ESP32_IP>/api/reboot
```

---

## 📚 Documentation

Detailed documentation is available inside the `ESP32-Adb-Cplusplus/docs/` folder:
- [System Architecture & Design](ESP32-Adb-Cplusplus/docs/01_architecture/system_design.md)
- [REST API Reference](ESP32-Adb-Cplusplus/docs/02_api/endpoints.md)
- [Setup & Toolchain Guide](ESP32-Adb-Cplusplus/docs/03_development/setup_and_toolchain.md)
- [Benchmark & Performance Reports](ESP32-Adb-Cplusplus/docs/04_reports/benchmark.md)

---

<div align="center">
  <i>"Use Python to save engineers' time. Use C++ to save the CPU's time."</i>
</div>
