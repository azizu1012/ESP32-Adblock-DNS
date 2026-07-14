# Kế hoạch Nâng cấp: Cụm DNS Sinkhole Dự phòng Cao

**Dự án:** ESP32 AdBlocker DNS \
**Loại tài liệu:** Architecture Decision Record (ADR) \
**Phiên bản:** 1.0 \
**Ngày:** 2026-07-10 \
**Trạng thái:** Chờ phần cứng (ESP32-S3 R8F16)

---

## I. Vấn đề thật sự là gì?

Hệ thống đang chạy tốt. Chặn hơn 230.000 tên miền, tự xoay DNS khi mạng nghẽn, tự phục hồi khi WiFi rớt. Không có gì để phàn nàn về mặt chức năng.

Nhưng nó có một lỗ hổng mang tính cấu trúc: **chỉ có một thiết bị duy nhất đứng giữa toàn bộ mạng và Internet**. Nếu nó chết — dù chỉ 5 giây để reboot — thì trong 5 giây đó, mọi người trong nhà đều thấy "không có mạng". Đây không phải lỗi phần mềm, đây là giới hạn vật lý của kiến trúc đơn điểm.

Giải pháp hiển nhiên: thêm thiết bị thứ hai. Nhưng "thêm một con nữa" là câu nói đơn giản che đậy một đống câu hỏi khó:

- Hai thiết bị phối hợp kiểu gì?
- Dữ liệu nào chia sẻ, dữ liệu nào giữ riêng?
- Khi một con chết, con kia có tự gánh được không?
- Người dùng quản lý ở đâu — một nơi hay hai nơi?

Tài liệu này đi qua từng câu hỏi, có lập luận cho mỗi quyết định.

---

## II. Hai thiết bị, hai tầm vóc

Điều đầu tiên cần nói rõ: thiết bị thứ hai không phải bản sao. Chúng ta ghép đôi hai cỗ máy có năng lực chênh lệch khổng lồ.

| Thông số | Thiết bị A — Green (hiện tại) | Thiết bị B — Blue (mới) |
|---|---|---|
| Xung nhịp | 160 MHz | 240 MHz |
| RAM khả dụng | 132 KB | **8.192 KB (8 MB)** — gấp ~62 lần |
| Flash | 4 MB | 16 MB |
| Vai trò dự kiến | Lính dự bị (Secondary) | Lính chính (Primary) |
| IP tĩnh | .234 | .235 |

Con số "gấp 62 lần RAM" không chỉ là "nhanh hơn" — nó mở ra cách xử lý hoàn toàn khác. Thiết bị A buộc phải đọc dữ liệu từ ổ lưu trữ mỗi lần kiểm tra (chậm). Thiết bị B có đủ chỗ để nhét toàn bộ dữ liệu vào RAM và truy xuất trực tiếp (nhanh gấp hàng trăm lần). Chi tiết ở Mục V.

---

## III. Mô hình phối hợp

### Ba lựa chọn, hai bị loại

**Lựa chọn 1 — Chính-Phụ (Active-Passive):**
B chạy chính, A ngủ, chỉ thức khi B chết.

*Tại sao loại:* DNS dùng giao thức UDP — không giữ trạng thái. Router cấp cho mọi thiết bị trong nhà hai địa chỉ DNS. Khi DNS chính không trả lời, hệ điều hành tự hỏi DNS phụ. Cơ chế dự phòng này đã có sẵn trong mọi OS hiện đại — không cần thiết bị A "thức dậy" gì cả.

Hơn nữa, nếu A ngủ, một số OS (đặc biệt iOS) sẽ ghi nhận DNS phụ "chết" → giảm điểm tin cậy → chuyển sang dùng DNS nhà mạng → vô hiệu hóa bộ lọc. Để A nhàn rỗi là lãng phí tài nguyên và tạo ra rủi ro ngược.

**Lựa chọn 2 — Song song đồng nhất (Active-Active Symmetric):**
Cả hai cùng chạy, cùng dùng chung một thuật toán.

*Tại sao loại:* "Đồng nhất" nghĩa là ép thiết bị B (8 MB RAM) phải xử lý giống thiết bị A (132 KB RAM) — tức là đọc từ ổ lưu trữ mỗi lần tra cứu. Giống như có hai nhân viên, một người đọc nhanh, một người phải tra từ điển — nhưng bắt cả hai đều tra từ điển "cho công bằng". Phí phạm năng lực đã đầu tư.

**Lựa chọn 3 — Song song dị thể (Active-Active Asymmetric) ✓:**
Cả hai cùng chạy, cùng trả lời đúng, nhưng bằng cách khác nhau phù hợp năng lực từng thiết bị.

*Tại sao chọn:*
- Tận dụng 100% tài nguyên cả hai thiết bị
- Router tự phân bổ tải qua DHCP (B gánh ~70-90%, A gánh phần còn lại)
- Dự phòng tự nhiên: một con chết → con kia gánh toàn bộ, không cần can thiệp

### Sơ đồ tổng quan

```
                   ROUTER / ONT
         ┌─────────────────────────────┐
         │  DNS chính : .235  (B)      │
         │  DNS phụ   : .234  (A)      │
         └─────────┬─────────┬─────────┘
                   │         │
          70-90%   │         │   10-30%
                   │         │
                   ▼         ▼
         ┌─────────────┐  ┌─────────────┐
         │ Thiết bị B  │  │ Thiết bị A  │
         │ (Blue)      │  │ (Green)     │
         │             │  │             │
         │ Tra cứu     │  │ Tra cứu     │
         │ từ RAM      │  │ từ Flash    │
         │ (siêu nhanh)│  │ (chậm hơn)  │
         └─────────────┘  └─────────────┘
```

---

## IV. Dữ liệu: cái gì chia sẻ, cái gì giữ riêng

Đây là phần quyết định sống còn. Chia sẻ quá nhiều → tốn tài nguyên, tăng rủi ro. Chia sẻ quá ít → hai thiết bị lệch pha, người dùng bối rối.

### 4.1. Bảng phân loại

| Loại dữ liệu | Kích thước | Tần suất thay đổi | Cần đồng bộ? |
|---|---|---|---|
| Danh sách chặn (Bloom Filter) | 1.2 MB, tĩnh | Rất hiếm (cập nhật thủ công) | **Không** — nạp thủ công vào từng thiết bị |
| Danh sách cho phép (Safelist tùy chỉnh) | < 2 KB | Rất hiếm (< 1 lần/ngày) | **Có** ← duy nhất cần đồng bộ |
| Danh sách phục hồi tự động (GCT) | Biến đổi, chỉ RAM | Liên tục | **Không** — mỗi thiết bị tự vận hành |
| Thống kê & Log | < 5 KB/thiết bị | Liên tục | **Không** — trình duyệt tự gom |
| Cấu hình mạng | < 1 KB | Cực hiếm | **Không** — mỗi thiết bị cấu hình riêng |

**Phát hiện quan trọng:** Trong toàn bộ dữ liệu, chỉ có đúng **một loại duy nhất** cần đồng bộ: danh sách cho phép do người dùng tự thêm. Kích thước nhỏ, thay đổi cực hiếm. Bài toán đồng bộ phân tán — vốn là một trong những bài toán khó nhất của ngành — bị thu hẹp xuống còn: truyền một danh sách text nhỏ giữa hai thiết bị trong cùng mạng LAN.

### 4.2. Cơ chế đồng bộ: Đẩy khi có sự kiện

Có hai trường phái: **Kéo định kỳ (Polling)** và **Đẩy khi có sự kiện (Event-Driven Push)**.

Phân tích bằng số:
- Thay đổi thực tế: trung bình 1 lần/ngày = 1 sự kiện / 86.400 giây
- Nếu Polling mỗi 10 giây: 8.640 lần hỏi/ngày → 8.639 lần nhận câu trả lời rỗng
- Tỷ lệ hữu ích: **0,012%**

99.988% công sức Polling là vô ích. Mỗi lần tốn chu kỳ xử lý, chiếm module vô tuyến, tạo nhiệt — trên thiết bị chạy 24/7 với tài nguyên hạn chế. Không thể biện minh.

→ Chọn Push. Chi phí chỉ phát sinh khi có sự kiện thực sự. Trong 99.999% thời gian, hệ thống đồng bộ hoàn toàn im lặng.

### 4.3. Chống vòng lặp chết (Broadcast Storm)

Khi A đẩy thông báo sang B, nếu B cũng được lập trình "khi có thay đổi thì đẩy sang anh em", B sẽ đẩy ngược lại A. A lại đẩy sang B. Vòng lặp vô hạn → cạn kiệt tài nguyên → sập.

```
   Không có nhận diện nguồn gốc:

   A ──đẩy──▶ B ──đẩy──▶ A ──đẩy──▶ B ──đẩy──▶ ...
   (vòng lặp vô hạn → hệ thống sập)
```

Giải pháp: mỗi thông điệp mang theo **ngữ cảnh nguồn gốc** — nó đến từ người dùng (gốc) hay từ thiết bị anh em (phái sinh).

```
   Có nhận diện nguồn gốc:

   Người dùng ──▶ A: "Cho phép x.com"
                  │
                  ├── A lưu vào bộ nhớ
                  │
                  └── A đẩy sang B kèm nhãn "phái sinh"
                                  │
                                  ├── B lưu vào bộ nhớ
                                  └── B thấy nhãn "phái sinh"
                                      ──▶ DỪNG. Không đẩy tiếp.

   Chuỗi kết thúc sau đúng 2 bước. Vòng lặp bị triệt tiêu.
```

### 4.4. Khi đồng bộ thất bại

Mạng LAN có thể gián đoạn bất cứ lúc nào (nhiễu sóng, thiết bị đang reboot...). Nếu thông điệp bị rớt, hai thiết bị sẽ có dữ liệu khác nhau — hiện tượng gọi là **Phân liệt não (Split-Brain)**.

**Tại sao chấp nhận được?**

Theo Định lý CAP (Brewer, 2000): khi mạng bị chia cắt, chỉ chọn được một trong hai — nhất quán tuyệt đối hoặc sẵn sàng phục vụ. Chúng ta chọn sẵn sàng: cả hai thiết bị tiếp tục phục vụ DNS ngay cả khi không liên lạc được với nhau. Lý do:

- Thao tác thay đổi danh sách cho phép cực hiếm (< 1 lần/ngày)
- Hệ điều hành cache DNS 5-10 phút → sự lệch pha ngắn hạn gần như không cảm nhận được

**Hai lớp phòng thủ:**

**Lớp 1 — Hàng đợi thử lại (Retry Queue):**

Khi đẩy thất bại → bỏ thông điệp vào hàng đợi nội bộ. Thử gửi lại theo trễ tăng dần:

| Lần thử | Chờ | Lý do |
|---|---|---|
| 1 | 2 giây | Có thể chỉ là nhiễu thoáng qua |
| 2 | 4 giây | Nếu vẫn thất bại, có thể thiết bị kia đang bận |
| 3 | 8 giây | Bắt đầu giãn ra để tránh chiếm dụng vô tuyến |
| 4 | 16 giây | Tình hình có vẻ nghiêm trọng hơn |
| 5 | 32 giây | Nếu vẫn không được, chờ Full Sync |

Hàng đợi giới hạn 5 mục (< 300 bytes RAM). Kể cả thiết bị kia chết vĩnh viễn, hàng đợi đầy cũng không gây tràn bộ nhớ.

Tại sao trễ tăng dần thay vì gửi lại liên tục? Nếu gửi mỗi 2 giây → 30 lần/phút chiếm dụng vô tuyến. Trễ tăng dần giảm xuống chỉ 1-2 lần/phút sau vài vòng, giải phóng băng thông cho DNS.

**Lớp 2 — Đồng bộ toàn phần khi khởi động (Full Sync on Boot):**

Mỗi khi một thiết bị bật nguồn, việc đầu tiên nó làm là hỏi thiết bị anh em: "Gửi cho tao toàn bộ danh sách cho phép hiện tại". Sau đó merge (lấy hợp — union) với danh sách cục bộ.

Cơ chế này đảm bảo: dù chuyện gì xảy ra trong lúc offline, khi bật lại, dữ liệu được hàn gắn tự động. Không cần can thiệp thủ công.

---

## V. Khai thác sự chênh lệch phần cứng

Phần này là nơi kiến trúc tạo ra giá trị thật sự từ khoản đầu tư phần cứng.

### 5.1. Bài toán tra cứu

Mỗi truy vấn DNS, hệ thống phải tra tên miền trong danh sách chặn (1.2 MB dữ liệu). Thao tác này xảy ra hàng chục lần mỗi giây — tốc độ tra cứu quyết định trải nghiệm người dùng.

### 5.2. Hai chiến lược

| Chỉ số | Thiết bị A (đọc từ Flash) | Thiết bị B (đọc từ RAM) |
|---|---|---|
| Cách hoạt động | Tính vị trí → nhảy đến → đọc 64 bytes từ ổ lưu trữ | Tính vị trí → đọc thẳng từ mảng byte trong RAM |
| Tốc độ mỗi truy vấn | 1-3 mili-giây | 1-5 **micro**-giây |
| Chênh lệch | — | **Nhanh gấp 500-1.000 lần** |
| RAM tiêu tốn | 64 bytes (cố định) | 1.2 MB (chiếm 15% của 8 MB, còn 6.8 MB trống) |
| Thông lượng tối đa | ~300-1.000 query/giây | Hàng trăm nghìn query/giây |
| Phù hợp vai trò | Secondary (gánh 10-30%) | Primary (gánh 70-90%) |

Minh họa trực quan chênh lệch tốc độ:

```
  Thiết bị A (Flash) : ████████████████████████████████  1-3 ms
  Thiết bị B (RAM)   : █                                 1-5 μs

  Chênh lệch: ~500 - 1.000 lần
```

### 5.3. Một giao diện, hai cách thực hiện

Tầng Logic phía trên (kiểm tra tên miền qua 5 lớp lọc) hoàn toàn không thay đổi. Nó chỉ gọi một hàm duy nhất — "tra cứu tên miền, trả lời Có hoặc Không". Sự khác biệt Flash/RAM được giấu hoàn toàn bên dưới.

```
       ┌────────────────────────────┐
       │ Logic kiểm tra tên miền    │ ◄── Không thay đổi
       │ (5 lớp lọc hiện tại)      │
       └─────────────┬──────────────┘
                     │
                     ▼
       "Tra cứu trong danh sách chặn"  ◄── Giao diện chung
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
        Đọc từ Flash   Đọc từ RAM      ◄── Tự chọn theo phần cứng
        (Thiết bị A)   (Thiết bị B)
```

Thiết bị tự nhận biết khi bật nguồn: nếu có PSRAM > 2 MB → nạp dữ liệu vào RAM. Nếu không → giữ nguyên cơ chế Flash cũ. Một điều kiện duy nhất, không phức tạp hóa bất kỳ Logic nào.

### 5.4. Bảo vệ tuổi thọ ổ lưu trữ

Flash có giới hạn vật lý: ~100.000 lần ghi/xóa mỗi sector trước khi hỏng.

Giải pháp: **gom lệnh ghi (Write Coalescing)**. Thay vì ghi ngay mỗi khi có thay đổi, hệ thống chỉ đánh dấu "có thay đổi" trong RAM. Ghi thật sự chỉ xảy ra khi đã qua ít nhất 60 giây kể từ lần ghi cuối.

Ước tính tuổi thọ (trường hợp xấu nhất — ghi 1 lần/phút):
- 525.600 lần ghi/năm
- Flash 4 MB ÷ 4 KB/sector = 1.024 sector, Wear Leveling phân bổ đều
- Tuổi thọ: (100.000 × 1.024) ÷ 525.600 ≈ **195 năm**
- Thực tế (ghi < 1 lần/ngày): vượt xa 1.000 năm

→ Ổ lưu trữ không bao giờ là rào cản.

---

## VI. Giao diện quản trị hợp nhất

### 6.1. Ai gom dữ liệu?

Người dùng muốn một trang web duy nhất xem thống kê cả hai thiết bị. Vậy ai sẽ gom?

**Phương án A — Thiết bị gom:** Một thiết bị đóng vai trung tâm, lấy dữ liệu từ thiết bị kia, trộn lại, gửi cho trình duyệt.

*Tại sao loại:* Quá trình nhận và phân tích dữ liệu từ thiết bị kia đòi hỏi cấp phát bộ nhớ liên tục. Trên vi điều khiển đa luồng, điều này kích hoạt Bộ thu gom rác — đóng băng toàn bộ luồng, kể cả luồng DNS. Kết quả: mất gói DNS, người dùng thấy mạng chậm. Bắt thiết bị vừa phục vụ DNS vừa phân tích dữ liệu là quá sức khi Heap đã chạy 4-5 luồng song song.

**Phương án B — Trình duyệt gom ✓:** Trình duyệt mở hai đường kết nối song song đến cả hai thiết bị, tự gom, tự hiển thị.

*Tại sao chọn:*
- Trình duyệt có hàng GB RAM và CPU GHz — thừa sức trộn 100 dòng Log trong < 0.1 ms
- Hai thiết bị chỉ phơi bày dữ liệu cục bộ — không thêm tải
- Mở rộng tự nhiên: thêm thiết bị thứ 3, thứ 4 → chỉ cần thêm IP vào danh sách fetch, Backend không sửa gì

### 6.2. Cách trộn dữ liệu

| Dạng dữ liệu | Cách trộn | Độ phức tạp |
|---|---|---|
| Con số đơn (tổng truy vấn, tổng chặn) | Cộng: A + B | Tức thì |
| Danh sách có thứ tự (50 Log gần nhất) | Trộn hai danh sách đã sắp xếp (Two-pointer Merge) | 100 phép so sánh, < 0.1 ms |

Mỗi dòng Log gắn nhãn [A] hoặc [B] để biết truy vấn đó qua thiết bị nào.

### 6.3. Bố cục giao diện dự kiến

```
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │  [Tổng truy vấn]   [Tổng chặn]      [Tỷ lệ chặn]       │
  │    12.453            8.291             66,6%             │
  │   (A:3k + B:9k)    (A:2k + B:6k)                        │
  │                                                          │
  │  ┌────────────────────────┬─────────────────────────┐    │
  │  │ Thiết bị B (Chính)     │ Thiết bị A (Dự bị)      │    │
  │  │ 240 MHz  │  52°C       │ 160 MHz  │  48°C         │    │
  │  │ RAM: 1.8 / 8.0 MB      │ RAM: 62 / 132 KB         │    │
  │  │ Uptime: 3d 14h         │ Uptime: 7d 2h            │    │
  │  └────────────────────────┴─────────────────────────┘    │
  │                                                          │
  │  ┌──────────────────────────────────────────────────┐    │
  │  │ Nhật ký Truy vấn (Gộp từ cả hai thiết bị)       │    │
  │  ├──────────────────────────────────────────────────┤    │
  │  │ 0s  [B]  google.com          CHO PHÉP            │    │
  │  │ 0s  [A]  doubleclick.net     CHẶN (từ khóa)      │    │
  │  │ 1s  [B]  facebook.com        CHO PHÉP            │    │
  │  │ 2s  [B]  ads.yahoo.com       CHẶN (heuristic)    │    │
  │  │ 3s  [A]  cdn.jsdelivr.net    CHO PHÉP            │    │
  │  └──────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────┘
```

---

## VII. Ma trận kịch bản lỗi

Kiến trúc tốt không chỉ mô tả lúc mọi thứ ổn — nó phải trả lời: hệ thống hỏng bằng cách nào, và tự phục hồi ra sao?

| Kịch bản | Phản ứng | Mức độ |
|---|---|---|
| Thiết bị B chết (lính chính sập) | OS tự chuyển sang A trong vài trăm ms. Không cần can thiệp. | Thấp (tự phục hồi) |
| Thiết bị A chết (dự bị sập) | B vẫn phục vụ 100%. Gần như không ai nhận ra. | Rất thấp |
| Cả hai chết (mất điện) | Mất DNS. Nhưng mất điện = Router cũng chết = mạng sập trước DNS. | Hiếm |
| Mạng giữa hai thiết bị đứt | Cả hai tiếp tục DNS độc lập. Safelist có thể lệch tạm thời → Full Sync khi reboot. | Thấp (tự hàn gắn) |
| Push đồng bộ thất bại | Vào Retry Queue. Trễ tăng dần 2s→4s→8s→16s→32s. Queue đầy → Full Sync khi thiết bị kia sống lại. | Rất thấp |
| Cập nhật firmware | Cập nhật từng thiết bị một. Con còn lại tiếp tục phục vụ → zero downtime. | Không gián đoạn |
| Hỏng Flash (Wear-out) | Write Coalescing giảm tần suất ghi. Tuổi thọ ước tính > 195 năm. | Không đáng lo |

---

## VIII. Lộ trình triển khai

| Giai đoạn | Nội dung | Ghi chú |
|---|---|---|
| **1. Nền tảng** | Cho phép mỗi thiết bị biết địa chỉ thiết bị anh em qua cấu hình | Trang Setup cho phép nhập IP Peer |
| **2. Đồng bộ** | Xây cơ chế đẩy sự kiện cho Safelist, kèm Retry Queue và Full Sync on Boot | Phần khó nhất — cần test kỹ |
| **3. Tối ưu RAM** | Thiết bị B tự nhận biết PSRAM, nạp Bloom vào RAM lúc boot. A giữ nguyên | Một điều kiện duy nhất |
| **4. Giao diện** | Nâng cấp Dashboard: gọi song song 2 thiết bị, trộn dữ liệu, hiển thị hợp nhất | Chủ yếu là JavaScript |
| **5. Kiểm thử** | Nạp firmware → cấu hình chéo → test đồng bộ → test rút điện → test phục hồi | Checklist cụ thể khi triển khai |

---

## IX. Giới hạn & hướng mở

### Giới hạn thừa nhận

- **Nhất quán cuối cùng, không phải tức thời.** Trong vài giây sau khi thay đổi Safelist, hai thiết bị có thể có dữ liệu khác nhau. Đây là đánh đổi có chủ đích để giữ tính sẵn sàng.

- **Thiết kế cho đúng 2 thiết bị.** Nếu mở rộng lên 3+, cơ chế Push điểm-điểm cần thay bằng Gossip Protocol hoặc Coordinator trung tâm.

- **Không có bầu chọn thủ lĩnh (Leader Election).** Cả hai hoàn toàn ngang hàng. Không có "nguồn sự thật duy nhất" — Full Sync on Boot là cách giải quyết thực dụng.

### Hướng mở (khi B đã ổn định)

- **6.8 MB RAM còn trống** trên B có thể dùng làm DNS Response Cache — cache kết quả upstream, giảm tải nhà mạng, tăng tốc phân giải cho tên miền hay hỏi lặp lại.

- **16 MB Flash** cho phép lưu nhật ký truy vấn dài hạn (hàng tuần thay vì 50 dòng), phục vụ phân tích xu hướng và phát hiện bất thường.

---

*Tài liệu sẽ được cập nhật khi ESP32-S3 Blue sẵn sàng.*
