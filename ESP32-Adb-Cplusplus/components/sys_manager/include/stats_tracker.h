#ifndef STATS_TRACKER_H
#define STATS_TRACKER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo Stats Tracker
void stats_tracker_init(void);

// Đăng ký query mới (gọi từ luồng DNS Server)
void stats_record_query(const char* domain, bool is_blocked, const char* client_ip);

// Trả về JSON Stats đầy đủ (cấp phát động trên Heap, cần free() sau khi dùng)
// Dùng cho API /api/stats
char* stats_get_json_response(void);

// Reset arena pool cho cJSON (gọi trước mọi cJSON op ngoài stats_get_json_response)
void stats_pool_reset(void);

// Giải phóng bộ nhớ cJSON — an toàn với cả pool pointer và heap pointer.
// Dùng THAY THẾ cho free() trên mọi kết quả trả về từ cJSON_Print* hoặc stats_get_*_json().
// Hooks cJSON toàn cục có thể redirect pool ptr; free() thường sẽ crash.
void stats_pool_free(void* ptr);

// Lock/Unlock stats mutex (cho web API handlers dùng cJSON)
void stats_lock(void);
void stats_unlock(void);

// Kiểm tra có query DNS trong 15 giây gần nhất (dùng cho LED health check)
bool stats_has_recent_activity(void);

// API riêng cho Safelist Custom (Lấy danh sách và Thêm/Xóa)
char* stats_get_custom_safelist_json(void);
bool stats_add_custom_safelist(const char* domain);
bool stats_remove_custom_safelist(const char* domain);
bool stats_is_in_custom_safelist(const char* domain);

#ifdef __cplusplus
}
#endif

#endif // STATS_TRACKER_H
