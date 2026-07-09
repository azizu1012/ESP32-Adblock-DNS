def _fnv1a_64(data):
    """FNV-1a 64-bit hash."""
    h = 0xCBF29CE484222325
    p = 0x100000001B3
    for b in data:
        h = ((h ^ b) * p) & 0xFFFFFFFFFFFFFFFF
    return h

def _bloom_search(self, domain):
    """Tìm domain trong Blocked Bloom Filter bằng 1 lần đọc Flash 64 bytes."""
    try:
        h = _fnv1a_64(domain.encode("utf-8"))
        block_idx = (h >> 32) % 18750
        h_low = h & 0xFFFFFFFF
        
        with open(self.BLOCKED_BIN, "rb") as f:
            f.seek(block_idx * 64)
            f.readinto(self._bloom_buf)
            
        for i in range(8):
            bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512
            byte_pos = bit_pos // 8
            bit_mask = 1 << (bit_pos % 8)
            if not (self._bloom_buf[byte_pos] & bit_mask):
                return False
        return True
    except:
        return False

def attach(cls):
    cls._bloom_search = _bloom_search
