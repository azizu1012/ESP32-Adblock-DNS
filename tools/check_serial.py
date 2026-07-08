import serial, time

ser = serial.Serial("COM3", 115200, timeout=2)
time.sleep(2)
data = ser.read_all().decode("utf-8", errors="ignore")
print(data[:2000] if len(data) > 2000 else data)
ser.close()
