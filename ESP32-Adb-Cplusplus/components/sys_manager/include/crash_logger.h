#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo tiến trình xoay vòng log và chờ NTP sync để ghi lỗi RTC
void crash_logger_init(void);

// Xoay vòng file log (xóa các dòng quá 12h)
void rotate_crash_logs(void);

#ifdef __cplusplus
}
#endif
