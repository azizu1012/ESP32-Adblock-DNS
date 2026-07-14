#include "dns_optimizer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "esp_netif.h"
#include <string.h>
#include <sys/time.h>

static const char *TAG = "DNS_Optimizer";

char g_upstream_ip[16] = "1.1.1.1";
int g_upstream_rtt = 15;
static SemaphoreHandle_t s_upstream_mutex = NULL;

void dns_optimizer_get_upstream(char* out_ip, int* out_rtt) {
    if (s_upstream_mutex == NULL) {
        s_upstream_mutex = xSemaphoreCreateMutex();
    }
    xSemaphoreTake(s_upstream_mutex, portMAX_DELAY);
    strcpy(out_ip, g_upstream_ip);
    if (out_rtt) *out_rtt = g_upstream_rtt;
    xSemaphoreGive(s_upstream_mutex);
}

void dns_optimizer_set_upstream(const char* ip, int rtt) {
    if (s_upstream_mutex == NULL) {
        s_upstream_mutex = xSemaphoreCreateMutex();
    }
    xSemaphoreTake(s_upstream_mutex, portMAX_DELAY);
    strcpy(g_upstream_ip, ip);
    g_upstream_rtt = rtt;
    xSemaphoreGive(s_upstream_mutex);
}


static int measure_rtt(const char* ip) {
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) return 999999;
    
    struct timeval tv;
    tv.tv_sec = 0;
    tv.tv_usec = 300000; // 300ms timeout
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    
    struct sockaddr_in dest_addr;
    memset(&dest_addr, 0, sizeof(dest_addr));
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(53);
    inet_pton(AF_INET, ip, &dest_addr.sin_addr);
    
    // DNS query cho google.com
    const uint8_t query[] = {
        0xaa, 0xbb, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x06, 'g', 'o', 'o', 'g', 'l', 'e',
        0x03, 'c', 'o', 'm', 0x00, 0x00, 0x01, 0x00, 0x01
    };
    
    struct timeval t0, t1;
    gettimeofday(&t0, NULL);
    sendto(sock, query, sizeof(query), 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    
    uint8_t rx_buffer[128];
    int len = recvfrom(sock, rx_buffer, sizeof(rx_buffer), 0, NULL, NULL);
    gettimeofday(&t1, NULL);
    close(sock);
    
    if (len > 2 && rx_buffer[0] == 0xaa && rx_buffer[1] == 0xbb) {
        return (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_usec - t0.tv_usec) / 1000;
    }
    return 999999;
}

static void optimize_task(void *pvParameter) {
    // Chờ 5 giây cho WiFi kết nối xong rồi đo ngay lần đầu
    vTaskDelay(pdMS_TO_TICKS(5000));
    
    while (1) {
        
        // Danh sách toàn diện giống Python: 1.1.1.1, 8.8.8.8, 9.9.9.9, 1.0.0.1, 8.8.4.4
        const char* candidates[6] = {"1.1.1.1", "8.8.8.8", "9.9.9.9", "1.0.0.1", "8.8.4.4", NULL};
        
        char dhcp_dns[16] = {0};
        esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        if (netif) {
            esp_netif_dns_info_t dns;
            if (esp_netif_get_dns_info(netif, ESP_NETIF_DNS_MAIN, &dns) == ESP_OK) {
                if (dns.ip.type == ESP_IPADDR_TYPE_V4) {
                    esp_ip4addr_ntoa(&dns.ip.u_addr.ip4, dhcp_dns, sizeof(dhcp_dns));
                    candidates[5] = dhcp_dns;
                }
            }
        }
        
        int best_rtt = 999999;
        char best_ip[16] = {0};
        strcpy(best_ip, g_upstream_ip);
        
        ESP_LOGI(TAG, "Bắt đầu Optimize Upstream...");
        for (int i = 0; i < 6; i++) {
            if (!candidates[i]) continue;
            int r1 = measure_rtt(candidates[i]);
            if (r1 < 999999) {
                int r2 = measure_rtt(candidates[i]);
                int rtt = (r1 + r2) / 2;
                ESP_LOGI(TAG, " - %s: %d ms", candidates[i], rtt);
                if (rtt < best_rtt) {
                    best_rtt = rtt;
                    strcpy(best_ip, candidates[i]);
                }
            } else {
                ESP_LOGI(TAG, " - %s: timeout", candidates[i]);
            }
        }
        
        if (best_rtt < 999999) {
            ESP_LOGI(TAG, "Chọn DNS nhanh nhất: %s (%d ms)", best_ip, best_rtt);
            // Thread-Safe Swap (Zero-Downtime)
            dns_optimizer_set_upstream(best_ip, best_rtt);
        }
        
        // Chờ 5 phút rồi quét lại
        vTaskDelay(pdMS_TO_TICKS(5 * 60 * 1000));
    }
}

void dns_optimizer_init(void) {
    if (s_upstream_mutex == NULL) {
        s_upstream_mutex = xSemaphoreCreateMutex();
    }
    // Đo vòng đầu tiên lúc khởi động luôn, sau đó mới vào vòng lặp chờ
    xTaskCreatePinnedToCore(optimize_task, "dns_opt_task", 3072, NULL, 2, NULL, tskNO_AFFINITY);
}
