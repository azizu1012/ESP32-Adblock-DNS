import serial, time, socket

ser = serial.Serial("COM3", 115200, timeout=2)

print("Hard reset...")
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.2)

# Wait for boot + wait extra for web server thread
print("Waiting for boot...")
time.sleep(8)

# Read serial output
data = ser.read_all().decode("utf-8", errors="ignore")
print("=== SERIAL ===")
for l in data.split("\n"):
    if l.strip():
        print(f"  {l.strip()}")

ser.close()

# Now test from laptop
print("\n=== HTTP TEST ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(("192.168.1.234", 80))
    print("TCP Connected")
    s.sendall(b"GET /api/stats HTTP/1.1\r\nHost: 192.168.1.234\r\nConnection: close\r\n\r\n")
    time.sleep(1.5)
    data = b""
    while True:
        try:
            c = s.recv(4096)
            if not c: break
            data += c
        except: break
    s.close()
    if data:
        print(f"Response: {len(data)} bytes")
        print(data.decode("utf-8", errors="ignore")[:600])
    else:
        print("No response data")
        # Try again with different approach
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.settimeout(10)
        s2.connect(("192.168.1.234", 80))
        s2.sendall(b"GET / HTTP/1.1\r\nHost: 192.168.1.234\r\nConnection: close\r\n\r\n")
        time.sleep(1.5)
        data2 = b""
        while True:
            try:
                c = s2.recv(4096)
                if not c: break
                data2 += c
            except: break
        s2.close()
        if data2:
            print(f"Root response: {len(data2)} bytes")
            print(data2.decode("utf-8", errors="ignore")[:300])
        else:
            print("Root also empty")
except Exception as e:
    print(f"Failed: {type(e).__name__}: {e}")
