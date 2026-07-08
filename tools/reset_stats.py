import serial, time
import json

ser = serial.Serial("COM3", 115200, timeout=5)
for _ in range(30):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
ser.read_all()

# Reset stats.json
ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
data = {"_ts": 0}
code = f"import json\nwith open('stats.json','w') as f: json.dump({json.dumps(data)},f)\nprint('OK')\n"
ser.write(code.encode("utf-8"))
ser.write(b"\x04")
time.sleep(1)
res = ser.read_all().decode("utf-8", errors="ignore")
ser.write(b"\x02")
time.sleep(0.1)
ser.read_all()
print("Stats reset:", "OK" in res)

# Reboot
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
