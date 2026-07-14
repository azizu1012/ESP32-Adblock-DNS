#include "bloom_filter.h"
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "BloomFilter";

static FILE *s_bloom_file = NULL;
static SemaphoreHandle_t s_bloom_mutex = NULL;

// FNV-1a 64-bit hash function
static uint64_t fnv1a_64(const char* data) {
    uint64_t h = 0xCBF29CE484222325ULL;
    const uint64_t p = 0x100000001B3ULL;
    while (*data) {
        h = (h ^ (uint8_t)(*data)) * p;
        data++;
    }
    return h;
}

bool bloom_filter_init(const char* filepath) {
    if (s_bloom_mutex == NULL) {
        s_bloom_mutex = xSemaphoreCreateMutex();
    }
    if (s_bloom_file != NULL) return true;

    s_bloom_file = fopen(filepath, "rb");
    if (!s_bloom_file) {
        ESP_LOGE(TAG, "Không tìm thấy %s. Đang tự động tạo file trắng 1.2MB...", filepath);
        FILE *f_create = fopen(filepath, "wb");
        if (f_create) {
            uint8_t zero_buf[1024] = {0};
            int chunks = 1200004 / 1024;
            for (int i = 0; i < chunks; i++) {
                fwrite(zero_buf, 1, 1024, f_create);
            }
            int rem = 1200004 % 1024;
            if (rem > 0) fwrite(zero_buf, 1, rem, f_create);
            fclose(f_create);
            ESP_LOGI(TAG, "Đã tạo xong file Bloom Filter trắng!");
            s_bloom_file = fopen(filepath, "rb");
        }
    }

    if (!s_bloom_file) {
        ESP_LOGE(TAG, "Lỗi nghiêm trọng: Không thể tạo hoặc mở %s", filepath);
        return false;
    }

    ESP_LOGI(TAG, "Đã mở file Bloom Filter thành công!");
    return true;
}

void bloom_filter_deinit(void) {
    if (s_bloom_file != NULL) {
        fclose(s_bloom_file);
        s_bloom_file = NULL;
    }
    if (s_bloom_mutex != NULL) {
        vSemaphoreDelete(s_bloom_mutex);
        s_bloom_mutex = NULL;
    }
}


bool bloom_filter_check(const char* domain) {
    if (s_bloom_file == NULL || s_bloom_mutex == NULL) return false;

    // 1. Băm tên miền
    uint64_t h = fnv1a_64(domain);
    
    // 2. Tính chỉ mục block (18750 block, mỗi block 64 bytes)
    uint32_t block_idx = (h >> 32) % 18750;
    uint32_t h_low = h & 0xFFFFFFFF;
    
    // Đọc chính xác 64 byte của block đó (Giống hệt Python f.seek)
    uint8_t block[64];
    xSemaphoreTake(s_bloom_mutex, portMAX_DELAY);
    fseek(s_bloom_file, block_idx * 64, SEEK_SET);
    fread(block, 1, 64, s_bloom_file);
    xSemaphoreGive(s_bloom_mutex);
    
    // 3. Kiểm tra 8 bít băm (Kirsch-Mitzenmacher optimization)
    for (int i = 0; i < 8; i++) {
        uint32_t bit_pos = (h_low ^ (i * 0x5bd1e995)) % 512;
        uint32_t byte_pos = bit_pos / 8;
        uint8_t bit_mask = 1 << (bit_pos % 8);
        
        // Nếu có bất kỳ bit nào = 0, chắc chắn miền này không bị chặn
        if (!(block[byte_pos] & bit_mask)) {
            return false;
        }
    }
    
    // Nếu tất cả 8 bits = 1, miền bị chặn
    return true;
}

uint32_t bloom_filter_get_count(void) {
    if (s_bloom_file == NULL || s_bloom_mutex == NULL) return 0;
    
    xSemaphoreTake(s_bloom_mutex, portMAX_DELAY);
    // Đọc 4 byte cuối file (little-endian uint32) - giống hệt Python struct.unpack("<I")
    fseek(s_bloom_file, 0, SEEK_END);
    long size = ftell(s_bloom_file);
    uint32_t count = 0;
    if (size >= 4) {
        fseek(s_bloom_file, size - 4, SEEK_SET);
        fread(&count, 4, 1, s_bloom_file);
    }
    
    // Đưa con trỏ về đầu file để an toàn cho các tác vụ khác (dù mmap có thể không bị ảnh hưởng)
    fseek(s_bloom_file, 0, SEEK_SET);
    xSemaphoreGive(s_bloom_mutex);
    
    return count;
}
