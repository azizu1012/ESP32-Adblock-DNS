import serial
import time
import sys

def main():
    try:
        ser = serial.Serial('COM3', 115200, timeout=1)
        print("Connected to COM3 at 115200 baud.")
        start_time = time.time()
        while time.time() - start_time < 5:
            line = ser.readline()
            if line:
                print(line.decode('utf-8', errors='replace').strip())
        ser.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
