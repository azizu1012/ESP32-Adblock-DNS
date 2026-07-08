import serial, time
ser = serial.Serial("COM3", 115200, timeout=3)
for _ in range(50):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
ser.read_all()

# First kill any running threads/server
ser.write(b"\x02\x02\x02")
time.sleep(0.2)
ser.read_all()

# Read config.py content
ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(b"with open('config.py') as f: print(f.read())\n")
ser.write(b"\x04")
time.sleep(2)
res = ser.read_all().decode("utf-8", errors="ignore")
print(res[:2000])
ser.close()
