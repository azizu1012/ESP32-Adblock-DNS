"""Upload firmware code + blocked.bin to ESP32 over serial.

Usage:
  python upload_fix.py [COM_PORT] [FIRMWARE_DIR]

Defaults: COM3, ../firmware (relative to this script)
"""
import serial, time, base64, os, sys

COM_PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
FIRMWARE_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "firmware")

ser = serial.Serial(COM_PORT, 115200, timeout=5)

def repl_connect():
    ser.write(b"\r\x01")
    time.sleep(0.3)
    ser.read_all()

def repl_disconnect():
    ser.write(b"\x02")
    time.sleep(0.1)
    ser.read_all()

def repl_send(text):
    ser.write(text.encode("utf-8"))
    ser.write(b"\x04")
    time.sleep(0.8)
    res = ser.read_all().decode("utf-8", errors="ignore")
    repl_disconnect()
    return res

def send_file(local_name, remote_name):
    path = os.path.join(FIRMWARE_DIR, local_name)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    repl_connect()
    code = f"with open('{remote_name}', 'w') as f: f.write({repr(content)})\n"
    res = repl_send(code)
    ok = "Traceback" not in res
    print(f"  {remote_name}: {'OK' if ok else 'FAIL'}")
    return ok

print("Reset...")
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.2)
print("Interrupt...")
for _ in range(25):
    ser.write(b"\x03"); time.sleep(0.08)
time.sleep(0.5)
ser.read_all()

print("Uploading firmware...")
for name in ["server.py", "stats.py", "dns.py", "boot.py"]:
    send_file(name, name)

bin_path = os.path.join(FIRMWARE_DIR, "blocked.bin")
if os.path.exists(bin_path):
    size_kb = os.path.getsize(bin_path) / 1024
    print(f"\nUploading blocked.bin ({size_kb:.0f} KB)...")

    with open(bin_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode()
    CHUNK = 800
    PASTE_LIMIT = 40000
    total_chunks = (len(b64) + CHUNK - 1) // CHUNK

    repl_connect()
    repl_send("f=open('blocked.bin','wb')\n")

    batch = []
    batch_size = 0
    n = 0
    for i in range(0, len(b64), CHUNK):
        chunk = b64[i:i+CHUNK]
        stmt = f"f.write(ubinascii.a2b_base64('{chunk}'))\n"
        batch.append(stmt.encode())
        batch_size += len(stmt)
        if batch_size >= PASTE_LIMIT:
            repl_connect()
            for s in batch: ser.write(s)
            repl_disconnect()
            n += len(batch)
            print(f"  {n}/{total_chunks} chunks", end="\r")
            batch = []
            batch_size = 0
            time.sleep(0.05)

    if batch:
        repl_connect()
        for s in batch: ser.write(s)
        repl_disconnect()
        n += len(batch)
        print(f"  {n}/{total_chunks} chunks")

    for attempt in range(3):
        repl_connect()
        res = repl_send("f.close();print('OK')\n")
        if "OK" in res:
            print("  blocked.bin: OK")
            break
        print(f"  close attempt {attempt+1} failed")
    else:
        print("  blocked.bin: FAIL")

print("\nReboot...")
ser.write(b"\x04")
time.sleep(6)
data = ser.read_all().decode("utf-8", errors="ignore")
ser.close()
for l in data.split("\n")[-15:]:
    l = l.strip()
    if l: print(l)
