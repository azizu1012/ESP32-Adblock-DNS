#include "sys_manager.h"
extern "C" void dns_optimizer_set_upstream(const char* ip, int rtt);
#include <esp_wifi.h>
#include <esp_event.h>
#include <esp_log.h>
#include <nvs.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include <cJSON.h>
#include <atomic>
#include "esp_sntp.h"
#include "esp_timer.h"
#include "crash_logger.h"
#include "stats_tracker.h"

static const char *TAG = "WiFi_Manager";
static std::atomic<bool> is_ap_mode{false};
static std::atomic<bool> is_connected{false};
static int s_retry_num = 0;
static SemaphoreHandle_t s_wifi_config_mutex = NULL;

extern "C" void wifi_config_lock(void) {
    if (s_wifi_config_mutex) xSemaphoreTake(s_wifi_config_mutex, portMAX_DELAY);
}

extern "C" void wifi_config_unlock(void) {
    if (s_wifi_config_mutex) xSemaphoreGive(s_wifi_config_mutex);
}

static esp_timer_handle_t wifi_retry_timer = NULL;
static void wifi_retry_timer_cb(void* arg) {
    ESP_LOGI(TAG, "Đang thử kết nối lại WiFi (Tự phục hồi)...");
    esp_wifi_connect();
}

static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_retry_num < 5) {
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "Thử kết nối lại WiFi (lần %d)...", s_retry_num);
        } else {
            ESP_LOGW(TAG, "Đã thử 5 lần không thành công! Hẹn giờ thử lại sau 15 giây...");
            log_abnormal_event("WiFi Connection Lost (5 retries failed). Reconnecting in 15s...");
            is_connected = false;
            esp_timer_stop(wifi_retry_timer); // Đảm bảo timer cũ đã dừng
            esp_timer_start_once(wifi_retry_timer, 15000000); // 15 giây = 15.000.000 us
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        s_retry_num = 0; // Reset bộ đếm khi kết nối thành công
        esp_timer_stop(wifi_retry_timer); // Tắt hẹn giờ
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "Đã kết nối WiFi thành công! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        
        wifi_config_lock();
        // Auto-assign .234 logic (Giống Python)
        FILE* f = fopen("/spiffs/config.json", "r");
        bool has_static_ip = false;
        if (f) {
            char buf[512];
            if (fgets(buf, sizeof(buf), f) != NULL) {
                if (strstr(buf, "\"ip\":\"")) has_static_ip = true;
            }
            fclose(f);
        }
        
        if (!has_static_ip) {
            ESP_LOGI(TAG, "Chưa có IP tĩnh, tự động gán đuôi .234 và reboot...");
            uint32_t ip = event->ip_info.ip.addr;
            uint32_t gw = event->ip_info.gw.addr;
            uint32_t netmask = event->ip_info.netmask.addr;
            
            // Đổi octet cuối thành 234
            ip = (ip & 0x00FFFFFF) | (234 << 24); // ESP32 dùng little-endian
            
            // Đọc lại config cũ bằng cJSON và cập nhật
            cJSON* root = NULL;
            f = fopen("/spiffs/config.json", "r");
            if (f) {
                fseek(f, 0, SEEK_END);
                long fsize = ftell(f);
                fseek(f, 0, SEEK_SET);
                if (fsize > 0 && fsize < 4096) {
                    char *buf = (char*)malloc(fsize + 1);
                    fread(buf, 1, fsize, f);
                    buf[fsize] = 0;
                    root = cJSON_Parse(buf);
                    free(buf);
                }
                fclose(f);
            }
            if (!root) root = cJSON_CreateObject();
            
            char ip_str[16], gw_str[16], nm_str[16];
            snprintf(ip_str, sizeof(ip_str), IPSTR, IP2STR((esp_ip4_addr_t*)&ip));
            snprintf(gw_str, sizeof(gw_str), IPSTR, IP2STR((esp_ip4_addr_t*)&gw));
            snprintf(nm_str, sizeof(nm_str), IPSTR, IP2STR((esp_ip4_addr_t*)&netmask));
            
            cJSON_ReplaceItemInObjectCaseSensitive(root, "ip", cJSON_CreateString(ip_str));
            cJSON_ReplaceItemInObjectCaseSensitive(root, "gateway", cJSON_CreateString(gw_str));
            cJSON_ReplaceItemInObjectCaseSensitive(root, "subnet", cJSON_CreateString(nm_str));
            
            if (!cJSON_GetObjectItem(root, "ip")) cJSON_AddItemToObject(root, "ip", cJSON_CreateString(ip_str));
            if (!cJSON_GetObjectItem(root, "gateway")) cJSON_AddItemToObject(root, "gateway", cJSON_CreateString(gw_str));
            if (!cJSON_GetObjectItem(root, "subnet")) cJSON_AddItemToObject(root, "subnet", cJSON_CreateString(nm_str));
            
            char* new_json = cJSON_PrintUnformatted(root);
            if (new_json) {
                f = fopen("/spiffs/config.json", "w");
                if (f) {
                    fputs(new_json, f);
                    fclose(f);
                }
                stats_pool_free(new_json);
            }
            cJSON_Delete(root);
            wifi_config_unlock();
            
            vTaskDelay(1000 / portTICK_PERIOD_MS);
            esp_restart();
        } else {
            wifi_config_unlock();
        }

        is_connected = true;
        is_ap_mode = false;
        s_retry_num = 0;
        
        // Tắt AP nếu đã kết nối thành công để tiết kiệm năng lượng
        esp_wifi_set_mode(WIFI_MODE_STA);
    }
}

void wifi_manager_init(void) {
    if (s_wifi_config_mutex == NULL) {
        s_wifi_config_mutex = xSemaphoreCreateMutex();
    }
    
    // Khởi tạo Timer để Auto-Reconnect
    esp_timer_create_args_t timer_args = {};
    timer_args.callback = &wifi_retry_timer_cb;
    timer_args.name = "wifi_retry";
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &wifi_retry_timer));

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    
    esp_netif_create_default_wifi_sta();
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL);

    wifi_config_t wifi_config = {};
    
    wifi_config_lock();
    FILE* f = fopen("/spiffs/config.json", "r");
    if (f) {
        fseek(f, 0, SEEK_END);
        long fsize = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (fsize > 0 && fsize < 4096) {
            char *buf = (char*)malloc(fsize + 1);
            fread(buf, 1, fsize, f);
            buf[fsize] = 0;
            
            cJSON* root = cJSON_Parse(buf);
            if (root) {
                cJSON* ssid = cJSON_GetObjectItem(root, "ssid");
                cJSON* pass = cJSON_GetObjectItem(root, "password");
                cJSON* ip = cJSON_GetObjectItem(root, "ip");
                cJSON* gw = cJSON_GetObjectItem(root, "gateway");
                cJSON* subnet = cJSON_GetObjectItem(root, "subnet");
                cJSON* upstream = cJSON_GetObjectItem(root, "upstream");
                
                if (ssid && cJSON_IsString(ssid)) {
                    strncpy((char*)wifi_config.sta.ssid, ssid->valuestring, sizeof(wifi_config.sta.ssid)-1);
                }
                if (pass && cJSON_IsString(pass)) {
                    strncpy((char*)wifi_config.sta.password, pass->valuestring, sizeof(wifi_config.sta.password)-1);
                }
                if (ip && gw && subnet && cJSON_IsString(ip) && cJSON_IsString(gw) && cJSON_IsString(subnet)) {
                    if (strlen(ip->valuestring) > 0) {
                        esp_netif_ip_info_t ip_info;
                        ip_info.ip.addr = esp_ip4addr_aton(ip->valuestring);
                        ip_info.gw.addr = esp_ip4addr_aton(gw->valuestring);
                        ip_info.netmask.addr = esp_ip4addr_aton(subnet->valuestring);
                        
                        esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
                        if (netif) {
                            esp_netif_dhcpc_stop(netif);
                            esp_netif_set_ip_info(netif, &ip_info);
                            
                            // Cấu hình DNS Server tĩnh (Bắt buộc để SNTP phân giải được pool.ntp.org khi dùng Static IP)
                            esp_netif_dns_info_t dns_info = {};
                            dns_info.ip.u_addr.ip4.addr = esp_ip4addr_aton("8.8.8.8");
                            dns_info.ip.type = ESP_IPADDR_TYPE_V4;
                            esp_netif_set_dns_info(netif, ESP_NETIF_DNS_MAIN, &dns_info);
                            
                            ESP_LOGI(TAG, "Đã set Static IP từ config: %s", ip->valuestring);
                        }
                    }
                }
                if (upstream && cJSON_IsString(upstream) && strlen(upstream->valuestring) < 16 && strlen(upstream->valuestring) > 0) {
                    dns_optimizer_set_upstream(upstream->valuestring, 15);
                    ESP_LOGI(TAG, "Đã set Upstream DNS từ config: %s", upstream->valuestring);
                }
                cJSON_Delete(root);
            }
            free(buf);
        }
        fclose(f);
        ESP_LOGI(TAG, "Đã đọc WiFi từ /spiffs/config.json: %s", wifi_config.sta.ssid);
    } else {
        // Nếu file chưa tồn tại (mất điện hoặc mới flash), tự động sinh ra file với config của user
        strcpy((char*)wifi_config.sta.ssid, "Dung");
        strcpy((char*)wifi_config.sta.password, "ddmmyy13122004");
        
        f = fopen("/spiffs/config.json", "w");
        if (f) {
            fprintf(f, "{\"ssid\":\"%s\",\"password\":\"%s\"}", wifi_config.sta.ssid, wifi_config.sta.password);
            fclose(f);
            ESP_LOGI(TAG, "Đã tạo file /spiffs/config.json mới với WiFi mặc định");
        }
    }
    wifi_config_unlock();

    // Luôn luôn khởi động ở chế độ APSTA (Vừa phát WiFi, vừa thu WiFi)
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    
    // Cấu hình AP (Phát WiFi)
    wifi_config_t ap_config = {};
    strcpy((char*)ap_config.ap.ssid, "ESP32-AdBlocker-Config");
    ap_config.ap.ssid_len = strlen("ESP32-AdBlocker-Config");
    ap_config.ap.channel = 1;
    ap_config.ap.max_connection = 4;
    ap_config.ap.authmode = WIFI_AUTH_OPEN;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_config));
    
    // Cấu hình STA (Thu WiFi)
    if (strlen((char*)wifi_config.sta.ssid) > 0) {
        ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    }
    
    is_ap_mode = true;
    
    // Soft-start: Chờ 500ms cho điện áp ổn định trước khi bật Wi-Fi PHY
    vTaskDelay(pdMS_TO_TICKS(500));
    
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_max_tx_power(32); // Cắt giảm công suất phát (8dBm) để mạch sống dai với cáp dỏm

    // Khởi tạo SNTP để đồng bộ thời gian (cần cho ghi log)
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
    
    // Đặt múi giờ Việt Nam (UTC+7)
    setenv("TZ", "<-07>7", 1);
    tzset();
}

bool wifi_is_ap_mode(void) { return is_ap_mode.load(); }
bool wifi_is_connected(void) { return is_connected.load(); }
