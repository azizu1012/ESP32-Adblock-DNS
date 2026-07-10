"""Upload firmware files to ESP32 via serial raw REPL."""
import sys, os, time

SYS_PATH = os.path.dirname(os.path.dirname(__file__))
FIRMWARE = os.path.join(SYS_PATH, "firmware")
FILES = ["boot.py", "config.py", "wifi.py", "stats.py", "dns.py", "dns_bloom.py", "dns_gct.py", "dns_upstream.py", "ddns.py", "server.py", "server_api.py", "server_static.py"]
WEB_DIR = os.path.join(FIRMWARE, "web")
WEB_FILES = ["index.html", "app.html", "setup.html"]

# Auto-compress HTML files with gzip before upload
def ensure_gzip():
    """Nén gzip các file HTML nếu chưa có file .gz hoặc .gz cũ hơn file gốc."""
    import gzip
    compressed = []
    for name in ["app.html", "setup.html"]:
        src = os.path.join(WEB_DIR, name)
        dst = src + ".gz"
        if not os.path.exists(src):
            continue
        # Nén lại nếu .gz không tồn tại hoặc cũ hơn file gốc
        if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
            with open(src, "rb") as f_in:
                data = f_in.read()
            with gzip.open(dst, "wb", compresslevel=9) as f_out:
                f_out.write(data)
            orig = len(data)
            comp = os.path.getsize(dst)
            print(f"  Compressed {name}: {orig:,} -> {comp:,} bytes ({(1-comp/orig)*100:.0f}% smaller)")
        compressed.append(name + ".gz")
    return compressed

try:
    import serial
except:
    os.system(f'"{os.path.join(SYS_PATH, ".venv", "Scripts", "pip")}" install pyserial -q')
    import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
BAUD = 115200


def raw_cmd(ser, cmd, timeout=15):
    """Gửi code qua raw REPL, đợi kết quả.

    MicroPython raw REPL protocol:
      → command + \\x04
      ← OK                (command accepted, starting execution)
      ← [stdout output]
      ← \\x04             (end of stdout)
      ← [stderr/traceback]
      ← \\x04             (end of stderr = execution fully complete)
    We must wait for the second \\x04 to ensure the command finished.
    """
    ser.write(cmd.encode())
    ser.write(b"\x04")  # Ctrl+D execute
    ser.flush()
    out = b""
    t0 = time.time()
    eot_count = 0
    while time.time() - t0 < timeout:
        b = ser.read(128)
        if b:
            out += b
            eot_count += out.count(b"\x04")
            # Two \x04 = end of stdout + end of stderr → fully done
            if eot_count >= 2:
                break
        else:
            time.sleep(0.01)
    return out


def main():
    print(f"Connecting {PORT} @ {BAUD}...")
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(1)
    ser.reset_input_buffer()

    print("Interrupting current program (Ctrl+C)...")
    ser.write(b"\x03")
    time.sleep(0.5)
    ser.write(b"\x03")
    time.sleep(0.5)
    ser.reset_input_buffer()

    print("Entering raw REPL (Ctrl+A)...")
    ser.write(b"\x01")
    time.sleep(0.5)
    prompt = ser.read(1024)
    if b"raw REPL" not in prompt:
        print(f"Warning: Unexpected prompt: {prompt.decode(errors='replace')}")

    ser.write(b"import gc; gc.collect()\r")
    ser.write(b"\x04")
    time.sleep(0.1)
    ser.reset_input_buffer()

    # Auto-compress HTML trước khi upload
    gz_files = ensure_gzip()
    
    # Upload các file Python và Web (bao gồm cả .gz)
    # Gộp chung vào danh sách để tải lên đồng bộ theo chunk
    web_all = WEB_FILES + gz_files
    all_files = [(fname, fname, "wb") for fname in FILES] + [("web/" + fname, "web/" + fname, "wb") for fname in web_all]
    
    # Tạo thư mục web trên ESP32 nếu chưa có
    raw_cmd(ser, "import os\ntry:\n    os.mkdir('web')\nexcept:\n    pass")
    
    for display_name, rel_path, mode in all_files:
        # Đường dẫn tuyệt đối trên PC
        if rel_path.startswith("web/"):
            pc_path = os.path.join(WEB_DIR, rel_path.split("/")[-1])
        else:
            pc_path = os.path.join(FIRMWARE, rel_path)
            
        with open(pc_path, "rb") as f:
            content = f.read()
            
        # Strip UTF-8 BOM cho các file Python đọc dạng binary (ef bb bf)
        if not rel_path.startswith("web/") and content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
            
        print(f"  {display_name} ({len(content)} bytes)...", end="", flush=True)
        t0 = time.time()
        
        # Mở file trên ESP32
        res_open = raw_cmd(ser, f"f = open('{rel_path}', '{mode}')\n")
        if b"OK" not in res_open:
            print(f" FAIL (open): {res_open.decode(errors='replace')}")
            continue
            
        # Ghi theo từng chunk 512 bytes để tránh tràn buffer UART của ESP32
        chunk_size = 512
        failed = False
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i+chunk_size]
            safe_chunk = repr(chunk)
            res_write = raw_cmd(ser, f"f.write({safe_chunk})\n", timeout=10)
            if b"OK" not in res_write:
                print(f" FAIL (write chunk {i}): {res_write.decode(errors='replace')}")
                failed = True
                break
                
        # Đóng file
        res_close = raw_cmd(ser, "f.close()\n")
        
        dt = time.time() - t0
        if not failed and b"OK" in res_close:
            print(f" {dt:.1f}s")
        else:
            print(f" FAIL (close): {res_close.decode(errors='replace')}")
            
        # Dọn rác bộ nhớ
        ser.write(b"gc.collect()\r")
        ser.write(b"\x04")
        time.sleep(0.1)
        ser.reset_input_buffer()

    print("\nResetting ESP32 (Ctrl+D)...")
    ser.write(b"\x04")
    time.sleep(0.5)
    ser.write(b"\x02")
    ser.close()
    print("Done!")



if __name__ == "__main__":
    main()
