import serial
import time
import binascii

BASE = "D:\\AI_Projects\\ESP32-Side-PRJ"
FIRMWARE = [
    "boot.py", "config.py", "wifi.py", "stats.py",
    "ddns.py", "dns.py", "server.py",
]


def enter_raw_repl(ser):
    ser.write(b"\r\x01")
    time.sleep(0.3)
    ser.read_all()


def exit_raw_repl(ser):
    ser.write(b"\x02")
    time.sleep(0.1)
    ser.read_all()


def send_text_file(ser, local_path, remote_path):
    print(f"  Sending {remote_path}...")
    with open(local_path, "r", encoding="utf-8") as f:
        content = f.read()
    enter_raw_repl(ser)
    code = f"with open('{remote_path}', 'w') as f: f.write({repr(content)})\n"
    ser.write(code.encode("utf-8"))
    ser.write(b"\x04")
    time.sleep(0.5)
    res = ser.read_all().decode("utf-8", errors="ignore")
    exit_raw_repl(ser)
    if "Traceback" in res:
        print(f"  ERROR: {res}")
    else:
        print(f"  OK")


def send_binary_file(ser, local_path, remote_path):
    print(f"  Sending {remote_path}...")
    enter_raw_repl(ser)
    ser.write(f"f = open('{remote_path}', 'wb')\n".encode("utf-8"))
    ser.write(b"\x04")
    time.sleep(0.2)
    ser.read_all()
    with open(local_path, "rb") as f:
        file_data = f.read()
    chunk_size = 2048
    total = (len(file_data) + chunk_size - 1) // chunk_size
    for i in range(0, len(file_data), chunk_size):
        chunk = file_data[i : i + chunk_size]
        hex_data = binascii.hexlify(chunk).decode("ascii")
        ser.write(f"f.write(bytes.fromhex('{hex_data}'))\n".encode("ascii"))
        ser.write(b"\x04")
        time.sleep(0.02)
        ser.read_all()
        idx = i // chunk_size + 1
        if idx % 20 == 0 or idx == total:
            print(f"    chunk {idx}/{total}")
    ser.write(b"f.close()\n")
    ser.write(b"\x04")
    time.sleep(0.2)
    ser.read_all()
    exit_raw_repl(ser)
    print("  OK")


try:
    import sys
    sys.path.append("C:\\Users\\Azuree\\AppData\\Local\\Temp\\opencode")

    ser = serial.Serial("COM3", 115200, timeout=2)

    print("Hard reset...")
    ser.setDTR(False)
    ser.setRTS(True)
    time.sleep(0.2)
    ser.setRTS(False)
    time.sleep(0.2)

    print("Interrupting...")
    for _ in range(25):
        ser.write(b"\x03")
        time.sleep(0.08)
    res = ser.read_all().decode("utf-8", errors="ignore")
    if ">>>" not in res:
        print("Warning: not in REPL")
    else:
        print("REPL OK")

    for f in FIRMWARE:
        send_text_file(ser, f"{BASE}\\firmware\\{f}", f)
    send_binary_file(ser, f"{BASE}\\data\\blocked.bin", "blocked.bin")

    enter_raw_repl(ser)
    ser.write(b"import os\nprint(os.listdir())\n")
    ser.write(b"\x04")
    time.sleep(1.0)
    print("Files:", ser.read_all().decode("utf-8", errors="ignore"))
    exit_raw_repl(ser)

    print("Rebooting...")
    ser.write(b"\x04")
    time.sleep(2.0)
    print(ser.read_all().decode("utf-8", errors="ignore"))
finally:
    ser.close()
