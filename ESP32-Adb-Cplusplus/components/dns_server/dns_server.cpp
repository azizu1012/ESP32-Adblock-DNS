#include "dns_server.h"
#include "bloom_filter.h"
#include "dns_optimizer.h"
#include "gct_verifier.h"
#include "sys_manager.h"
#include "stats_tracker.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "lwip/sockets.h"
#include <string.h>
#include <ctype.h>
#include <fcntl.h>
#include <arpa/inet.h>

static const char *TAG = "DNS_Server";
static const int DNS_PORT = 53;

// --- BLOCKING LISTS ---
static const char* SAFELIST[] = {
    "adwords.google.com", "adidas.com",
    "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com",
    "s.youtube.com", "video-stats.l.google.com", "clients4.google.com", "clients1.google.com",
    "android.clients.google.com", "connectivitycheck.gstatic.com",
    "msftconnecttest.com", "msftncsi.com",
    "captive.apple.com", "gsp1.apple.com",
    "spclient.wg.spotify.com", "apresolve.spotify.com"
};

static const char* SAFELIST_SUFFIX[] = {
    // TikTok / ByteDance
    "tiktok.com", "tiktokv.com", "tiktokcdn.com", "byteoversea.com", "ibytedtos.com", "ibyteimg.com",
    // Shopee & ShopeeFood & Lazada & Tiki
    "shopee.vn", "shopee.com", "shopeemobile.com", "shopeesz.com", "susercontent.com", "shopeefood.vn", "foody.vn", "now.vn",
    "lazada.vn", "lazcdn.com", "alicdn.com", "lazada.com", "sendo.vn", "senimg.com",
    "tiki.vn", "tikicdn.com", "tiki.com.vn",
    // Zalo & VN E-wallets / Banks
    "zalo.me", "zadn.vn", "zaloapp.com", "zalo.vn", "momo.vn", "mservice.io", "mservice.com.vn", "zalopay.vn", "vnpay.vn",
    // Meta (Facebook/Instagram/Messenger/WhatsApp)
    "fbcdn.net", "cdninstagram.com", "facebook.com", "instagram.com", "messenger.com", "whatsapp.com", "whatsapp.net",
    // Google Services & YouTube CDNs
    "googlevideo.com", "ytimg.com", "ggpht.com", "googleapis.com", "gstatic.com", "googleusercontent.com", "gvt1.com", "gvt2.com",
    // Apple & App Store CDNs
    "apple.com", "icloud.com", "cdn-apple.com", "mzstatic.com",
    // Grab, Gojek, Be
    "grab.com", "grabtaxi.com", "gojek.com", "go-jek.com", "be.com.vn",
    // Streaming
    "netflix.com", "nflximg.net", "nflxvideo.net", "nflxso.net", "nflxext.com", "spotify.com", "scdn.co", "fptplay.vn", "fptplay.net", "vieon.vn", "zingmp3.vn", "zmdcdn.me", "nhaccuatui.com", "nixcdn.com",
    // Social & Captcha
    "twimg.com", "twitter.com", "x.com", "reddit.com", "redditmedia.com", "redditstatic.com", "discord.com", "discordapp.com", "discordapp.net", "pinimg.com",
    "telegram.org", "viber.com", "recaptcha.net", "hcaptcha.com",
    // Gaming
    "roblox.com", "rbxcdn.com", "mihoyo.com", "hoyoverse.com", "starrails.com", "zenlesszonezero.com", "cognosphere.com", "yuanshen.com",
    "kurogames.com", "kurogame.com", "hypergryph.com", "yostar.com", "hg-cdn.com", "arknights.global",
    "steampowered.com", "steamcommunity.com", "steamgames.com", "valvesoftware.com",
    "riotgames.com", "valorant.com", "epicgames.com", "unrealengine.com", "ea.com", "ubi.com", "ubisoft.com",
    // Misc
    "vnecdn.net", "update.microsoft.com", "windowsupdate.com"
};

static const char* KEYWORDS[] = {
    "telemetry", "analytics", "adserver", "adsystem", "doubleclick", "adcolony", "applovin", "popunder"
};

// Hàm trích xuất tên miền từ DNS UDP payload (Zero-copy)
static bool parse_dns_domain(const uint8_t *payload, int len, char *out_domain, int max_len, uint16_t *out_qtype) {
    if (len < 12) return false;
    int offset = 12; // Bỏ qua DNS Header
    int out_idx = 0;
    while (offset < len) {
        uint8_t label_len = payload[offset++];
        if (label_len == 0) break; // Hết domain
        // Nếu là con trỏ nén (Compression pointer), bỏ qua vì Query thường không bị nén ở câu hỏi đầu tiên
        if ((label_len & 0xC0) == 0xC0) return false; 
        
        if (out_idx + label_len + 1 >= max_len) return false; // Tràn bộ đệm
        
        for (int i = 0; i < label_len; i++) {
            if (offset >= len) return false;
            out_domain[out_idx++] = tolower(payload[offset++]);
        }
        out_domain[out_idx++] = '.';
    }
    if (out_idx > 0) out_domain[out_idx - 1] = '\0'; // Xóa dấu chấm cuối
    else out_domain[0] = '\0';

    if (offset + 4 <= len) {
        *out_qtype = (payload[offset] << 8) | payload[offset+1];
    } else {
        *out_qtype = 1;
    }
    return true;
}

// Kiểm tra các lớp chặn
static bool is_domain_blocked(const char* domain) {
    // 0. Dynamic Safelist (GCT - Tạm tha)
    if (is_domain_in_safelist_dyn(domain)) return false;

    // 1. Hardcoded Safelist
    for (int i = 0; i < sizeof(SAFELIST)/sizeof(SAFELIST[0]); i++) {
        if (strcmp(domain, SAFELIST[i]) == 0) return false;
    }
    // 2. Safelist Suffix
    for (int i = 0; i < sizeof(SAFELIST_SUFFIX)/sizeof(SAFELIST_SUFFIX[0]); i++) {
        const char *suffix = SAFELIST_SUFFIX[i];
        int d_len = strlen(domain);
        int s_len = strlen(suffix);
        if (d_len >= s_len) {
            if (strcmp(domain + d_len - s_len, suffix) == 0) {
                if (d_len == s_len || domain[d_len - s_len - 1] == '.') return false;
            }
        }
    }
    // 3. Heuristics (ad.*)
    if (strncmp(domain, "ad", 2) == 0) {
        if (domain[2] == 's' && domain[3] == '.') return true;
        if (isdigit((unsigned char)domain[2])) return true;
    }
    // 4. Keywords
    for (int i = 0; i < sizeof(KEYWORDS)/sizeof(KEYWORDS[0]); i++) {
        if (strstr(domain, KEYWORDS[i]) != NULL) return true;
    }
    // 5. Bloom Filter (Kiểm tra mảng 1.2MB trong bộ nhớ dùng mmap)
    if (bloom_filter_check(domain)) return true;

    return false;
}

// Chế tạo DNS Block Response giả (A -> 0.0.0.0, AAAA -> ::)
static int build_block_response(uint8_t *payload, int len, uint16_t qtype) {
    if (len < 12) return 0;
    // Đổi Cờ thành Standard Query Response
    payload[2] = 0x81;
    payload[3] = 0x80;
    // Set Answer Count = 1
    payload[6] = 0x00;
    payload[7] = 0x01;
    
    // Tìm điểm cuối của Question
    int offset = 12;
    while (offset < len && payload[offset] != 0) {
        offset += payload[offset] + 1;
    }
    offset += 1; // Bỏ qua 0x00
    offset += 4; // Bỏ qua QTYPE và QCLASS

    // Thêm Answer (16 bytes cho IPv4, 28 bytes cho IPv6)
    if (qtype == 0x001C) { // AAAA
        const uint8_t answer[] = {
            0xC0, 0x0C, 
            0x00, 0x1C, 
            0x00, 0x01, 
            0x00, 0x00, 0x01, 0x2C, 
            0x00, 0x10, 
            0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 // :: (IPv6)
        };
        memcpy(payload + offset, answer, sizeof(answer));
        return offset + sizeof(answer);
    } else { // A
        uint8_t ip_bytes[4] = {0,0,0,0};
        
        // Nếu đang ở AP Mode (Chưa có WiFi), Redirect Captive Portal về 192.168.4.1
        if (wifi_is_ap_mode()) {
            ip_bytes[0] = 192; ip_bytes[1] = 168; ip_bytes[2] = 4; ip_bytes[3] = 1;
        }

        uint8_t answer[] = {
            0xC0, 0x0C, 
            0x00, 0x01, 
            0x00, 0x01, 
            0x00, 0x00, 0x01, 0x2C, 
            0x00, 0x04, 
            ip_bytes[0], ip_bytes[1], ip_bytes[2], ip_bytes[3]
        };
        memcpy(payload + offset, answer, sizeof(answer));
        return offset + sizeof(answer);
    }
}

// Cấu trúc để quản lý Pending Queries (Async Forwarding)
struct pending_query_t {
    uint16_t client_tx_id;
    struct sockaddr_storage client_addr;
    socklen_t client_len;
    bool active;
    uint64_t timestamp_ms; // thời điểm gửi, dùng cho timeout cleanup
};

static struct pending_query_t pending_queries[32];
static uint16_t proxy_tx_id = 0;
static const uint64_t PENDING_TIMEOUT_MS = 3000; // 3s timeout cho pending query

static void dns_server_task(void *pvParameters) {
    // 1. Khởi tạo Sockets
    int local_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    int up_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    
    if (local_sock < 0 || up_sock < 0) {
        ESP_LOGE(TAG, "Lỗi tạo socket");
        vTaskDelete(NULL);
        return;
    }
    
    // Set Non-blocking
    fcntl(local_sock, F_SETFL, O_NONBLOCK);
    fcntl(up_sock, F_SETFL, O_NONBLOCK);

    struct sockaddr_in dest_addr;
    memset(&dest_addr, 0, sizeof(dest_addr));
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_port = htons(DNS_PORT);
    
    if (bind(local_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) < 0) {
        ESP_LOGE(TAG, "Lỗi bind Port 53");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in upstream_addr;
    memset(&upstream_addr, 0, sizeof(upstream_addr));
    upstream_addr.sin_family = AF_INET;
    upstream_addr.sin_port = htons(53);
    // Lưu ý: UPSTREAM_IP thay bằng biến toàn cục g_upstream_ip, cập nhật liên tục bên trong loop


    ESP_LOGI(TAG, "DNS Server Async Proxy đang chạy.");
    uint8_t buffer[512];

    while (1) {
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(local_sock, &readfds);
        FD_SET(up_sock, &readfds);
        
        int max_sd = (local_sock > up_sock) ? local_sock : up_sock;
        struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
        
        int activity = select(max_sd + 1, &readfds, NULL, NULL, &tv);
        
        // Periodic cleanup: dọn pending query quá hạn mỗi 1s khi select timeout
        if (activity == 0) {
            uint64_t now_ms = esp_timer_get_time() / 1000;
            for (int i = 0; i < 32; i++) {
                if (pending_queries[i].active &&
                    (now_ms - pending_queries[i].timestamp_ms) > PENDING_TIMEOUT_MS) {
                    pending_queries[i].active = false;
                }
            }
        }

        if (activity > 0) {
            // A. Có gói tin từ Điện thoại (Client)
            if (FD_ISSET(local_sock, &readfds)) {
                struct sockaddr_storage client_addr;
                socklen_t client_len = sizeof(client_addr);
                int len = recvfrom(local_sock, buffer, sizeof(buffer), 0, (struct sockaddr *)&client_addr, &client_len);
                if (len > 12) {
                    char domain[256];
                    uint16_t qtype;
                    if (parse_dns_domain(buffer, len, domain, sizeof(domain), &qtype)) {
                        // 1. Chế độ Captive Portal (Mất mạng -> Redirect All)
                        if (wifi_is_ap_mode()) {
                            int resp_len = build_block_response(buffer, len, qtype);
                            sendto(local_sock, buffer, resp_len, 0, (struct sockaddr *)&client_addr, client_len);
                            continue;
                        }

                        // 2. Chế độ AdBlocker bình thường
                        if (is_domain_blocked(domain)) {
                            // Gửi vào hàng đợi GCT để kiểm tra xem có Block oan không
                            gct_queue_domain(domain);
                            
                            // Trả về IP rỗng (0.0.0.0)
                            int resp_len = build_block_response(buffer, len, qtype);
                            sendto(local_sock, buffer, resp_len, 0, (struct sockaddr *)&client_addr, client_len);
                            
                            // Ghi lại thống kê chặn
                            char ip_str[16];
                            struct sockaddr_in* addr_in = (struct sockaddr_in*)&client_addr;
                            inet_ntop(AF_INET, &(addr_in->sin_addr), ip_str, INET_ADDRSTRLEN);
                            stats_record_query(domain, true, ip_str);
                            // Báo hiệu LED ngay khi block — không đợi GCT
                            led_trigger_block_blink();
                        } else {
                            // Ghi nhận cho phép
                            char ip_str[16];
                            struct sockaddr_in* addr_in = (struct sockaddr_in*)&client_addr;
                            inet_ntop(AF_INET, &(addr_in->sin_addr), ip_str, INET_ADDRSTRLEN);
                            stats_record_query(domain, false, ip_str);

                            // Chuyển tiếp lên Upstream
                            pending_queries[proxy_tx_id].client_tx_id = (buffer[0] << 8) | buffer[1];
                            pending_queries[proxy_tx_id].client_addr = client_addr;
                            pending_queries[proxy_tx_id].client_len = client_len;
                            pending_queries[proxy_tx_id].active = true;
                            pending_queries[proxy_tx_id].timestamp_ms = esp_timer_get_time() / 1000;
                            
                            buffer[0] = proxy_tx_id >> 8;
                            buffer[1] = proxy_tx_id & 0xFF;
                            
                            // Cập nhật Dynamic Upstream (Optimizer tráo đổi)
                            char active_ip[16];
                            dns_optimizer_get_upstream(active_ip, NULL);
                            inet_pton(AF_INET, active_ip, &upstream_addr.sin_addr);
                            sendto(up_sock, buffer, len, 0, (struct sockaddr *)&upstream_addr, sizeof(upstream_addr));
                            
                            proxy_tx_id = (proxy_tx_id + 1) & 0x1F;
                        }
                    }
                }
            }

            // B. Có gói tin trả lời từ Upstream
            if (FD_ISSET(up_sock, &readfds)) {
                int len = recvfrom(up_sock, buffer, sizeof(buffer), 0, NULL, NULL);
                if (len > 12) {
                    uint16_t upstream_tx = (buffer[0] << 8) | buffer[1];
                    int slot = upstream_tx % 32;
                    if (pending_queries[slot].active) {
                        // Khôi phục TX ID của Client
                        buffer[0] = pending_queries[slot].client_tx_id >> 8;
                        buffer[1] = pending_queries[slot].client_tx_id & 0xFF;
                        
                        // Bắn trả lại điện thoại
                        sendto(local_sock, buffer, len, 0, (struct sockaddr *)&pending_queries[slot].client_addr, pending_queries[slot].client_len);
                        pending_queries[slot].active = false;
                    }
                }
            }
        }
    }
}

void dns_server_start(void) {
    bloom_filter_init("/spiffs/blocked.bin");
    
    // Khởi tạo Optimizer và GCT
    dns_optimizer_init();
    gct_verifier_init();
    
    xTaskCreatePinnedToCore(dns_server_task, "dns_server", 4096, NULL, 5, NULL, 0);
}
