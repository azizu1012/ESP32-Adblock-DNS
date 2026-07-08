"""Upload firmware files to ESP32 via serial raw REPL."""
import sys, os, time

SYS_PATH = os.path.dirname(os.path.dirname(__file__))
FIRMWARE = os.path.join(SYS_PATH, "firmware")
FILES = ["boot.py", "config.py", "wifi.py", "stats.py", "dns.py", "ddns.py", "server.py"]
WEB_DIR = os.path.join(FIRMWARE, "web")
WEB_FILES = ["index.html", "setup.html"]

try:
    import serial
except:
    os.system(f'"{os.path.join(SYS_PATH, ".venv", "Scripts", "pip")}" install pyserial -q')
    import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
BAUD = 115200


def raw_cmd(ser, cmd, timeout=15):
    """Gửi code qua raw REPL, đợi kết quả."""
    ser.write(cmd.encode())
    ser.write(b"\x04")  # Ctrl+D execute
    ser.flush()
    out = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        b = ser.read(128)
        if b:
            out += b
            if b"OK" in out:
                break
        else:
            time.sleep(0.01)
    return out


def main():
    print(f"Connecting {PORT} @ {BAUD}...")
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(1)
    ser.reset_input_buffer()

    print("Interrupting current program (Ctrl+C)...")
    ser.write(b"\x03")
    time.sleep(0.5)
    ser.write(b"\x03")
    time.sleep(0.5)
    ser.reset_input_buffer()

    print("Entering raw REPL (Ctrl+A)...")
    ser.write(b"\x01")
    time.sleep(0.5)
    prompt = ser.read(1024)
    if b"raw REPL" not in prompt:
        print(f"Warning: Unexpected prompt: {prompt.decode(errors='replace')}")

    ser.write(b"import gc; gc.collect()\r")
    ser.write(b"\x04")
    time.sleep(0.1)
    ser.reset_input_buffer()

    # Upload các file Python
    for fname in FILES:
        path = os.path.join(FIRMWARE, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Strip UTF-8 BOM if PowerShell injected it
        if content.startswith("\ufeff"):
            content = content[1:]
        
        # Ghi file dùng repr()
        safe = repr(content)
        cmd = f"open('{fname}','w').write({safe})"
        print(f"  {fname} ({len(content)} bytes)...", end="", flush=True)
        t0 = time.time()
        res = raw_cmd(ser, cmd)
        dt = time.time() - t0
        
        if b"OK" in res:
            print(f" {dt:.1f}s")
        else:
            print(f" FAIL ({dt:.1f}s): {res.decode(errors='replace')[-100:]}")
        
        # GC
        ser.write(b"gc.collect()\r")
        ser.write(b"\x04")
        time.sleep(0.1)
        ser.reset_input_buffer()

    # Create web/ directory on ESP32 if not exists
    raw_cmd(ser, "import os\ntry:\n    os.mkdir('web')\nexcept:\n    pass")

    # Upload web/index.html and web/setup.html as binary
    for fname in WEB_FILES:
        path = os.path.join(WEB_DIR, fname)
        with open(path, "rb") as f:
            content = f.read()
        safe = repr(content)
        cmd = f"open('web/{fname}','wb').write({safe})"
        print(f"  web/{fname} ({len(content)} bytes)...", end="", flush=True)
        t0 = time.time()
        res = raw_cmd(ser, cmd, timeout=20)
        dt = time.time() - t0
        if b"OK" in res:
            print(f" {dt:.1f}s")
        else:
            print(f" FAIL ({dt:.1f}s): {res.decode(errors='replace')[-100:]}")
        ser.write(b"gc.collect()\r")
        ser.write(b"\x04")
        time.sleep(0.1)
        ser.reset_input_buffer()

    print("\nResetting ESP32 (Ctrl+D)...")
    ser.write(b"\x04")
    time.sleep(0.5)
    # exit raw repl
    ser.write(b"\x02")
    ser.close()
    print("Done!")



if __name__ == "__main__":
    main()
