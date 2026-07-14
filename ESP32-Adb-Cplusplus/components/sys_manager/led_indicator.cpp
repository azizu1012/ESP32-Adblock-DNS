#include "sys_manager.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

// Đèn LED tích hợp thường ở GPIO 2
#define BLINK_GPIO GPIO_NUM_2
static const char *TAG = "LED";

static bool block_trigger = false;

static void led_task(void *pvParameter) {
    gpio_reset_pin(BLINK_GPIO);
    gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);
    
    while(1) {
        if (block_trigger) {
            // Chớp giật 1 phát khi chặn thành công
            gpio_set_level(BLINK_GPIO, 1);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 0);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            block_trigger = false;
        } else if (wifi_is_ap_mode()) {
            // Chớp đều liên tục (Setup mode)
            gpio_set_level(BLINK_GPIO, 1);
            vTaskDelay(200 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 0);
            vTaskDelay(200 / portTICK_PERIOD_MS);
        } else if (wifi_is_connected()) {
            // Heartbeat: 2 nhịp nhanh, nghỉ 2s (Active LOW: 0 là ON, 1 là OFF)
            gpio_set_level(BLINK_GPIO, 0);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 1);
            vTaskDelay(100 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 0);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 1);
            vTaskDelay(2000 / portTICK_PERIOD_MS);
        } else {
            // Đang dò WiFi (Sáng lâu)
            gpio_set_level(BLINK_GPIO, 1);
            vTaskDelay(500 / portTICK_PERIOD_MS);
            gpio_set_level(BLINK_GPIO, 0);
            vTaskDelay(500 / portTICK_PERIOD_MS);
        }
    }
}

void led_indicator_init(void) {
    xTaskCreatePinnedToCore(led_task, "led_task", 2048, NULL, 1, NULL, tskNO_AFFINITY);
}

void led_trigger_block_blink(void) {
    block_trigger = true;
}
