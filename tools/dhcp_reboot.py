import serial, time, json

ser = serial.Serial("COM3", 115200, timeout=3)
for _ in range(25):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
ser.read_all()

config = {"ssid": "Dung", "password": "12082001"}
data = json.dumps(config)

ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
code = f"import json\nwith open('wifi_config.json','w') as f: json.dump({data},f)\nprint('OK')\n"
ser.write(code.encode("utf-8"))
ser.write(b"\x04")
time.sleep(1)
res = ser.read_all().decode("utf-8", errors="ignore")
print("Saved:", "OK" in res)
ser.write(b"\x02")
time.sleep(0.1)
ser.read_all()

print("Rebooting...")
ser.write(b"\x04")
time.sleep(15)
data = ser.read_all().decode("utf-8", errors="ignore")
for l in data.split("\n"):
    l = l.strip()
    if l: print(l)
ser.close()
