import serial, time

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

def send_file(local, remote):
    with open(BASE + "\\" + local, "r", encoding="utf-8") as f:
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

send_file("stats.py", "stats.py")
send_file("server.py", "server.py")

print("\nReboot...")
ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(b"import machine; machine.reset()\n")
ser.write(b"\x04")
time.sleep(15)
data = ser.read_all().decode("utf-8", errors="replace")
for l in data.split("\n")[-20:]:
    l = l.strip()
    if l: print(l)
ser.close()
