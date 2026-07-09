"""
dns_bloom.py
Xử lý thuật toán băm (Hash) và kiểm tra miền bị chặn (Blocked Domains) 
dựa trên cấu trúc dữ liệu Blocked Bloom Filter.

Được tách ra từ dns.py để giảm kích thước file và tránh God File.
Dùng kỹ thuật monkey patching `attach(cls)` để gắn vào class DNSServer.
"""

def _fnv1a_64(data):
    """
    Thuật toán băm FNV-1a 64-bit.
    Rất nhẹ và nhanh trên vi điều khiển, cho tỷ lệ va chạm (collision) cực thấp.
    Đầu vào: data (bytes)
    Đầu ra: số nguyên 64-bit (int)
    """
    h = 0xCBF29CE484222325
    p = 0x100000001B3
    for b in data:
        h = ((h ^ b) * p) & 0xFFFFFFFFFFFFFFFF
    return h

def _bloom_search(self, domain):
    """
    Tìm domain trong Blocked Bloom Filter bằng 1 lần đọc Flash 64 bytes.
    Thay vì load toàn bộ 1.2MB file vào RAM (bất khả thi trên ESP32),
    hàm này dùng Double Hashing để tính toán block index (chỉ mục khối).
    Sau đó seek() thẳng đến khối đó và đọc đúng 64 bytes vào buffer cấp sẵn (Zero Allocation).
    """
    try:
        # 1. Băm tên miền
        h = _fnv1a_64(domain.encode("utf-8"))
        
        # 2. Tính chỉ mục block (18750 block, mỗi block 64 bytes)
        block_idx = (h >> 32) % 18750
        h_low = h & 0xFFFFFFFF
        
        # 3. Mở file và nhảy (seek) đến đúng vị trí block
        with open(self.BLOCKED_BIN, "rb") as f:
            f.seek(block_idx * 64)
            # Đọc thẳng vào buffer có sẵn để tránh cấp phát RAM động
            f.readinto(self._bloom_buf)
            
        # 4. Kiểm tra 8 bít băm (Kirsch-Mitzenmacher optimization)
        for i in range(8):
            bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512
            byte_pos = bit_pos // 8
            bit_mask = 1 << (bit_pos % 8)
            
            # Nếu có bất kỳ bit nào = 0, chắc chắn miền này không bị chặn
            if not (self._bloom_buf[byte_pos] & bit_mask):
                return False
                
        # Nếu tất cả 8 bits = 1, miền này khả năng cao nằm trong danh sách đen
        return True
    except Exception:
        # An toàn (Fail-safe): Lỗi đọc file thì cho phép qua
        return False

def attach(cls):
    """
    Hàm monkey patching: Gắn các phương thức tĩnh và logic vào class gốc (DNSServer).
    Điều này giúp module hóa code mà không tốn RAM cho mô hình kế thừa OOP.
    """
    cls._bloom_search = _bloom_search
