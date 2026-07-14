#pragma once

#include <esp_http_server.h>

#ifdef __cplusplus
extern "C" {
#endif

// Khởi động Web Server
void web_server_start(void);
void web_server_stop(void);

// Đăng ký API Routes (web_server_api.cpp)
void register_api_routes(httpd_handle_t server);

// Đăng ký Static File Routes (web_server_static.cpp)
void register_static_routes(httpd_handle_t server);

#ifdef __cplusplus
}
#endif
