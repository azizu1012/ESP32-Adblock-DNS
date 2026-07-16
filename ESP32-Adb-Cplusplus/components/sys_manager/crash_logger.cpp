#include "crash_logger.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_sntp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <vector>
#include <string>

static const char *TAG = "CrashLogger";

// Lưu vào RTC memory để không bị mất khi reset
RTC_DATA_ATTR esp_reset_reason_t pending_crash_reason = ESP_RST_UNKNOWN;

static const char* get_reason_str(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_POWERON: return "Power-on Reset";
        case ESP_RST_EXT: return "External Pin Reset";
        case ESP_RST_SW: return "Software Reset";
        case ESP_RST_PANIC: return "Software Exception / Panic";
        case ESP_RST_INT_WDT: return "Interrupt Watchdog Timeout";
        case ESP_RST_TASK_WDT: return "Task Watchdog Timeout";
        case ESP_RST_WDT: return "Other Watchdog";
        case ESP_RST_DEEPSLEEP: return "Deep Sleep Wakeup";
        case ESP_RST_BROWNOUT: return "Brownout (Voltage Drop)";
        case ESP_RST_SDIO: return "SDIO Reset";
        default: return "Other / Unknown";
    }
}

void rotate_crash_logs(void) {
    FILE* f = fopen("/spiffs/crash.log", "r");
    if (!f) return;

    std::vector<std::string> valid_lines;
    char line[256];
    
    time_t now = time(NULL);
    const int MAX_AGE_SEC = 24 * 3600; // 24 hours

    while (fgets(line, sizeof(line), f)) {
        // Cú pháp dự kiến: [YYYY-MM-DD HH:MM:SS] CRASH DETECTED: ...
        if (line[0] == '[') {
            if (strncmp(line, "[TIME NOT SYNCED]", 17) == 0) {
                valid_lines.push_back(line);
                if (valid_lines.size() > 50) valid_lines.erase(valid_lines.begin());
                continue;
            }
            
            struct tm tm_info;
            memset(&tm_info, 0, sizeof(tm_info));
            int year, month, day, hour, min, sec;
            if (sscanf(line, "[%d-%d-%d %d:%d:%d]", &year, &month, &day, &hour, &min, &sec) == 6) {
                tm_info.tm_year = year - 1900;
                tm_info.tm_mon = month - 1;
                tm_info.tm_mday = day;
                tm_info.tm_hour = hour;
                tm_info.tm_min = min;
                tm_info.tm_sec = sec;
                
                time_t log_time = mktime(&tm_info);
                if (log_time != -1 && difftime(now, log_time) <= MAX_AGE_SEC) {
                    valid_lines.push_back(line);
                    if (valid_lines.size() > 50) valid_lines.erase(valid_lines.begin());
                }
            }
        }
    }
    fclose(f);

    // Ghi đè file với các dòng còn hợp lệ
    if (valid_lines.empty()) {
        remove("/spiffs/crash.log");
    } else {
        f = fopen("/spiffs/crash.log", "w");
        if (f) {
            for (const auto& l : valid_lines) {
                fputs(l.c_str(), f);
            }
            fclose(f);
        }
    }
}

static void logger_task(void *pvParameters) {
    // Chờ đồng bộ thời gian NTP
    time_t now = 0;
    struct tm timeinfo;
    memset(&timeinfo, 0, sizeof(timeinfo));
    int retry = 0;
    
    while (timeinfo.tm_year < (2020 - 1900) && ++retry < 60) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        time(&now);
        localtime_r(&now, &timeinfo);
    }
    
    // Đã có giờ chuẩn (hoặc timeout)
    if (timeinfo.tm_year >= (2020 - 1900)) {
        ESP_LOGI(TAG, "Time synced! Rotating logs...");
        // 1. Xoay vòng log cũ
        rotate_crash_logs();
    } else {
        ESP_LOGE(TAG, "Failed to sync time, logs will not rotate properly.");
    }
    
    // 2. Ghi lỗi pending (nếu có), kể cả khi không có giờ
    if (pending_crash_reason != ESP_RST_UNKNOWN) {
        FILE* f = fopen("/spiffs/crash.log", "a");
        if (f) {
            char strftime_buf[64];
            if (timeinfo.tm_year >= (2020 - 1900)) {
                strftime(strftime_buf, sizeof(strftime_buf), "[%Y-%m-%d %H:%M:%S]", &timeinfo);
            } else {
                strcpy(strftime_buf, "[TIME NOT SYNCED]");
            }
            fprintf(f, "%s CRASH DETECTED: %s\n", strftime_buf, get_reason_str(pending_crash_reason));
            fclose(f);
            ESP_LOGW(TAG, "Wrote pending crash: %s", get_reason_str(pending_crash_reason));
        }
        pending_crash_reason = ESP_RST_UNKNOWN;
    }
    
    vTaskDelete(NULL);
}

void crash_logger_init(void) {
    xTaskCreate(logger_task, "crash_logger", 4096, NULL, 5, NULL);
}

void log_abnormal_event(const char* event_msg) {
    time_t now = 0;
    struct tm timeinfo;
    memset(&timeinfo, 0, sizeof(timeinfo));
    time(&now);
    localtime_r(&now, &timeinfo);
    
    FILE* f = fopen("/spiffs/crash.log", "a");
    if (f) {
        char strftime_buf[64];
        if (timeinfo.tm_year >= (2020 - 1900)) {
            strftime(strftime_buf, sizeof(strftime_buf), "[%Y-%m-%d %H:%M:%S]", &timeinfo);
        } else {
            strcpy(strftime_buf, "[TIME NOT SYNCED]");
        }
        fprintf(f, "%s ABNORMAL EVENT: %s\n", strftime_buf, event_msg);
        fclose(f);
        ESP_LOGW(TAG, "Logged abnormal event: %s", event_msg);
    }
}
