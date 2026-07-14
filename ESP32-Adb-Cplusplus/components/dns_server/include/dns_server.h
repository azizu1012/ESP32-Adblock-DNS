#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Khởi động DNS Server chạy ngầm trên một FreeRTOS Task
void dns_server_start(void);

#ifdef __cplusplus
}
#endif
