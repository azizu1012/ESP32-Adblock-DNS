#include "stats_tracker.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_spi_flash.h"
#include "esp_spiffs.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "sys_manager.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
// No GCT included
// No GCT included

extern "C" uint8_t temprature_sens_read();

extern char g_upstream_ip[16];
extern int g_upstream_rtt;
extern "C" uint32_t bloom_filter_get_count(void);

#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <cstring>
#include <cmath>
#include <cJSON.h>

static const char* TAG = "StatsTracker";

static SemaphoreHandle_t stats_mutex;

static uint32_t total_queries = 0;
static uint32_t blocked_queries = 0;
static uint32_t allowed_queries = 0;
static std::string last_blocked_domain = "";

// Recent queries: ring buffer of 100 items
struct RecentQuery {
    std::string domain;
    bool is_blocked;
    uint64_t timestamp_us;
    std::string client_ip;
};
static std::vector<RecentQuery> recent_queries;
static const size_t MAX_RECENT = 100;
static size_t recent_head = 0;

// Top domains: unordered map tracking counts
static std::unordered_map<std::string, uint32_t> top_domains;

// Active clients: unordered map tracking IPs and last seen timestamp (in microseconds)
static std::unordered_map<std::string, uint64_t> active_clients;

// Custom Safelist: persistent safelist managed by user
static std::unordered_set<std::string> custom_safelist;

static void load_custom_safelist() {
    FILE* f = fopen("/spiffs/safelist.json", "r");
    if (!f) return;

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size > 0 && size < 65536) {
        char* buf = (char*)malloc(size + 1);
        if (buf) {
            fread(buf, 1, size, f);
            buf[size] = '\0';
            cJSON* root = cJSON_Parse(buf);
            if (root && cJSON_IsArray(root)) {
                int count = cJSON_GetArraySize(root);
                for (int i = 0; i < count; i++) {
                    cJSON* item = cJSON_GetArrayItem(root, i);
                    if (cJSON_IsString(item) && item->valuestring != NULL) {
                        custom_safelist.insert(item->valuestring);
                    }
                }
            }
            if (root) cJSON_Delete(root);
            free(buf);
        }
    }
    fclose(f);
}

static void save_custom_safelist() {
    cJSON* root = cJSON_CreateArray();
    for (const auto& domain : custom_safelist) {
        cJSON_AddItemToArray(root, cJSON_CreateString(domain.c_str()));
    }
    char* json_str = cJSON_PrintUnformatted(root);
    if (json_str) {
        FILE* f = fopen("/spiffs/safelist.json", "w");
        if (f) {
            fwrite(json_str, 1, strlen(json_str), f);
            fclose(f);
        }
        free(json_str);
    }
    cJSON_Delete(root);
}

void stats_init(void) {
    stats_mutex = xSemaphoreCreateMutex();
    recent_queries.reserve(MAX_RECENT);
    load_custom_safelist();
}

void stats_record_query(const char* domain, bool is_blocked, const char* client_ip) {
    if (!stats_mutex) return;
    xSemaphoreTake(stats_mutex, portMAX_DELAY);

    total_queries++;
    if (is_blocked) {
        blocked_queries++;
        last_blocked_domain = domain;
    } else {
        allowed_queries++;
    }

    // Add to recent
    uint64_t now_us = esp_timer_get_time();
    RecentQuery rq;
    rq.domain = domain;
    rq.is_blocked = is_blocked;
    rq.timestamp_us = now_us;
    rq.client_ip = (client_ip) ? client_ip : "";

    if (recent_queries.size() < MAX_RECENT) {
        recent_queries.push_back(rq);
    } else {
        recent_queries[recent_head] = rq;
        recent_head = (recent_head + 1) % MAX_RECENT;
    }

    // Add to top domains (if blocked)
    if (is_blocked) {
        top_domains[domain]++;
    }

    // Track client IP
    if (client_ip && strlen(client_ip) > 0) {
        active_clients[client_ip] = esp_timer_get_time();
    }

    xSemaphoreGive(stats_mutex);
}

char* stats_get_json_response(void) {
    if (!stats_mutex) return strdup("{}");

    // Clean up active clients older than 10 minutes (600,000,000 us)
    uint64_t now_us = esp_timer_get_time();
    uint64_t cutoff_us = (now_us > 600000000ULL) ? (now_us - 600000000ULL) : 0;

    xSemaphoreTake(stats_mutex, portMAX_DELAY);

    int client_count = 0;
    for (auto it = active_clients.begin(); it != active_clients.end(); ) {
        if (it->second < cutoff_us) {
            it = active_clients.erase(it);
        } else {
            client_count++;
            ++it;
        }
    }
    if (client_count == 0) client_count = 1; // Fallback to 1 (self)

    cJSON *root = cJSON_CreateObject();
    
    // Core stats
    char version_str[64] = "2.0-C++";
    struct stat st;
    if (stat("/spiffs/app.html.gz", &st) == 0) {
        snprintf(version_str, sizeof(version_str), "%ld-%lld", (long)st.st_size, (long long)st.st_mtime);
    }
    cJSON_AddStringToObject(root, "v", version_str);
    
    cJSON_AddNumberToObject(root, "total", total_queries);
    cJSON_AddNumberToObject(root, "blocked", blocked_queries);
    cJSON_AddNumberToObject(root, "allowed", allowed_queries);
    
    double ratio = (total_queries > 0) ? (((double)blocked_queries / total_queries) * 100.0) : 0.0;
    ratio = round(ratio * 10.0) / 10.0;
    cJSON_AddNumberToObject(root, "ratio", ratio);
    
    cJSON_AddNumberToObject(root, "uptime", (unsigned long)(now_us / 1000000ULL));
    cJSON_AddStringToObject(root, "last_blocked", last_blocked_domain.c_str());
    cJSON_AddNumberToObject(root, "active_clients", client_count);
    cJSON_AddNumberToObject(root, "blocklist_entries", bloom_filter_get_count());

    // RAM & System
    uint32_t free_ram = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    uint32_t total_ram = heap_caps_get_total_size(MALLOC_CAP_INTERNAL);
    cJSON_AddNumberToObject(root, "free_ram", free_ram);
    cJSON_AddNumberToObject(root, "alloc_ram", total_ram - free_ram);
    cJSON_AddNumberToObject(root, "total_ram", total_ram);
    
    // CPU Temperature (ESP32 ROM function returns Fahrenheit)
    // Use integer math to avoid IEEE 754 float precision artifacts
    uint8_t temp_f = temprature_sens_read();
    int temp_x10 = (int)((temp_f - 32) * 50 / 9);  // (F-32)*5/9 * 10, integer only
    double temp_clean = temp_x10 / 10.0;  // 539 / 10.0 = exactly 53.9 in double
    
    cJSON_AddNumberToObject(root, "cpu_temp", temp_clean);
    cJSON_AddNumberToObject(root, "cpu_freq", 240);
    cJSON_AddNumberToObject(root, "core_count", 2);

    // Flash info
    size_t total_bytes = 0, used_bytes = 0;
    if (esp_spiffs_info(NULL, &total_bytes, &used_bytes) == ESP_OK) {
        cJSON_AddNumberToObject(root, "flash_free", total_bytes - used_bytes);
        cJSON_AddNumberToObject(root, "flash_total", total_bytes);
    } else {
        cJSON_AddNumberToObject(root, "flash_free", 0);
        cJSON_AddNumberToObject(root, "flash_total", 4194304); // 4MB
    }
    cJSON_AddNumberToObject(root, "flash_chip", 0);

    // Networking
    cJSON_AddStringToObject(root, "upstream", g_upstream_ip);
    cJSON_AddNumberToObject(root, "upstream_rtt", g_upstream_rtt);
    
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (netif) {
        esp_netif_ip_info_t ip_info;
        if (esp_netif_get_ip_info(netif, &ip_info) == ESP_OK) {
            char ip_str[16];
            esp_ip4addr_ntoa(&ip_info.ip, ip_str, sizeof(ip_str));
            cJSON_AddStringToObject(root, "ip", ip_str);
        } else {
            cJSON_AddStringToObject(root, "ip", "");
        }
    } else {
        cJSON_AddStringToObject(root, "ip", "");
    }

    // Dynamic Safelist (GCT)
    cJSON *dyn_list = cJSON_CreateArray();
    cJSON_AddItemToObject(root, "safelist_dyn", dyn_list);

    // Recent queries array
    cJSON *recent_arr = cJSON_CreateArray();
    size_t count = recent_queries.size();
    for (size_t i = 0; i < count; ++i) {
        size_t idx = (recent_head + i) % count;
        if (idx < count) {
            cJSON *item = cJSON_CreateArray();
            cJSON_AddItemToArray(item, cJSON_CreateString(recent_queries[idx].domain.c_str()));
            cJSON_AddItemToArray(item, cJSON_CreateBool(recent_queries[idx].is_blocked));
            
            // 3. Categories array (empty for now, could be implemented later)
            cJSON *cats = cJSON_CreateArray();
            if (recent_queries[idx].is_blocked) {
                cJSON_AddItemToArray(cats, cJSON_CreateString("ads"));
            }
            cJSON_AddItemToArray(item, cats);
            
            // 4. Time ago in seconds
            uint64_t diff_us = now_us - recent_queries[idx].timestamp_us;
            cJSON_AddItemToArray(item, cJSON_CreateNumber((double)(diff_us / 1000000ULL)));
            
            // 5. Layer (null or string)
            if (recent_queries[idx].is_blocked) {
                cJSON_AddItemToArray(item, cJSON_CreateString("BBF"));
            } else {
                cJSON_AddItemToArray(item, cJSON_CreateNull());
            }
            
            // 6. Client IP
            cJSON_AddItemToArray(item, cJSON_CreateString(recent_queries[idx].client_ip.c_str()));
            
            cJSON_AddItemToArray(recent_arr, item);
        }
    }
    cJSON_AddItemToObject(root, "recent", recent_arr);

    // Top domains array
    // Create a vector of pairs, sort by count descending, pick top 10
    std::vector<std::pair<std::string, uint32_t>> top_vec(top_domains.begin(), top_domains.end());
    std::sort(top_vec.begin(), top_vec.end(), 
        [](const std::pair<std::string, uint32_t>& a, const std::pair<std::string, uint32_t>& b) {
            return a.second > b.second;
        });

    cJSON *top_arr = cJSON_CreateArray();
    int top_limit = (top_vec.size() > 10) ? 10 : top_vec.size();
    for (int i = 0; i < top_limit; ++i) {
        cJSON *item = cJSON_CreateObject();
        cJSON_AddStringToObject(item, "d", top_vec[i].first.c_str());
        cJSON_AddNumberToObject(item, "c", top_vec[i].second);
        
        cJSON *g_arr = cJSON_CreateArray();
        cJSON_AddItemToArray(g_arr, cJSON_CreateString("ads")); // Default category
        cJSON_AddItemToObject(item, "g", g_arr);
        
        cJSON_AddItemToArray(top_arr, item);
    }
    cJSON_AddItemToObject(root, "top", top_arr);

    xSemaphoreGive(stats_mutex);

    char *json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return json_str;
}

char* stats_get_custom_safelist_json(void) {
    if (!stats_mutex) return strdup("[]");
    xSemaphoreTake(stats_mutex, portMAX_DELAY);
    
    cJSON* root = cJSON_CreateArray();
    for (const auto& domain : custom_safelist) {
        cJSON_AddItemToArray(root, cJSON_CreateString(domain.c_str()));
    }
    
    char* json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    xSemaphoreGive(stats_mutex);
    return json_str;
}

bool stats_add_custom_safelist(const char* domain) {
    if (!stats_mutex) return false;
    xSemaphoreTake(stats_mutex, portMAX_DELAY);
    
    custom_safelist.insert(domain);
    save_custom_safelist();
    
    xSemaphoreGive(stats_mutex);
    return true;
}

bool stats_remove_custom_safelist(const char* domain) {
    if (!stats_mutex) return false;
    xSemaphoreTake(stats_mutex, portMAX_DELAY);
    
    auto it = custom_safelist.find(domain);
    if (it != custom_safelist.end()) {
        custom_safelist.erase(it);
        save_custom_safelist();
    }
    
    xSemaphoreGive(stats_mutex);
    return true;
}

bool stats_is_in_custom_safelist(const char* domain) {
    if (!stats_mutex) return false;
    xSemaphoreTake(stats_mutex, portMAX_DELAY);
    
    bool found = (custom_safelist.find(domain) != custom_safelist.end());
    
    xSemaphoreGive(stats_mutex);
    return found;
}
