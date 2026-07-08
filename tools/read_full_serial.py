import serial, time
ser = serial.Serial("COM3", 115200, timeout=1)
time.sleep(3)
data = b""
for i in range(50):
    try:
        d = ser.read(100)
        if d: data += d
    except: pass
    time.sleep(0.2)
ser.close()
text = data.decode("utf-8", errors="replace")
print(text[-2000:])
