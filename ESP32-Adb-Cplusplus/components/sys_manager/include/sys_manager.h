#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Khởi tạo WiFi (Tự động đọc cấu hình hoặc bật AP Mode)
void wifi_manager_init(void);
bool wifi_is_ap_mode(void);
bool wifi_is_connected(void);

// Thread Safety cho file config WiFi
void wifi_config_lock(void);
void wifi_config_unlock(void);

// Khởi tạo đèn LED trạng thái
void led_indicator_init(void);
void led_trigger_block_blink(void); // Nháy 1 cái khi block quảng cáo

#ifdef __cplusplus
}
#endif
