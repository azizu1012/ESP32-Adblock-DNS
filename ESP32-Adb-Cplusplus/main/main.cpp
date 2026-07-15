#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "esp_spiffs.h"
#include "dns_server.h"
#include "web_server.h"
#include "sys_manager.h"
#include "stats_tracker.h"
#include "dns_optimizer.h"

static const char *TAG = "AdBlock_C++";

// Hàm mồi (Mount) ổ đĩa SPIFFS
static void init_spiffs(void) {
    esp_vfs_spiffs_conf_t conf = {
      .base_path = "/spiffs",
      .partition_label = NULL,
      .max_files = 5,
      .format_if_mount_failed = true
    };
    esp_err_t ret = esp_vfs_spiffs_register(&conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Lỗi mount SPIFFS (%s)", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Mount ổ đĩa SPIFFS thành công!");
    }
}

static void log_reset_reason(void) {
    esp_reset_reason_t reason = esp_reset_reason();
    const char* reason_str = "UNKNOWN";
    bool is_crash = false;

    switch (reason) {
        case ESP_RST_POWERON: reason_str = "Power-on Reset"; break;
        case ESP_RST_EXT: reason_str = "External Pin Reset"; break;
        case ESP_RST_SW: reason_str = "Software Reset"; break;
        case ESP_RST_PANIC: reason_str = "Software Exception / Panic"; is_crash = true; break;
        case ESP_RST_INT_WDT: reason_str = "Interrupt Watchdog Timeout"; is_crash = true; break;
        case ESP_RST_TASK_WDT: reason_str = "Task Watchdog Timeout"; is_crash = true; break;
        case ESP_RST_WDT: reason_str = "Other Watchdog"; is_crash = true; break;
        case ESP_RST_DEEPSLEEP: reason_str = "Deep Sleep Wakeup"; break;
        case ESP_RST_BROWNOUT: reason_str = "Brownout (Voltage Drop)"; is_crash = true; break;
        case ESP_RST_SDIO: reason_str = "SDIO Reset"; break;
        default: reason_str = "Other / Unknown"; break;
    }

    ESP_LOGI(TAG, "Reset Reason: %s", reason_str);

    // Save to crash.log if it's an unexpected crash
    if (is_crash) {
        FILE* f = fopen("/spiffs/crash.log", "a");
        if (f) {
            fprintf(f, "CRASH DETECTED: %s\n", reason_str);
            fclose(f);
        }
    }
}

extern "C" void app_main(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Khởi tạo ổ cứng để chuẩn bị đọc file web
    init_spiffs();
    log_reset_reason();

    // --- DUMP CRASH LOG ---
    FILE* f = fopen("/spiffs/crash.log", "r");
    if (f) {
        ESP_LOGE(TAG, "==== CRASH LOG DUMP ====");
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            // Loại bỏ ký tự xuống dòng ở cuối nếu có để in đẹp hơn
            line[strcspn(line, "\r\n")] = 0;
            ESP_LOGE(TAG, "LOG: %s", line);
        }
        ESP_LOGE(TAG, "========================");
        fclose(f);
    } else {
        ESP_LOGI(TAG, "No crash log found.");
    }
    // ----------------------

    ESP_LOGI(TAG, "C++ DNS AdBlocker is starting...");
    ESP_LOGI(TAG, "CPU Core: %d", esp_cpu_get_core_id());
    
    // Khởi tạo Đèn LED và WiFi
    led_indicator_init();
    wifi_manager_init();

    // 2. Cấu hình WiFi và DNS Manager
    stats_init();
    dns_server_start();
    web_server_start();

    // Vòng lặp chính
    while (1) {
        vTaskDelay(1000 / portTICK_PERIOD_MS);
    }
}
