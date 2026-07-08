import serial
import time

ser = serial.Serial("COM3", 115200, timeout=0.5)
ser.reset_input_buffer()
ser.reset_output_buffer()

# Read all available serial data
for _ in range(60):
    try:
        d = ser.read(200)
        if d:
            print(d.decode("utf-8", errors="ignore"), end="")
        else:
            time.sleep(0.5)
    except:
        break

ser.close()
