import serial, time

ser = serial.Serial("COM3", 115200, timeout=5)
for _ in range(5):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.3)
ser.read_all()

# Soft reboot
ser.write(b"\x04")
time.sleep(12)
data = ser.read_all().decode("utf-8", errors="ignore")
for l in data.split("\n")[-25:]:
    l = l.strip()
    if l: print(l)
ser.close()
