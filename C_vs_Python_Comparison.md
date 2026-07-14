# Bảng So Sánh Chi Tiết: ESP32 DNS AdBlocker (C++ vs Python)

Dự án này đã trải qua hai giai đoạn phát triển chính: Prototype ban đầu bằng **MicroPython** và Phiên bản Production bằng **C++ (ESP-IDF)**. Dưới đây là bảng phân tích và so sánh chi tiết giữa hai phiên bản để thấy rõ được giới hạn của Python trên hệ thống nhúng và sức mạnh của C++.

---

## 1. Kiến trúc và Đa tiến trình (Concurrency)

| Tiêu chí | Phiên bản Python (MicroPython) | Phiên bản C++ (ESP-IDF / FreeRTOS) |
| :--- | :--- | :--- |
| **Mô hình luồng** | Bị giới hạn bởi **GIL (Global Interpreter Lock)**. Các luồng (`_thread`) không thực sự chạy song song hoàn toàn. | Khai thác tối đa kiến trúc **Dual-Core**. Web UI và DNS Server chạy hoàn toàn độc lập trên 2 nhân. |
| **Độ trễ khi tải nặng** | Có hiện tượng "chặn" (blocking) khi Web Server xử lý JSON lớn, khiến truy vấn DNS bị rớt (timeout). | Không bao giờ nghẽn. Task DNS được ghim cứng vào Core 0 với mức độ ưu tiên cao, Web Server chạy ở Core 1. |
| **Quản lý RAM** | **Garbage Collection (GC)** phải chạy liên tục (gây khựng) do RAM 130KB nhanh chóng bị lấp đầy bởi các chuỗi String tạm. | Quản lý bộ nhớ thủ công và tĩnh (Static Allocation). Không bao giờ cấp phát động trong vòng lặp DNS. Chống phân mảnh tuyệt đối. |

---

## 2. Hiệu năng Truy vấn DNS (Benchmarking)

> *Kết quả được đo bằng công cụ `benchmark_dns.py` mô phỏng hàng trăm request liên tục.*

| Tiêu chí | Phiên bản Python (MicroPython) | Phiên bản C++ (ESP-IDF / FreeRTOS) |
| :--- | :--- | :--- |
| **RAM tiêu thụ (Nền)** | ~40-50 KB Free RAM. Gần như cạn kiệt. | ~180-200 KB Free RAM. Rất dư dả. |
| **Tốc độ Resolve** | Trung bình **15 - 25 req/sec**. Nếu quá tải sẽ gây Exception. | Khả năng đáp ứng > **300+ req/sec**. Gần như bằng 0 độ trễ phần mềm. |
| **Độ ổn định khi tải** | Rớt (Timeout) khoảng 10-15% nếu gửi dồn dập 500 requests do LwIP TCP backlog và GC. | Xử lý hoàn hảo 500 requests liên tục (0% timeout), RAM không hề suy suyển. |
| **Đọc Bloom Filter** | Phải dùng cấu trúc `f.readinto(bytearray)` kết hợp `gc.collect()`. Khá chậm do overhead Python. | Tận dụng cơ chế **Memory Mapped (mmap)** qua VFS. Đọc file 1.2MB nhanh như đọc biến trong RAM. |

---

## 3. Hoạt động của Web UI và API

| Tiêu chí | Phiên bản Python (MicroPython) | Phiên bản C++ (ESP-IDF / FreeRTOS) |
| :--- | :--- | :--- |
| **Gửi file tĩnh** | Dễ bị tràn RAM (`MemoryError`) khi gửi file > 10KB. Phải chia chunk rất thủ công và dễ đứt kết nối. | HTTP Server (`esp_http_server`) dùng `httpd_resp_send_chunk` gửi file mượt mà. Hỗ trợ ETag và GZIP cấp thấp. |
| **Lỗi TCP Delayed ACK** | Phải nối (concatenate) HTTP Header và Body Chunk đầu tiên bằng tay để lách phạt 200ms của Windows/iOS. | Được xử lý chuẩn mực bởi stack mạng LwIP gốc của ESP-IDF với tùy chọn `TCP_NODELAY`. Độ trễ API < 10ms. |
| **JSON Serialization** | Render cục JSON lịch sử chặn lớn mất đến 300-500ms, làm treo chip tạm thời. | Thư viện `cJSON` xử lý cực nhanh dưới nền C, tạo chuỗi API trả về trong chưa tới 10ms. |

---

## 4. Quản lý Hệ thống và Phần cứng

| Tiêu chí | Phiên bản Python (MicroPython) | Phiên bản C++ (ESP-IDF / FreeRTOS) |
| :--- | :--- | :--- |
| **LED Heartbeat** | Dùng Timer phần cứng (`Timer(0)`) bị xung đột ngầm do cấp phát bộ nhớ trong ngắt (IRQ). Dễ crash im lặng. | Task RTOS thuần túy (`vTaskDelay`). An toàn tuyệt đối, chớp nháy siêu mượt không độ trễ. |
| **Tính toán Uptime/Tick** | Hay gặp lỗi tràn số khi đồng bộ NTP làm đồng hồ nhảy vọt (Năm 2000 -> 2026). Trừ Ticks bị lỗi. | Dùng `esp_timer_get_time()` đếm vi giây độc lập hoàn toàn với NTP. Ổn định vĩnh viễn. |
| **An toàn hệ thống (WDT)** | Watchdog Timer hoạt động qua Software layer. Có lúc chip treo không tự reset được. | Hardware Watchdog Timer kết hợp Task Watchdog của FreeRTOS, bảo vệ đa tầng chống treo cứng. |

---

## Kết luận

- **Python (MicroPython)**: Là công cụ cực kỳ tuyệt vời để **R&D (Nghiên cứu và Phát triển)**. Nó giúp chúng ta thiết kế luồng (Flow), thử nghiệm thuật toán Bloom Filter và hoàn thiện UI Web App trong thời gian ngắn mà không phải bận tâm về Toolchain C/C++.
- **C++ (ESP-IDF)**: Là đích đến bắt buộc cho **Production (Sản phẩm thực tế)**. Hệ thống DNS Blocker là một thiết bị Core Network (Mạng cốt lõi) chạy 24/7. C++ cung cấp tính ổn định tuyệt đối, không có Garbage Collection, làm chủ RAM tĩnh và chạy đa nhân thực sự.

Sự kết hợp giữa *Tạo Prototype bằng Python* và *Hiện thực hóa bằng C++* là quy trình lý tưởng cho dự án nhúng phức tạp này!
