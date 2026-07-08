import serial, time

ser = serial.Serial("COM3", 115200, timeout=2)

print("Waiting for running ESP32...")
time.sleep(1)
ser.read_all()

# Interrupt main thread
print("Interrupt main loop...")
for _ in range(5):
    ser.write(b"\x03"); time.sleep(0.1)
time.sleep(1)
ser.write(b"\r\n"); time.sleep(0.3)
ser.read_all()

# Enter raw REPL
print("Enter raw REPL...")
ser.write(b"\r\x01")
time.sleep(0.5)
ser.read_all()

code = """import socket, time
try:
  s = socket.socket()
  s.settimeout(5)
  s.connect(('127.0.0.1', 80))
  s.sendall(b'GET /api/stats HTTP/1.0\\r\\nHost: test\\r\\n\\r\\n')
  time.sleep(0.5)
  data = b''
  while True:
    try:
      c = s.recv(4096)
      if not c: break
      data += c
    except: break
  s.close()
  print('GOT:', len(data), 'bytes')
  print(data[:500])
except Exception as e:
  print('LOCALHOST FAIL:', e)

try:
  import network
  ip = network.WLAN(network.STA_IF).ifconfig()[0]
  print('Trying', ip)
  s = socket.socket()
  s.settimeout(5)
  s.connect((ip, 80))
  s.sendall(b'GET /api/stats HTTP/1.0\\r\\nHost: test\\r\\n\\r\\n')
  time.sleep(0.5)
  data = b''
  while True:
    try:
      c = s.recv(4096)
      if not c: break
      data += c
    except: break
  s.close()
  print('GOT:', len(data), 'bytes')
  print(data[:500])
except Exception as e:
  print('IP FAIL:', e)
"""
ser.write(code.encode())
ser.write(b"\x04")
time.sleep(4)
result = ser.read_all().decode("utf-8", errors="ignore")
print("=== RESULT ===")
for l in result.split("\n"):
    if l.strip():
        print(f"  {l.strip()}")

ser.write(b"\x02")
time.sleep(0.1)
ser.close()
