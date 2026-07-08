import serial, time, base64, os

BASE = "D:\\AI_Projects\\ESP32-Side-PRJ\\firmware"
ser = serial.Serial("COM3", 115200, timeout=5)

print("Reset...")
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.2)

print("Interrupt...")
for _ in range(25):
    ser.write(b"\x03"); time.sleep(0.08)
time.sleep(0.5)
ser.read_all()

# First upload text files
def send_file(local, remote):
    with open(os.path.join(BASE, local), "r", encoding="utf-8") as f:
        content = f.read()
    ser.write(b"\r\x01")
    time.sleep(0.3)
    ser.read_all()
    code = f"with open('{remote}', 'w') as f: f.write({repr(content)})\n"
    ser.write(code.encode("utf-8"))
    ser.write(b"\x04")
    time.sleep(0.8)
    res = ser.read_all().decode("utf-8", errors="ignore")
    ser.write(b"\x02")
    time.sleep(0.1)
    ser.read_all()
    ok = "Traceback" not in res
    print(f"  {remote}: {'OK' if ok else 'FAIL'}")
    return ok

print("Uploading code files...")
send_file("server.py", "server.py")
send_file("stats.py", "stats.py")
send_file("dns.py", "dns.py")
send_file("boot.py", "boot.py")

# Upload blocked.bin via chunked base64
bin_path = os.path.join(BASE, "blocked.bin")
if os.path.exists(bin_path):
    size_kb = os.path.getsize(bin_path) / 1024
    print(f"\nUploading blocked.bin ({size_kb:.0f} KB)...")
    
    with open(bin_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode()
    
    # Open file in raw REPL
    CHUNK = 800  # base64 chars per chunk -> ~600 bytes binary
    
    # Use paste mode, but only send ~50KB at a time to fit in RAM
    PASTE_LIMIT = 40000  # paste buffer limit
    
    total_chunks = (len(b64) // CHUNK) + 1
    print(f"  Chunks: {total_chunks}, total b64: {len(b64)} chars")
    
    # We need to write in multiple paste sessions
    # Each paste session: append chunks to the file
    
    # First, open file in raw REPL
    ser.write(b"\r\x01")
    time.sleep(0.3)
    ser.read_all()
    ser.write(b"f=open('blocked.bin','wb')\n")
    ser.write(b"\x04")
    time.sleep(0.5)
    ser.read_all()
    ser.write(b"\x02")
    time.sleep(0.1)
    ser.read_all()
    
    # Send chunks in groups
    batch = []
    batch_size = 0
    n = 0
    for i in range(0, len(b64), CHUNK):
        chunk = b64[i:i+CHUNK]
        stmt = f"f.write(ubinascii.a2b_base64('{chunk}'))\n"
        batch.append(stmt.encode())
        batch_size += len(stmt)
        if batch_size >= PASTE_LIMIT:
            ser.write(b"\r\x01")
            time.sleep(0.3)
            ser.read_all()
            for s in batch:
                ser.write(s)
            ser.write(b"\x04")
            time.sleep(0.3)
            ser.read_all()
            ser.write(b"\x02")
            time.sleep(0.1)
            ser.read_all()
            n += len(batch)
            print(f"  Sent {n}/{total_chunks} chunks ({n*CHUNK}/{len(b64)} chars)", end="\r")
            batch = []
            batch_size = 0
            time.sleep(0.05)
    
    # Last batch
    if batch:
        ser.write(b"\r\x01")
        time.sleep(0.3)
        ser.read_all()
        for s in batch:
            ser.write(s)
        ser.write(b"\x04")
        time.sleep(0.3)
        ser.read_all()
        ser.write(b"\x02")
        time.sleep(0.1)
        ser.read_all()
        n += len(batch)
    
    print(f"\n  Sent {n}/{total_chunks} chunks. Closing file...")
    
    # Close file (separate paste session)
    for attempt in range(3):
        ser.write(b"\r\x01")
        time.sleep(0.3)
        ser.read_all()
        ser.write(b"f.close();print('OK')\n")
        ser.write(b"\x04")
        time.sleep(0.3)
        res = ser.read_all().decode("utf-8", errors="ignore")
        ser.write(b"\x02")
        time.sleep(0.1)
        ser.read_all()
        if "OK" in res:
            print("  blocked.bin: OK")
            break
        print(f"  close attempt {attempt+1} failed, retry...")
    else:
        print("  blocked.bin: FAIL")
        print(res[:200])

print("\nReboot...")
ser.write(b"\x04")
time.sleep(6)
data = ser.read_all().decode("utf-8", errors="ignore")
ser.close()
for l in data.split("\n")[-25:]:
    l = l.strip()
    if l: print(l)
