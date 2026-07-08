import serial, time
ser = serial.Serial("COM3", 115200, timeout=3)
for _ in range(50):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
ser.read_all()

ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(b"with open('wifi_config.json') as f: print(f.read())\n")
ser.write(b"\x04")
time.sleep(1.5)
res = ser.read_all().decode("utf-8", errors="ignore")
ser.write(b"\x02")
time.sleep(0.2)
print(res[:500])
ser.close()
