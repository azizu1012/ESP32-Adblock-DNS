import serial, time
ser = serial.Serial("COM3", 115200, timeout=3)
for _ in range(30):
    ser.write(b"\x03"); time.sleep(0.05)
time.sleep(0.5)
ser.read_all()

ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(b"import os; s=os.stat('blocked.bin'); print('SIZE:', s[6])\n")
ser.write(b"\x04")
time.sleep(1.5)
res = ser.read_all().decode("utf-8", errors="ignore")
ser.write(b"\x02")
time.sleep(0.2)
ser.read_all()
print(res)
ser.close()
