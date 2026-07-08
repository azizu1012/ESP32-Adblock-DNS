import serial, time
ser = serial.Serial("COM3", 115200, timeout=3)
time.sleep(1)
print("Sending Ctrl+C...")
for _ in range(20):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
s = ser.read_all().decode("utf-8", errors="ignore")
print(repr(s[-300:]))
ser.close()
