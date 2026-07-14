#include "web_server.h"
#include <esp_http_server.h>
#include <esp_log.h>
#include <sys/stat.h>
#include <string.h>

static const char *TAG = "Web_Static";
static const char *BASE_PATH = "/spiffs";

// Hàm phục vụ file tĩnh thông minh (Tự động nhận diện đuôi .gz)
static esp_err_t serve_file_handler(httpd_req_t *req) {
    char filepath[1024];
    
    // Điều hướng giống y hệt server_static.py
    if (strcmp(req->uri, "/") == 0) {
        snprintf(filepath, sizeof(filepath), "%s/index.html", BASE_PATH);
    } else if (strcmp(req->uri, "/setup") == 0) {
        snprintf(filepath, sizeof(filepath), "%s/setup.html", BASE_PATH);
    } else if (strcmp(req->uri, "/api/ui") == 0) {
        snprintf(filepath, sizeof(filepath), "%s/app.html.gz", BASE_PATH);
    } else {
        snprintf(filepath, sizeof(filepath), "%s%s", BASE_PATH, req->uri);
    }

    struct stat file_stat;
    if (stat(filepath, &file_stat) == -1) {
        ESP_LOGE(TAG, "File không tồn tại: %s", filepath);
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "File not found");
        return ESP_FAIL;
    }

    // Parse ETag (size-mtime)
    char file_etag[64];
    snprintf(file_etag, sizeof(file_etag), "\"%ld-%lld\"", (long)file_stat.st_size, (long long)file_stat.st_mtime);

    char req_etag[64];
    if (httpd_req_get_hdr_value_str(req, "If-None-Match", req_etag, sizeof(req_etag)) == ESP_OK) {
        if (strncmp(req_etag, file_etag, strlen(file_etag)) == 0) {
            httpd_resp_set_status(req, "304 Not Modified");
            httpd_resp_send(req, NULL, 0);
            return ESP_OK;
        }
    }

    // Set GZIP nếu đuôi file là .gz
    if (strstr(filepath, ".gz")) {
        httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
    }
    httpd_resp_set_hdr(req, "ETag", file_etag);
    
    FILE* fd = fopen(filepath, "r");
    if (!fd) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to read file");
        return ESP_FAIL;
    }

    char *chunk = (char *)malloc(1024);
    if (!chunk) {
        fclose(fd);
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Memory error");
        return ESP_FAIL;
    }

    size_t chunksize;
    do {
        chunksize = fread(chunk, 1, 1024, fd);
        if (chunksize > 0) {
            if (httpd_resp_send_chunk(req, chunk, chunksize) != ESP_OK) {
                free(chunk);
                fclose(fd);
                return ESP_FAIL;
            }
        }
    } while (chunksize != 0);

    free(chunk);
    fclose(fd);
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

void register_static_routes(httpd_handle_t server) {
    httpd_uri_t uri_root = { .uri = "/", .method = HTTP_GET, .handler = serve_file_handler, .user_ctx = NULL };
    httpd_uri_t uri_setup = { .uri = "/setup", .method = HTTP_GET, .handler = serve_file_handler, .user_ctx = NULL };
    httpd_uri_t uri_ui = { .uri = "/api/ui", .method = HTTP_GET, .handler = serve_file_handler, .user_ctx = NULL };
    
    httpd_register_uri_handler(server, &uri_root);
    httpd_register_uri_handler(server, &uri_setup);
    httpd_register_uri_handler(server, &uri_ui);
}
