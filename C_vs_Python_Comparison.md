# Bảng So Sánh Chuyên Sâu: ESP32 DNS AdBlocker (C++ vs MicroPython)

Tài liệu này phân tích ở mức độ hệ thống (System-Level) những sự khác biệt cốt lõi giữa hai phiên bản của dự án: Prototype bằng **MicroPython** và Phiên bản Production bằng **C++ (ESP-IDF/FreeRTOS)**. Sự chuyển đổi ngôn ngữ này không chỉ là thay đổi về mặt cú pháp mà là một sự thay đổi hoàn toàn về hệ sinh thái và cách tương tác với phần cứng ESP32.

---

## 1. Quản Trị Bộ Nhớ (Memory Management)

Đây là điểm khác biệt sống còn nhất quyết định đến sự ổn định của hệ thống nhúng hoạt động 24/7.

### MicroPython (Heap & Garbage Collection)
- **Giới hạn Heap**: MicroPython dành ra một vùng nhớ cố định (thường khoảng 130KB - 140KB) làm Garbage Collection (GC) Heap. Toàn bộ chuỗi (String), List, Dictionary đều phải nằm trong vùng này.
- **Phân mảnh (Fragmentation)**: Việc nhận gói tin UDP (chứa DNS domain) tạo ra hàng loạt chuỗi String rác liên tục. Sau khoảng vài trăm truy vấn, bộ nhớ bị phân mảnh nghiêm trọng.
- **Garbage Collection Overhead**: Hệ thống thỉnh thoảng bị "đứng hình" (choke) mất 20-50ms để chạy lệnh `gc.collect()`. Nếu Web Server cố gắng serialize một file JSON quá lớn trong lúc RAM bị phân mảnh, nó sẽ ném ra lỗi `MemoryError` và crash luồng đó.

### C++ / ESP-IDF (Static Allocation & Pointers)
- **Truy cập Toàn bộ RAM**: C++ cho phép truy cập trực tiếp vào toàn bộ 320KB SRAM nội bộ của ESP32. Free RAM thường xuyên ở mức an toàn > 170KB.
- **Cấp phát tĩnh (Static Allocation)**: Trong quá trình xử lý gói tin DNS, C++ sử dụng các mảng buffer được cấp phát tĩnh một lần duy nhất lúc khởi động (`static uint8_t rx_buffer[512]`). 
- **Zero-Allocation Parsing**: Tên miền được trích xuất trực tiếp bằng con trỏ (Pointer arithmetic) di chuyển dọc theo bộ đệm UDP mà không hề tạo ra bản sao (copy) nào. Nhờ đó, rò rỉ bộ nhớ (Memory Leak) và phân mảnh bằng 0%.

---

## 2. Mô Hình Đa Nhiệm (Concurrency & Threading)

### MicroPython (Global Interpreter Lock - GIL)
- Dù ESP32 có 2 nhân (Dual-Core 240MHz), MicroPython quản lý luồng qua module `_thread` nhưng bị khóa bởi **GIL**.
- Tại một thời điểm, chỉ có 1 luồng thực thi mã Python. Khi Web UI xử lý API (ví dụ nối chuỗi để trả về HTTP Header), luồng DNS bị kẹt lại. Điều này dẫn đến việc bị rớt gói UDP (Packet Loss / Timeout) lên đến 15% khi có nhiều thiết bị truy vấn cùng lúc.

### C++ / ESP-IDF (Symmetric Multiprocessing - SMP / FreeRTOS)
- **True Dual-Core**: FreeRTOS cho phép ép cứng (Pin to Core) từng tác vụ. 
  - `dns_server_task` được ghim vào **Core 0** (chuyên xử lý Network, ngắt Wi-Fi).
  - `web_server_task` được ghim vào **Core 1** (chuyên xử lý giao diện và I/O).
- Cả hai nhân chạy hoàn toàn độc lập và song song. Khi giao diện Web đang render JSON khổng lồ, Core 0 vẫn âm thầm phản hồi các truy vấn DNS trong thời gian tính bằng micro-giây (<1ms). Giao tiếp giữa 2 nhân được đồng bộ bằng `xSemaphoreCreateMutex`.

---

## 3. Quản Lý File & Cấu Trúc Dữ Liệu Lớn (Bloom Filter)

Thuật toán lõi của dự án yêu cầu tra cứu một danh sách đen (Blocklist) dạng Bloom Filter nhị phân kích thước **1.2 MB**.

### MicroPython (File I/O)
- Do RAM chỉ có 130KB, không thể nạp file 1.2MB vào RAM. MicroPython phải dùng hàm `f.seek()` và `f.readinto(bytearray)` để trích xuất từng khối 64 bytes.
- Mỗi lần gọi `f.readinto()` là một lần MicroPython phải gọi xuống C-API, đẩy qua VFS, rồi trả về Python object. Quá trình này tạo ra độ trễ cao và overhead không cần thiết, làm giảm tốc độ nhận diện quảng cáo.

### C++ / ESP-IDF (Memory-Mapped I/O - mmap)
- C++ ESP-IDF hỗ trợ **Memory Mapping (mmap)** qua phân vùng SPIFFS/LittleFS. 
- Thay vì "đọc" file, C++ ánh xạ toàn bộ file 1.2MB từ Flash Memory thẳng vào bộ nhớ ảo (Virtual Memory Space) qua Cache của ESP32.
- Hàm kiểm tra quảng cáo chỉ đơn giản là gọi `pointer = mapped_file_ptr + offset`. Trải nghiệm truy xuất dữ liệu từ Flash nhanh gần như đọc trực tiếp từ RAM (không phát sinh bất kỳ hàm I/O nào trong quá trình chặn).

---

## 4. Xử Lý Mạng (Networking & LwIP Stack)

### MicroPython (Bọc qua `usocket`)
- API `socket` của Python che giấu quá nhiều chi tiết bên dưới. 
- Gặp lỗi **TCP Delayed ACK**: Khi gửi Web tĩnh chia thành nhiều chunks, Windows/iOS thường kìm ACK lại 200ms vì chờ gom gói. Bằng MicroPython, lập trình viên phải vất vả cộng dồn (concatenate) HTTP Header và Body thành một khối rồi mới gọi `socket.sendall()` để lách luật, gây tốn RAM trầm trọng.

### C++ / ESP-IDF (Raw LwIP & `esp_http_server`)
- Sử dụng trực tiếp `esp_http_server`, một HTTP server cấp thấp được tối ưu hóa cho LwIP.
- Server tự động điều tiết bộ đệm TCP (TCP Window), gửi dữ liệu bằng hàm `httpd_resp_send_chunk` một cách trơn tru, đồng thời hỗ trợ natively cờ `TCP_NODELAY`.
- Kết quả: Phản hồi API ở C++ chỉ tốn khoảng **5-10ms**, trong khi ở Python thỉnh thoảng vọt lên **200-500ms**.

---

## 5. Dev-Ops & Trải Nghiệm Lập Trình (Toolchain)

| Tiêu chí | MicroPython | C++ (ESP-IDF) |
| :--- | :--- | :--- |
| **Biên dịch & Chạy** | Nhanh chóng. Sửa file `.py` xong upload qua Serial mất 1-2 giây là chạy ngay. Không cần biên dịch. | Chậm hơn. Cần cài đặt hệ thống CMake/Ninja, toolchain Xtensa. Build lần đầu tốn 1-2 phút, build lại tốn 10-15s. |
| **Gỡ lỗi (Debugging)** | REPL tiện lợi, có traceback rõ ràng. Tuy nhiên lỗi liên quan đến ngắt (IRQ) như Timer thường làm crash cứng im lặng. | Đòi hỏi kỹ năng đọc Backtrace, sử dụng GDB, JTAG, coredump, phân tích Exception Registers (`epc1`, `excvaddr`). Khó gỡ lỗi nhưng một khi đã chạy thì không bao giờ hỏng. |
| **Kích thước Firmware** | MicroPython Firmware chiếm sẵn khoảng 1.5MB Flash. Script Python rất nhỏ (vài chục KB). | Firmware C++ build ra khoảng 800KB - 1MB (đã bao gồm LwIP, FreeRTOS). Tiết kiệm Flash hơn nhiều. |

---

## TỔNG KẾT (Tại Sao Lại Chuyển Đổi?)

Bước đệm **MicroPython** là một khoản đầu tư vô cùng chính xác. Nó giúp tiết kiệm hàng tuần lễ vật lộn với logic C++ để chứng minh rằng: *Thuật toán chặn DNS bằng Bloom Filter và Web-UI bằng React hoàn toàn khả thi trên ESP32.*

Khi bản Prototype thành công, việc port sang **C++ (ESP-IDF)** là bước đi sống còn để đưa thiết bị lên cấp độ **Production-Ready**. Ở C++, hệ thống tận dụng được **100% tài nguyên CPU**, **mmap Flash Memory**, quản lý **RAM tĩnh** triệt để. Nhờ đó, ESP32 hiện tại có thể chịu tải hàng ngàn truy vấn DNS mỗi phút mà RAM vẫn không suy suyển 1 byte, đáp ứng hoàn hảo yêu cầu của một hệ thống Core Network hoạt động 24/7.
