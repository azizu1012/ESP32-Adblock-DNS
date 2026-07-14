idf_component_register(SRCS "web_server.cpp" "web_server_api.cpp" "web_server_static.cpp"
                    INCLUDE_DIRS "include"
                    REQUIRES esp_http_server spiffs esp_timer sys_manager)
