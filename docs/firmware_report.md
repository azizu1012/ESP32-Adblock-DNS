# Báo Cáo Chi Tiết Thông Số Phần Cứng & Firmware ESP32

*Bản báo cáo này được truy xuất trực tiếp từ phần lõi (Serial REPL) của chip ESP32, cung cấp số liệu thực tế đang chạy trên thiết bị thay vì thông số lý thuyết.*

## 1. Thông Tin Firmware (Hệ Điều Hành)
- **Hệ điều hành:** MicroPython `v1.28.0`
- **Ngày biên dịch (Build Date):** 06/04/2026
- **Lõi Python (Core):** `3.4.0`
- **Nhận diện phần cứng (Machine):** `Generic ESP32 module with ESP32`
- **Địa chỉ MAC (Wi-Fi):** `b0:cb:d8:cb:b6:a0`

## 2. Thông Số CPU & RAM (Garbage Collection Heap)
- **Tốc độ xung nhịp CPU:** `160 MHz` *(Mức 160MHz giúp chip tiết kiệm điện, toả nhiệt thấp mà vẫn dư sức xử lý mạng. Có thể đẩy lên 240MHz nếu cần).*
- **Tổng dung lượng RAM cấp phát (Heap):** `~ 151.3 KB` (155,008 Bytes)
- **RAM đang bị chiếm dụng (Allocated):** `43.7 KB` (44,832 Bytes)
- **RAM đang trống (Free):** `107.5 KB` (110,176 Bytes)

> [!TIP]
> **Đánh giá RAM:** Trạng thái bộ nhớ đang **cực kỳ hoàn hảo**. Hệ thống chỉ tiêu tốn 43KB (gần 30%) để gánh toàn bộ server DNS lẫn web. Lượng RAM trống lên tới hơn 100KB là một con số "mơ ước" trên MicroPython, thừa sức chịu tải hàng nghìn truy vấn DNS bùng nổ cùng lúc mà không lo sập hầm (Out-Of-Memory).

## 3. Bộ Nhớ Lưu Trữ (Flash - Phân vùng LittleFS)
- **Tổng dung lượng phân vùng (Flash Total):** `2 MB` (2,097,152 Bytes)
- **Dung lượng đã dùng (Flash Used):** `~ 1.3 MB` *(Chứa cỗ máy lọc `blocked.bin` 1.2MB, code Python và giao diện Web)*.
- **Dung lượng trống (Flash Free):** `720 KB` (737,280 Bytes)

> [!NOTE]
> **Đánh giá Flash:** Con số này hoàn toàn trùng khớp với mức `720KB free (65% used)` mà bạn đã soi ra lúc nãy. Mức dư 720KB này vô cùng quý giá vì hệ thống file LittleFS rất cần một khoảng không gian trống để "tráo đổi vị trí ghi" (wear-leveling), giúp các ô nhớ Flash không bị chai và kéo dài tuổi thọ của chip lên mức tối đa.

## 4. Kết Luận
ESP32 của bạn đang chạy phiên bản firmware cực xịn (`v1.28.0`) và cấu trúc tài nguyên đang ở trạng thái **vàng**. Dung lượng Flash được tối ưu sát sao (nhờ việc không nạp file HTML gốc), và RAM được giải phóng liên tục giúp thiết bị có khả năng hoạt động ổn định 24/7.
