cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(PARTITION_TABLE_CUSTOM ON)
set(PARTITION_TABLE_CUSTOM_FILENAME "partitions.csv")
project(esp32_adblock_dns)

# Tự động đóng gói toàn bộ thư mục web của Python sang ổ đĩa SPIFFS của C++
spiffs_create_partition_image(spiffs ../ESP32-Adb-Python/firmware/web FLASH_IN_PROJECT)
