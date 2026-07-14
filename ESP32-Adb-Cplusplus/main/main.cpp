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

    ESP_LOGI(TAG, "C++ DNS AdBlocker is starting...");
    ESP_LOGI(TAG, "CPU Core: %d", esp_cpu_get_core_id());
    
    // Khởi tạo Đèn LED và WiFi
    led_indicator_init();
    wifi_manager_init();

    // 2. Cấu hình WiFi và DNS Manager
    stats_init();
    dns_server_start();
    dns_optimizer_init();
    web_server_start();

    // Vòng lặp chính
    while (1) {
        vTaskDelay(1000 / portTICK_PERIOD_MS);
    }
}
