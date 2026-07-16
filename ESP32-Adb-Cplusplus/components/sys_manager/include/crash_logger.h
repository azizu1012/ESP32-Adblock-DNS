#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo tiến trình xoay vòng log và chờ NTP sync để ghi lỗi RTC
void crash_logger_init(void);

// Xoay vòng file log (xóa các dòng quá 24h)
void rotate_crash_logs(void);

// Ghi log trạng thái dị thường (ví dụ rớt mạng, lỗi malloc) cùng thời gian chuẩn NTP
void log_abnormal_event(const char* event_msg);

#ifdef __cplusplus
}
#endif
