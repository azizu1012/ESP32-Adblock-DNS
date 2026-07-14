#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo Bloom Filter (mount SPIFFS và map file vào bộ nhớ ảo)
bool bloom_filter_init(const char* filepath);

// Đóng file và giải phóng bộ nhớ ảo
void bloom_filter_deinit(void);

// Kiểm tra xem một domain có nằm trong danh sách đen không
bool bloom_filter_check(const char* domain);

// Đọc số lượng domain bị chặn (4 byte cuối file blocked.bin)
uint32_t bloom_filter_get_count(void);

#ifdef __cplusplus
}
#endif
