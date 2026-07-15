#include "web_server.h"
#include <esp_http_server.h>
#include <esp_log.h>
#include <esp_system.h>
#include <string.h>
#include <sys/param.h>
#include <sys/time.h>
#include <cJSON.h>
#include "esp_timer.h"
#include "stats_tracker.h"
#include "sys_manager.h"

static const char *TAG = "Web_API";

// ----------------------------------------------------
// Hệ thống Anti-DDoS Rate Limiting (15 req/s)
// ----------------------------------------------------
static uint32_t last_req_sec = 0;
static uint16_t req_count = 0;

static bool is_rate_limited() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    if (tv.tv_sec != last_req_sec) {
        last_req_sec = tv.tv_sec;
        req_count = 1;
        return false;
    }
    req_count++;
    if (req_count > 15) {
        ESP_LOGW(TAG, "Anti-DDoS: Vượt quá 15 req/s, ngắt kết nối!");
        return true;
    }
    return false;
}

// ----------------------------------------------------
// API Handlers
// ----------------------------------------------------

static esp_err_t api_stats_handler(httpd_req_t *req) {
    if (is_rate_limited()) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Too Many Requests");
        return ESP_FAIL;
    }
    httpd_resp_set_type(req, "application/json");
    
    char* json_str = stats_get_json_response();
    if (json_str) {
        httpd_resp_send(req, json_str, HTTPD_RESP_USE_STRLEN);
        free(json_str);
    } else {
        httpd_resp_send(req, "{}", 2);
    }
    return ESP_OK;
}

static esp_err_t api_safelist_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    httpd_resp_set_type(req, "application/json");
    char* json_str = stats_get_custom_safelist_json();
    if (json_str) {
        httpd_resp_send(req, json_str, HTTPD_RESP_USE_STRLEN);
        free(json_str);
    } else {
        httpd_resp_send(req, "[]", 2);
    }
    return ESP_OK;
}

static esp_err_t api_safelist_add_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    char buf[128];
    int ret = httpd_req_recv(req, buf, sizeof(buf) - 1);
    if (ret <= 0) return ESP_FAIL;
    buf[ret] = '\0';
    
    // Parse json {"domain": "..."}
    cJSON* root = cJSON_Parse(buf);
    if (root) {
        cJSON* domain = cJSON_GetObjectItem(root, "domain");
        if (domain && cJSON_IsString(domain)) {
            stats_add_custom_safelist(domain->valuestring);
            httpd_resp_sendstr(req, "{\"ok\":true}");
        } else {
            httpd_resp_sendstr(req, "{\"ok\":false}");
        }
        cJSON_Delete(root);
    }
    return ESP_OK;
}

static esp_err_t api_safelist_remove_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    char buf[128];
    int ret = httpd_req_recv(req, buf, sizeof(buf) - 1);
    if (ret <= 0) return ESP_FAIL;
    buf[ret] = '\0';
    
    cJSON* root = cJSON_Parse(buf);
    if (root) {
        cJSON* domain = cJSON_GetObjectItem(root, "domain");
        if (domain && cJSON_IsString(domain)) {
            stats_remove_custom_safelist(domain->valuestring);
            httpd_resp_sendstr(req, "{\"ok\":true}");
        } else {
            httpd_resp_sendstr(req, "{\"ok\":false}");
        }
        cJSON_Delete(root);
    }
    return ESP_OK;
}

static esp_err_t api_upload_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    
    FILE* fd = fopen("/spiffs/blocked.bin", "w");
    if (!fd) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Cannot open file for writing");
        return ESP_FAIL;
    }

    char* buf = (char*)malloc(4096);
    if (!buf) {
        fclose(fd);
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Out of memory");
        return ESP_FAIL;
    }
    
    int ret, remaining = req->content_len;
    
    // Đọc từng Chunk 4KB thay vì đọc cả cục 1.2MB vào RAM
    while (remaining > 0) {
        if ((ret = httpd_req_recv(req, buf, MIN(remaining, 4096))) <= 0) {
            if (ret == HTTPD_SOCK_ERR_TIMEOUT) continue;
            free(buf);
            fclose(fd);
            return ESP_FAIL;
        }
        // Zero-copy Chunking vào SPIFFS
        fwrite(buf, 1, ret, fd);
        remaining -= ret;
    }
    free(buf);
    fclose(fd);
    
    httpd_resp_sendstr(req, "{\"status\":\"ok\"}");
    return ESP_OK;
}

static esp_err_t api_crashlog_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    httpd_resp_set_type(req, "text/plain");

    FILE* fd = fopen("/spiffs/crash.log", "r");
    if (!fd) {
        httpd_resp_sendstr(req, "No crash log found (or file is empty).\n");
        return ESP_OK;
    }

    char chunk[512];
    size_t chunksize;
    do {
        chunksize = fread(chunk, 1, sizeof(chunk), fd);
        if (chunksize > 0) {
            if (httpd_resp_send_chunk(req, chunk, chunksize) != ESP_OK) {
                fclose(fd);
                return ESP_FAIL;
            }
        }
    } while (chunksize != 0);

    fclose(fd);
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

static esp_err_t api_reboot_handler(httpd_req_t *req) {
    httpd_resp_sendstr(req, "{\"status\":\"rebooting\"}");
    vTaskDelay(100 / portTICK_PERIOD_MS);
    esp_restart();
    return ESP_OK;
}

static esp_err_t api_config_reset_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    wifi_config_lock();
    remove("/spiffs/config.json");
    wifi_config_unlock();
    httpd_resp_sendstr(req, "{\"ok\":true,\"message\":\"Reset. Rebooting...\"}");
    vTaskDelay(1000 / portTICK_PERIOD_MS);
    esp_restart();
    return ESP_OK;
}

static esp_err_t api_config_dhcp_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;
    
    wifi_config_lock();
    FILE* f = fopen("/spiffs/config.json", "r");
    if (f) {
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (size > 0 && size < 4096) {
            char* file_buf = (char*)malloc(size + 1);
            if (file_buf) {
                fread(file_buf, 1, size, f);
                file_buf[size] = '\0';
                cJSON* root = cJSON_Parse(file_buf);
                if (root) {
                    cJSON_DeleteItemFromObject(root, "ip");
                    cJSON_DeleteItemFromObject(root, "gateway");
                    cJSON_DeleteItemFromObject(root, "subnet");
                    
                    char* json_str = cJSON_PrintUnformatted(root);
                    if (json_str) {
                        FILE* fw = fopen("/spiffs/config.json", "w");
                        if (fw) {
                            fwrite(json_str, 1, strlen(json_str), fw);
                            fclose(fw);
                        }
                        free(json_str);
                    }
                    cJSON_Delete(root);
                }
                free(file_buf);
            }
        }
        fclose(f);
    }
    wifi_config_unlock();
    
    httpd_resp_sendstr(req, "{\"ok\":true,\"message\":\"DHCP mode. Rebooting...\"}");
    vTaskDelay(1000 / portTICK_PERIOD_MS);
    esp_restart();
    return ESP_OK;
}

static esp_err_t api_config_wifi_handler(httpd_req_t *req) {
    if (is_rate_limited()) return ESP_FAIL;

    char buf[512];
    int ret = httpd_req_recv(req, buf, sizeof(buf) - 1);
    if (ret <= 0) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "No data");
        return ESP_FAIL;
    }
    buf[ret] = '\0';

    cJSON* req_json = cJSON_Parse(buf);
    if (!req_json) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    cJSON* config_json = cJSON_CreateObject();
    
    wifi_config_lock();
    FILE* f = fopen("/spiffs/config.json", "r");
    if (f) {
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (size > 0 && size < 4096) {
            char* file_buf = (char*)malloc(size + 1);
            if (file_buf) {
                fread(file_buf, 1, size, f);
                file_buf[size] = '\0';
                cJSON* root = cJSON_Parse(file_buf);
                if (root) {
                    cJSON_Delete(config_json);
                    config_json = root;
                }
                free(file_buf);
            }
        }
        fclose(f);
    }

    // Merge keys from req_json into config_json
    cJSON* child = req_json->child;
    while (child) {
        cJSON* exist = cJSON_GetObjectItem(config_json, child->string);
        if (exist) {
            cJSON_ReplaceItemInObject(config_json, child->string, cJSON_Duplicate(child, 1));
        } else {
            cJSON_AddItemToObject(config_json, child->string, cJSON_Duplicate(child, 1));
        }
        child = child->next;
    }

    char* json_str = cJSON_PrintUnformatted(config_json);
    if (json_str) {
        FILE* fw = fopen("/spiffs/config.json", "w");
        if (fw) {
            fwrite(json_str, 1, strlen(json_str), fw);
            fclose(fw);
        }
        free(json_str);
    }
    wifi_config_unlock();

    cJSON_Delete(config_json);
    cJSON_Delete(req_json);

    httpd_resp_sendstr(req, "{\"ok\":true}");
    vTaskDelay(1000 / portTICK_PERIOD_MS);
    esp_restart();
    return ESP_OK;
}

void register_api_routes(httpd_handle_t server) {
    httpd_uri_t uri_stats = { .uri = "/api/stats", .method = HTTP_GET, .handler = api_stats_handler, .user_ctx = NULL };
    httpd_uri_t uri_safe = { .uri = "/api/safelist", .method = HTTP_GET, .handler = api_safelist_handler, .user_ctx = NULL };
    httpd_uri_t uri_safe_add = { .uri = "/api/safelist/add", .method = HTTP_POST, .handler = api_safelist_add_handler, .user_ctx = NULL };
    httpd_uri_t uri_safe_rem = { .uri = "/api/safelist/remove", .method = HTTP_POST, .handler = api_safelist_remove_handler, .user_ctx = NULL };
    httpd_uri_t uri_upload = { .uri = "/api/upload", .method = HTTP_POST, .handler = api_upload_handler, .user_ctx = NULL };
    httpd_uri_t uri_reboot = { .uri = "/api/reboot", .method = HTTP_POST, .handler = api_reboot_handler, .user_ctx = NULL };
    httpd_uri_t uri_config_wifi = { .uri = "/api/config/wifi", .method = HTTP_POST, .handler = api_config_wifi_handler, .user_ctx = NULL };
    httpd_uri_t uri_config_reset = { .uri = "/api/config/reset", .method = HTTP_POST, .handler = api_config_reset_handler, .user_ctx = NULL };
    httpd_uri_t uri_config_dhcp = { .uri = "/api/config/dhcp", .method = HTTP_POST, .handler = api_config_dhcp_handler, .user_ctx = NULL };
    httpd_uri_t uri_crashlog = { .uri = "/api/crashlog", .method = HTTP_GET, .handler = api_crashlog_handler, .user_ctx = NULL };
    
    httpd_register_uri_handler(server, &uri_stats);
    httpd_register_uri_handler(server, &uri_safe);
    httpd_register_uri_handler(server, &uri_safe_add);
    httpd_register_uri_handler(server, &uri_safe_rem);
    httpd_register_uri_handler(server, &uri_upload);
    httpd_register_uri_handler(server, &uri_reboot);
    httpd_register_uri_handler(server, &uri_config_wifi);
    httpd_register_uri_handler(server, &uri_config_reset);
    httpd_register_uri_handler(server, &uri_config_dhcp);
    httpd_register_uri_handler(server, &uri_crashlog);
}
