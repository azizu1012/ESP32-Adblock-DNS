import serial, time, socket, threading

def read_serial(ser, stop):
    buf = ""
    while not stop.is_set():
        try:
            d = ser.read(100)
            if d:
                txt = d.decode("utf-8", errors="ignore")
                print(txt, end="", flush=True)
                buf += txt
            else:
                time.sleep(0.05)
        except:
            break
    return buf

ser = serial.Serial("COM3", 115200, timeout=0.2)
ser.setDTR(False); ser.setRTS(True)
time.sleep(0.2)
ser.setRTS(False)

stop = threading.Event()
reader = threading.Thread(target=read_serial, args=(ser, stop), daemon=True)
reader.start()

# Wait for boot
time.sleep(10)

print("\n\n=== HTTP TEST ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(("192.168.1.234", 80))
    print(">>> TCP Connected")
    s.sendall(b"GET / HTTP/1.1\r\nHost: 192.168.1.234\r\nConnection: close\r\n\r\n")
    time.sleep(2)
    try:
        r = s.recv(4096)
        if r:
            print(f">>> Response: {len(r)} bytes")
            print(r.decode("utf-8", errors="ignore")[:300])
        else:
            print(">>> No data (empty recv)")
    except Exception as e:
        print(f">>> Recv error: {e}")
    s.close()
except Exception as e:
    print(f">>> Connect error: {e}")

time.sleep(1)
print("\n\n=== DONE ===")
stop.set()
time.sleep(0.5)
ser.close()
