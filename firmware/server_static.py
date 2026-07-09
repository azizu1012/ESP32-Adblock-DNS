"""
server_static.py
Quản lý việc truyền phát (streaming) các file tĩnh như HTML, CSS, JS từ Flash của ESP32.
Sử dụng kỹ thuật chunking để không làm tràn RAM khi file quá lớn.
Hỗ trợ Gzip Pre-compression và ETag caching để tối ưu tốc độ tải trang.
"""
def _stream_file(conn, path, if_none_match=None, accept_gzip=False):
    """
    Stream file tĩnh từ flash, ưu tiên file .gz nén sẵn nếu trình duyệt hỗ trợ.
    Gzip pre-compression giảm dung lượng 23KB -> ~5KB, giải phóng socket nhanh hơn 4x.
    Tích hợp cơ chế ETag Caching (If-None-Match), trả về 304 Not Modified ngay lập tức 
    khi file không đổi để chống nghẽn do DDoS / F5 spamming.
    """
    import gc
    import os
    try:
        conn.settimeout(2.0)
    except Exception:
        pass
    gc.collect()

    # Kiem tra file .gz nen san co ton tai va trinh duyet co ho tro gzip khong
    gz_path = path + ".gz"
    use_gzip = False
    if accept_gzip:
        try:
            os.stat(gz_path)
            use_gzip = True
        except OSError:
            pass

    # Stat file goc de tinh ETag (luon dua tren file goc, khong phai file .gz)
    try:
        stat = os.stat(path)
        size = stat[6]
        mtime = stat[8] if len(stat) > 8 else 0
    except OSError:
        conn.sendall(
            b"HTTP/1.1 404 Not Found\r\nContent-Type:text/plain\r\n"
            b"Connection:close\r\nContent-Length:13\r\n\r\n404 Not Found"
        )
        return

    # ETag dua tren kich thuoc va thoi gian sua doi cua file goc
    etag = f'"{ size}-{mtime}"'

    # Neu ETag trung khop, tra ve 304 ngay lap tuc
    if if_none_match == etag:
        resp = (
            "HTTP/1.1 304 Not Modified\r\n"
            f"ETag: {etag}\r\n"
            "Cache-Control: no-cache, must-revalidate\r\n"
            "Connection: close\r\n\r\n"
        )
        conn.sendall(resp.encode())
        return

    # Xac dinh file thuc te se stream (nen hoac goc)
    if use_gzip:
        gz_stat = os.stat(gz_path)
        send_size = gz_stat[6]
        send_path = gz_path
    else:
        send_size = size
        send_path = path

    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Cache-Control: no-cache, must-revalidate\r\n"
        f"ETag: {etag}\r\n"
        + ("Content-Encoding: gzip\r\n" if use_gzip else "")
        + "Connection: close\r\n"
        f"Content-Length: {send_size}\r\n"
        "\r\n"
    )
    # Combine header and the first chunk to avoid TCP Delayed ACK
    with open(send_path, "rb") as f:
        first_chunk = f.read(1024)
        conn.sendall(header.encode() + first_chunk)
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            conn.sendall(chunk)

def _redirect(conn, path="/"):
    """Gui HTTP redirect 302 - toi uu phan tach Header/Body."""
    body = f"<html><body><script>window.location='{path}'</script></body></html>"
    header = (
        "HTTP/1.1 302 Found\r\n"
        f"Location: {path}\r\n"
        "Content-Type: text/html\r\n"
        "Connection: close\r\n"
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    )
    conn.sendall(header.encode())
    conn.sendall(body.encode())

def attach(cls):
    cls._stream_file = staticmethod(_stream_file)
    cls._redirect = staticmethod(_redirect)
