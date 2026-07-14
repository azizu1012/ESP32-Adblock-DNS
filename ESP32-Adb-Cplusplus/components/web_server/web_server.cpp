#include "web_server.h"
#include <esp_http_server.h>
#include <esp_log.h>
#include <esp_system.h>
#include <sys/param.h>

static const char *TAG = "Web_Server";
static httpd_handle_t server = NULL;

void web_server_start(void) {
    if (server != NULL) return;
    
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.stack_size = 8192; // Tăng stack size để tránh Stack Overflow
    
    // Tối ưu giống Python: Bật Keep Alive để tránh rớt kết nối
    config.keep_alive_enable = true;
    config.keep_alive_idle = 5;
    config.keep_alive_interval = 5;
    config.keep_alive_count = 3;
    
    // Tối ưu giống Python (Payload Cap): Chặn mỏm Header quá 4096 bytes để chống OOM
    // (Đã chuyển cấu hình max_req_hdr_len vào sdkconfig.defaults của ESP-IDF)
    
    config.max_uri_handlers = 12; // 8 route API + tĩnh
    config.max_open_sockets = 5;  // Giới hạn an toàn của ESP-IDF cho web server

    ESP_LOGI(TAG, "Đang khởi động Web Server trên C++...");
    if (httpd_start(&server, &config) == ESP_OK) {
        // Đăng ký Captive Portal (Redirect mọi request chưa biết về /setup)
        httpd_register_err_handler(server, HTTPD_404_NOT_FOUND, [](httpd_req_t *req, httpd_err_code_t err) -> esp_err_t {
            httpd_resp_set_status(req, "302 Found");
            httpd_resp_set_hdr(req, "Location", "/setup");
            httpd_resp_send(req, NULL, 0);
            return ESP_OK;
        });

        // Đăng ký các module
        register_api_routes(server);
        register_static_routes(server);
    }
}

void web_server_stop(void) {
    if (server) {
        httpd_stop(server);
        server = NULL;
    }
}
