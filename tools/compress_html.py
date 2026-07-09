"""Compress HTML files with gzip for ESP32 pre-compression serving."""
import gzip
import os

HTML_DIR = os.path.join(os.path.dirname(__file__), "..", "firmware", "web")

def compress_file(src):
    dst = src + ".gz"
    with open(src, "rb") as f_in:
        data = f_in.read()
    with gzip.open(dst, "wb", compresslevel=9) as f_out:
        f_out.write(data)
    orig = os.path.getsize(src)
    comp = os.path.getsize(dst)
    ratio = (1 - comp / orig) * 100
    print(f"  {os.path.basename(src)}: {orig:,} -> {comp:,} bytes ({ratio:.1f}% smaller)")
    return dst

def main():
    print("Compressing HTML files for ESP32 gzip serving...\n")
    for name in ["index.html", "setup.html"]:
        path = os.path.join(HTML_DIR, name)
        if os.path.exists(path):
            compress_file(path)
        else:
            print(f"  WARNING: {path} not found, skipping")
    print("\nDone! Upload .gz files to ESP32 with upload_serial.py")

if __name__ == "__main__":
    main()
