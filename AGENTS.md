# ESP32 AdBlocker DNS Agent Guide

## Developer Commands & Toolchain
- **Virtual Environment**: Always use the local virtual environment:
  - Windows: `& ".venv/Scripts/python.exe"`
  - Commands must run from the workspace root `D:\AI_Projects\ESP32-Side-PRJ`.
- **Run Tests**:
  - `& ".venv/Scripts/python.exe" tests/test_core.py`
- **Upload Code**:
  - `& ".venv/Scripts/python.exe" tools/upload_serial.py COM3`

## Operational Gotchas (Crucial for Serial REPL)
- **Interrupting the Loop**: The ESP32 runs a continuous DNS poll loop. Before trying to enter raw REPL (`\x01`) or write files via serial, you **must** send Ctrl+C (`\x03`) multiple times to stop the running script. Otherwise, the port will hang and timeout.
- **Watchdog Timer (WDT)**: The firmware utilizes a 30s hardware watchdog (`machine.WDT`). Any blockages in the main thread for over 30s will trigger a hardware reboot.
- **Garbage Collection (GC)**: The GC heap is limited to ~134KB. `gc.collect()` must be executed frequently, especially in loop iterations and before/after file writes.

## Architecture Quirks
- **Thread Safety**: 
  - The Web server (`server.py`) runs in a separate thread via `_thread.start_new_thread`.
  - The DNS server (`dns.py`) runs on the main thread via `poll()`.
  - All shared statistics are stored in `Stats` (`stats.py`) and **must** acquire `self.lock` (`_thread.allocate_lock()`) during modifications or serialization to prevent heap corruption crashes.
- **DNS Blocking Layers**: Whitelist/blacklist checking goes through: SAFELIST → heuristic (ad.*) → keyword → hash. Each layer has specific logic and exits early.
- **IPv6 AAAA Queries**: Intercepted at layer 4 and returned as `::` (16 zero bytes) using the binary response formatting in `_block_response`.
- **Hashing**: Binary search on `blocked.bin` utilizes 64-bit FNV-1a hashes. Do not use 32-bit hashes as they generate collisions at the current volume (230K+ entries).
