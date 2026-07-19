#include "gct_verifier.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "sys_manager.h" // Để lấy cờ chớp đèn
#include <string.h>
#include <time.h>
#include <unordered_map>
#include <string>

static const char *TAG = "GCT_Verifier";

// Cấu trúc map lưu danh sách động: <Domain, Expiry_Timestamp>
static std::unordered_map<std::string, time_t> safelist_dyn;
static QueueHandle_t gct_queue;
static SemaphoreHandle_t gct_mutex = NULL;

static bool verify_with_adguard(const char* domain) {
    // TODO: Implement thật bằng DNS query tới 94.140.14.14 (AdGuard DNS)
    // Hiện tại return false: KHÔNG whitelist bừa, giữ nguyên blocking decision
    return false;
}

static void gct_task(void *pvParameter) {
    char domain[256];
    while (1) {
        if (xQueueReceive(gct_queue, &domain, portMAX_DELAY)) {
            ESP_LOGI(TAG, "Đang kiểm chứng chéo domain: %s", domain);
            
            // Giả lập Query 3 Server Public
            bool is_safe = verify_with_adguard(domain);
            
            if (is_safe) {
                ESP_LOGW(TAG, "GCT Phát hiện Oan! Đưa %s vào Dyn Safelist (10 phút)", domain);
                time_t now;
                time(&now);
                // Vì C++ tối ưu hơn nhiều nên giảm thời gian chờ phạt xuống còn 1/6 (600s = 10 phút)
                if (gct_mutex) xSemaphoreTake(gct_mutex, portMAX_DELAY);
                safelist_dyn[std::string(domain)] = now + 600;
                if (gct_mutex) xSemaphoreGive(gct_mutex);
            } else {
                ESP_LOGI(TAG, "AdGuard cũng block %s. Xác nhận đây là Ads!", domain);
                // Kích hoạt đèn chớp chặn
                led_trigger_block_blink();
            }
        }
    }
}

void gct_verifier_init(void) {
    gct_mutex = xSemaphoreCreateMutex();
    gct_queue = xQueueCreate(20, 256);
    xTaskCreatePinnedToCore(gct_task, "gct_task", 4096, NULL, 1, NULL, tskNO_AFFINITY);
}

void gct_queue_domain(const char* domain) {
    // Gửi domain vào hàng đợi, không đợi (non-blocking) nếu đầy
    xQueueSend(gct_queue, domain, 0);
}

bool is_domain_in_safelist_dyn(const char* domain) {
    if (!gct_mutex) return false;
    time_t now;
    time(&now);
    
    bool found = false;
    xSemaphoreTake(gct_mutex, portMAX_DELAY);
    auto it = safelist_dyn.find(std::string(domain));
    if (it != safelist_dyn.end()) {
        if (now < it->second) {
            found = true; // Vẫn còn hạn
        } else {
            safelist_dyn.erase(it); // Hết hạn, xóa
        }
    }
    xSemaphoreGive(gct_mutex);
    return found;
}

