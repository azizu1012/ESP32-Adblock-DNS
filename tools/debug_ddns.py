import serial, time

ser = serial.Serial("COM3", 115200, timeout=2)
ser.setDTR(False); ser.setRTS(True); time.sleep(0.2)
ser.setRTS(False); time.sleep(0.5)

for _ in range(25): ser.write(b"\x03"); time.sleep(0.08)
time.sleep(0.5); ser.read_all()

code = b'''
import socket
s = socket.socket()
s.settimeout(8)
addr = socket.getaddrinfo("www.duckdns.org",80)[0][-1]
s.connect(addr)
body = "GET /update?domains=esp32adblocker&token=af25ae49-bce2-4ca5-b417-8600c2650669 HTTP/1.1\r\nHost: www.duckdns.org\r\nUser-Agent: ESP32\r\nConnection: close\r\n\r\n"
s.sendall(body.encode())
resp = b""
while True:
    try:
        d = s.recv(512)
        if not d: break
        resp += d
    except: break
s.close()
print("RAW:", repr(resp))
print("TEXT:", resp.decode())
'''

ser.write(b"\x01\r")
time.sleep(0.3)
ser.read_all()
ser.write(code)
ser.write(b"\x04")
time.sleep(2)
res = ser.read_all().decode("utf-8", errors="ignore")
print(res)
ser.close()
