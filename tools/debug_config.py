import serial, time

ser = serial.Serial("COM3", 115200, timeout=2)
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.5)

for _ in range(25): ser.write(b"\x03"); time.sleep(0.08)
time.sleep(0.5); ser.read_all()

code = """
ip = '192.168.1.234'
status_bg = 'rgba(34,197,94,0.1);border-color:rgba(34,197,94,0.2)' if ip else 'rgba(245,158,11,0.1);border-color:rgba(245,158,11,0.2)'
status_html = ('<span>OK %s</span>' % ip) if ip else '<span>No</span>'
template = '<div style="background:%s">%s</div>' % (status_bg, status_html)
print('TEMPLATE:', template)
"""

ser.write(b"\r\x01")
time.sleep(0.3); ser.read_all()
ser.write(code.encode("utf-8"))
ser.write(b"\x04")
time.sleep(1)
print(ser.read_all().decode("utf-8", errors="ignore"))
ser.close()
