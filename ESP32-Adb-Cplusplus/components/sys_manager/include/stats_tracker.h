#ifndef STATS_TRACKER_H
#define STATS_TRACKER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo Stats Tracker
void stats_init(void);

// Đăng ký query mới (gọi từ luồng DNS Server)
void stats_record_query(const char* domain, bool is_blocked, const char* client_ip);

// Trả về JSON Stats đầy đủ (cấp phát động trên Heap, cần free() sau khi dùng)
// Dùng cho API /api/stats
char* stats_get_json_response(void);

// API riêng cho Safelist Custom (Lấy danh sách và Thêm/Xóa)
char* stats_get_custom_safelist_json(void);
bool stats_add_custom_safelist(const char* domain);
bool stats_remove_custom_safelist(const char* domain);
bool stats_is_in_custom_safelist(const char* domain);

#ifdef __cplusplus
}
#endif

#endif // STATS_TRACKER_H
