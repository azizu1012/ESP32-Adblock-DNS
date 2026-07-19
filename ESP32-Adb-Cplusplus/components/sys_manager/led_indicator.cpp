#include "sys_manager.h"
#include "stats_tracker.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "esp_timer.h"

#define LEDC_TIMER      LEDC_TIMER_0
#define LEDC_CHANNEL    LEDC_CHANNEL_0
#define LEDC_MODE       LEDC_HIGH_SPEED_MODE
#define LEDC_DUTY_RES   LEDC_TIMER_10_BIT
#define LEDC_FREQUENCY  5000
#define BLINK_GPIO      GPIO_NUM_2

static const char *TAG = "LED";

static bool block_pending = false;

static const uint32_t BRIGHT_FULL = 128;   // Đã giảm từ 1023 xuống 128 (đỡ chói)
static const uint32_t BRIGHT_DIM  = 16;    // Đã giảm từ 256 xuống 16 (cực mờ)
static const uint32_t BRIGHT_OFF  = 0;

static inline void led_set(uint32_t duty) {
    ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, duty);
    ledc_update_duty(LEDC_MODE, LEDC_CHANNEL);
}

static bool led_dns_healthy(void) {
    return stats_has_recent_activity();
}

static void led_task(void *pvParameter) {
    ESP_LOGI(TAG, "LED task started (hw init done in main task)");
    while (1) {
        if (block_pending) {
            led_set(BRIGHT_DIM);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(450 / portTICK_PERIOD_MS); // Nghỉ 450ms để giới hạn nháy tối đa 2 lần/s
            block_pending = false;
            continue;
        }

        if (wifi_is_ap_mode()) {
            led_set(BRIGHT_FULL);
            vTaskDelay(200 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(200 / portTICK_PERIOD_MS);
        } else if (!wifi_is_connected()) {
            led_set(BRIGHT_FULL);
            vTaskDelay(500 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(500 / portTICK_PERIOD_MS);
        } else if (!led_dns_healthy()) {
            led_set(BRIGHT_FULL);
            vTaskDelay(125 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(125 / portTICK_PERIOD_MS);
        } else {
            led_set(BRIGHT_DIM);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(100 / portTICK_PERIOD_MS);
            led_set(BRIGHT_DIM);
            vTaskDelay(50 / portTICK_PERIOD_MS);
            led_set(BRIGHT_OFF);
            vTaskDelay(2000 / portTICK_PERIOD_MS);
        }
    }
}

void led_indicator_init(void) {
    // LEDC timer/channel config trong main task (stack rộng), tránh overflow trong led_task
    ledc_timer_config_t ledc_timer = {
        .speed_mode      = LEDC_MODE,
        .duty_resolution = LEDC_DUTY_RES,
        .timer_num       = LEDC_TIMER,
        .freq_hz         = LEDC_FREQUENCY,
        .clk_cfg         = LEDC_AUTO_CLK,
        .deconfigure     = false
    };
    ledc_timer_config(&ledc_timer);

    ledc_channel_config_t ledc_channel = {
        .gpio_num   = BLINK_GPIO,
        .speed_mode = LEDC_MODE,
        .channel    = LEDC_CHANNEL,
        .intr_type  = LEDC_INTR_DISABLE,
        .timer_sel  = LEDC_TIMER,
        .duty       = BRIGHT_OFF,
        .hpoint     = 0,
        .flags      = {0}
    };
    ledc_channel_config(&ledc_channel);

    xTaskCreatePinnedToCore(led_task, "led_task", 2048, NULL, 1, NULL, tskNO_AFFINITY);
    ESP_LOGI(TAG, "LED indicator initialized");
}

void led_trigger_block_blink(void) {
    block_pending = true;
}
