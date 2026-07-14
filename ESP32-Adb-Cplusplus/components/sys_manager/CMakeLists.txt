idf_component_register(SRCS "wifi_manager.cpp" "led_indicator.cpp" "stats_tracker.cpp"
                    INCLUDE_DIRS "include"
                    REQUIRES nvs_flash esp_wifi lwip esp_netif driver json esp_timer spiffs)
