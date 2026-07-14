# Báo Cáo Chi Tiết Thông Số Phần Cứng & Firmware ESP32

*Bản báo cáo này được tổng hợp từ dữ liệu nội soi bằng công cụ cấp thấp `esptool` trực tiếp vào vi mạch (silicon) và thông số từ lõi hệ điều hành MicroC++.*

## 1. Dữ Liệu Phần Cứng Vật Lý (Hardware Silicon)
- **Dòng chip (Chip Type):** `ESP32-D0WD-V3 (revision v3.1)` *(Đây là dòng chip lõi kép hiệu năng rất cao, phiên bản V3 đã sửa nhiều lỗi bảo mật và ổn định hơn thế hệ cũ).*
- **Các tính năng gốc (Features):** Wi-Fi, Bluetooth, Dual Core + LP (Low Power) Core.
- **Tốc độ tối đa trên phần cứng:** `240 MHz` *(Hiện tại firmware đang hãm lại ở mức 160 MHz để tiết kiệm điện, nhưng có thể bung sức mạnh lên 240 MHz bất cứ lúc nào).*
- **Thạch anh dao động (Crystal Freq):** `40 MHz`
- **Địa chỉ MAC gốc (Wi-Fi):** `b0:cb:d8:cb:b6:a0`

## 2. Thông Tin Bộ Nhớ Vật Lý (Flash Memory)
- **Hãng sản xuất chip nhớ (Manufacturer ID):** `5e`
- **Tổng dung lượng chip nhớ (Physical Flash Size):** `4 MB` (Đây là dung lượng phần cứng thực tế hàn trên board mạch).
- **Phân vùng lưu trữ dữ liệu (LittleFS Partition):** `2 MB` *(Phần này được cắt ra từ 4MB ở trên để làm ổ cứng lưu trữ file `blocked.bin` và HTML. Đã dùng 1.3MB, còn dư 720KB để hệ thống xoay xở wear-leveling).*

## 3. Thông Tin Hệ Điều Hành (Firmware & RAM)
- **Hệ điều hành:** MicroC++ `v1.28.0` (Ngày build: 06/04/2026).
- **Tổng RAM cấp phát (GC Heap):** `~ 151.3 KB`
- **Tình trạng RAM hiện tại:** Chỉ tiêu tốn `43.7 KB` cho toàn bộ core DNS và Web, còn trống thênh thang `107.5 KB`.

> [!NOTE]
> **Đánh giá tổng thể:** Mạch của bạn là phiên bản ESP32 tiêu chuẩn 4MB vô cùng mạnh mẽ, không bị cắt giảm (chip D0WD-V3 lõi kép). Tổng dung lượng bộ nhớ vật lý 4MB hoàn toàn dư dả cho các bản cập nhật Firmware sau này, và 2MB phân vùng lưu trữ đã đáp ứng quá tốt cho danh sách chặn quảng cáo dung lượng lớn.
