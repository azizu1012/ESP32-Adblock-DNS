import serial, time

ser = serial.Serial("COM3", 115200, timeout=5)
for _ in range(30):
    ser.write(b"\x03"); time.sleep(0.05)

time.sleep(0.5)
# Clear input buffer
def send(cmd, wait=0.3):
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)

def read_all():
    return ser.read_all().decode("utf-8", errors="replace")

s = read_all()
print("=== Boot === ")
for l in s.split("\n"):
    l = l.strip()
    if l: print(l)

# Turn off AP if on
send("import network, time")
send("ap = network.WLAN(network.AP_IF)")
send("ap.active(False)")

# Init STA with fresh state
send("w = network.WLAN(network.STA_IF)")
send("w.active(False)")
time.sleep(0.5)
send("w.active(True)")

# Scan
send("nets = w.scan()", wait=5)
s = read_all()
print("=== Scan === ")
for l in s.split("\n"):
    l = l.strip()
    if l: print(l)

# Connect
send("w.connect('Dung','12082001')", wait=0.5)
# Wait for connection
for i in range(30):
    time.sleep(0.5)
    send("if w.isconnected(): print('CONNECTED, IP:', w.ifconfig()[0]); break", wait=0.3)
    s = read_all()
    if "CONNECTED" in s:
        print(s)
        break
    if i == 29:
        print("FAILED to connect")
        s = read_all()
        print(s)

ser.close()
