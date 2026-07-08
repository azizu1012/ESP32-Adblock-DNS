import serial, time, json

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

send_file("boot.py", "boot.py")

# Write wifi config
config = {"ssid": "Dung", "password": "12082001", "ip": "192.168.1.234", "gateway": "192.168.1.1"}
data = json.dumps(config)
ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
code = f"import json\nwith open('wifi_config.json','w') as f: json.dump({data},f)\nprint('OK: config saved')\n"
ser.write(code.encode("utf-8"))
ser.write(b"\x04")
time.sleep(1)
res = ser.read_all().decode("utf-8", errors="ignore")
ser.write(b"\x02")
time.sleep(0.1)
ser.read_all()
print("  wifi_config:", "OK" if "OK" in res else "FAIL")

# Reboot
print("Reboot...")
ser.write(b"\x04")
time.sleep(12)
data = ser.read_all().decode("utf-8", errors="ignore")
for l in data.split("\n")[-30:]:
    l = l.strip()
    if l: print(l)
ser.close()
