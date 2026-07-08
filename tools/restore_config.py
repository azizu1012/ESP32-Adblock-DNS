import serial, time, json

ser = serial.Serial("COM3", 115200, timeout=3)
time.sleep(1)
ser.read_all()

# Write config
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
time.sleep(0.2)
ser.read_all()

print(res)

if "OK" in res:
    # Reboot
    print("Rebooting...")
    ser.write(b"\x04")
    time.sleep(10)
    data = ser.read_all().decode("utf-8", errors="ignore")
    for l in data.split("\n")[-30:]:
        l = l.strip()
        if l: print(l)

ser.close()
