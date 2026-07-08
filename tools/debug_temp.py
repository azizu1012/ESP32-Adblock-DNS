import serial, time

ser = serial.Serial("COM3", 115200, timeout=2)
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.5)

# Interrupt
for _ in range(25):
    ser.write(b"\x03"); time.sleep(0.08)
time.sleep(0.5)
ser.read_all()

code = """
import esp32
raw = esp32.raw_temperature()
print("raw_temperature:", repr(raw))
print("type:", type(raw))
# Try alternative: maybe it returns something else
import machine
adc = machine.ADC(machine.Pin(34))
adc.atten(machine.ADC.ATTN_11DB)
print("adc34:", adc.read())
"""

ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(code.encode("utf-8"))
ser.write(b"\x04")
time.sleep(1)
res = ser.read_all().decode("utf-8", errors="ignore")
ser.write(b"\x02")
time.sleep(0.1)
print(res)

# Also check help(esp32)
ser.write(b"\r\x01")
time.sleep(0.3)
ser.read_all()
ser.write(b"import esp32; help(esp32)\n".encode("utf-8"))
time.sleep(0.5)
res = ser.read_all().decode("utf-8", errors="ignore")
print(res)

ser.close()
