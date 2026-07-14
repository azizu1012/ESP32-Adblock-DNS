import serial, threading, requests, time
s = serial.Serial('COM3', 115200, timeout=1)
out = ''
def read_serial():
    global out
    end = time.time() + 5
    while time.time() < end:
        out += s.read(100).decode('utf-8', errors='ignore')
t = threading.Thread(target=read_serial)
t.start()
time.sleep(1)
try:
    requests.get('http://192.168.1.234/api/ui', timeout=3)
except Exception as e:
    print(f'Req err: {e}')
t.join()
print('SERIAL OUTPUT:')
print(out)
