# CCC PRODUCT OFFERING MASTER

**Project:** Chuyện Chợ Chứng (CCC)  
**Status:** Product & commercial source of truth  
**Version:** 1.0  
**Date:** 2026-08-22  
**Audience:** Product, Engineering, Sales, Marketing, Customer Support, Content

---

## 1. Vai trò của tài liệu

Tài liệu này là nguồn chuẩn để trả lời các câu hỏi:

- CCC đang bán những gói nào?
- Mỗi gói được theo dõi bao nhiêu mã?
- Lượt đổi mã được tính ra sao?
- KPI toàn thị trường và dữ liệu chi tiết được hiển thị thế nào?
- VIP Day 100.000đ/24 giờ hoạt động ra sao?
- Nâng cấp, gia hạn, Grace Period và hết hạn được xử lý thế nào?
- Nội dung bán hàng và UI không được hứa quá quyền thực tế nào?

Nếu UI, code, nội dung hướng dẫn hoặc nội dung bán hàng mâu thuẫn với tài liệu này, phải dừng lại đối chiếu business rule trước khi phát hành.

---

# 2. Định vị sản phẩm

Chuyện Chợ Chứng không bán “mã thắng” hay khuyến nghị mua/bán.

CCC cung cấp một lớp **Stock Intelligence** giúp người dùng:

1. nhìn thấy sức nóng của thị trường;
2. theo dõi các mã họ quan tâm;
3. nhận biết sự hội tụ của 4 tín hiệu kỹ thuật CCC;
4. giảm công sức theo dõi thủ công;
5. mở rộng phạm vi theo dõi khi nhu cầu tăng.

Thông điệp nền:

> **Thị trường có gì đáng chú ý — và trong DS mã theo dõi của bạn đang có gì?**

CCC phải luôn phân biệt:

- **Toàn thị trường:** số lượng / bối cảnh tổng hợp.
- **DS mã theo dõi của bạn:** danh tính và dữ liệu kỹ thuật mà user được quyền xem theo gói.
- **Public Quote / Fundamental Research:** dữ liệu công khai theo contract riêng.

Không dùng từ “phạm vi” trong copy bán hàng hướng tới user nếu có thể diễn đạt tự nhiên bằng “DS mã theo dõi”, “quyền xem”, hoặc “toàn thị trường”.

---

# 3. Bậc thang sản phẩm hiện tại

| Sản phẩm | Giá hiện tại | DS mã theo dõi | Lượt đổi mã / tháng | Email | Telegram | Quyền kỹ thuật toàn thị trường |
|---|---:|---:|---:|---|---|---|
| FREE | 0đ | 10 | 3 | Không | Không | Không |
| BASIC | 100.000đ/tháng | 20 | 20 | Không | Không | Không |
| PLUS | 300.000đ/tháng | 50 | 50 | Có | Có | Không |
| PRO | 500.000đ/tháng | 100 | 100 | Có | Có | Không |
| FULL | 1.000.000đ/tháng | Không giới hạn | Không giới hạn | Có | Có | Có |
| VIP DAY | 100.000đ/24 giờ | Không thay DS nền | Không áp giới hạn trong thời gian VIP | Full feature tạm thời | Full feature tạm thời | Có trong 24 giờ |

> Giá và quyền hiện tại phản ánh cấu hình sản phẩm đang chốt ngày 22/08/2026. Khi giá thay đổi phải cập nhật tài liệu trước hoặc đồng thời với hệ thống.

---

# 4. FREE — gói tạo thói quen

FREE không phải demo rỗng. FREE phải đủ hữu ích để user hiểu giá trị CCC.

### Quyền chính

- DS mã theo dõi tối đa: **10 mã**.
- 7 ngày đầu để khởi tạo DS, không trừ lượt đổi.
- Sau 7 ngày: quota **3 mã ADD mới / chu kỳ tháng**.
- REMOVE không mất lượt.
- DS được giữ xuyên suốt; không reset hàng tháng.
- KPI Tổng quan vẫn hiển thị **số lượng toàn thị trường**.
- Chi tiết kỹ thuật chỉ hiển thị cho mã thuộc DS của user.

### Vai trò thương mại

FREE giúp user thấy đồng thời hai thứ:

1. “Thị trường hiện đang có bao nhiêu tín hiệu đáng chú ý?”
2. “Trong 10 mã mình chọn có bao nhiêu mã đang xuất hiện tín hiệu?”

Khoảng cách giữa hai con số tạo ra lý do tự nhiên để:

- thay đổi DS mã;
- mở rộng gói tháng;
- hoặc mua VIP Day khi cần xem toàn thị trường ngay.

---

# 5. BASIC / PLUS / PRO — mở rộng DS mã theo dõi

Các gói giới hạn mã tuân theo quy tắc:

> **Gói N mã → capacity N và quota ADD N mã mỗi chu kỳ tháng.**

### BASIC

- 20 mã.
- 20 lượt ADD / tháng.
- Phù hợp người theo dõi danh mục nhỏ hoặc một số nhóm ngành.

### PLUS

- 50 mã.
- 50 lượt ADD / tháng.
- Email + Telegram.
- Là gói trung tâm cho user muốn theo dõi tương đối rộng nhưng chưa cần toàn thị trường.

### PRO

- 100 mã.
- 100 lượt ADD / tháng.
- Email + Telegram.
- Phù hợp user theo dõi nhiều nhóm ngành / chiến lược.

### Nguyên tắc hiển thị

Cả BASIC / PLUS / PRO vẫn được thấy số lượng KPI toàn thị trường. Danh tính kỹ thuật ngoài DS không được tiết lộ.

---

# 6. FULL — quyền toàn thị trường dài hạn

FULL là gói dành cho user cần CCC thường xuyên và muốn bỏ giới hạn theo mã.

- Xem kỹ thuật toàn Scanner Universe.
- DS mã không giới hạn.
- Không giới hạn lượt ADD/REMOVE.
- Email + Telegram.
- Không áp logic setup/quota để giới hạn sử dụng.

FULL không được mô phỏng bằng một con số giả rất lớn trong database. Quyền không giới hạn phải được biểu diễn bằng entitlement rõ ràng.

---

# 7. VIP DAY — FULL tạm thời 24 giờ

## 7.1. Định nghĩa

VIP Day là **Temporary Full Access Entitlement**.

- Giá: **100.000đ**.
- Thời gian: **24 giờ kể từ khi kích hoạt / thanh toán thành công**.
- Quyền trong thời gian hiệu lực: tương đương FULL.

VIP Day **không phải subscription nền mới**.

## 7.2. Quy tắc overlay

Ví dụ user FREE:

`FREE → VIP DAY 24h → trở về FREE`

User PLUS:

`PLUS → VIP DAY 24h → trở về PLUS`

Trong mọi trường hợp, VIP Day không được:

- đổi `plan_id` của gói nền;
- reset quota gói nền;
- đổi ngày anchor;
- đổi ngày hết hạn gói nền;
- xóa hoặc thay DS mã theo dõi nền;
- tạo 7 ngày setup mới.

Hết 24 giờ, user trở lại **đúng trạng thái trước khi VIP bắt đầu**.

## 7.3. DS mã trong VIP Day

Trong VIP Day, user được xem toàn thị trường mà không cần đưa 800 mã vào DS.

DS nền vẫn được giữ nguyên để:

- tiếp tục cá nhân hóa;
- nhận lại đúng trạng thái sau VIP;
- tránh làm bẩn quota / lịch sử DS.

## 7.4. Vai trò thương mại

VIP Day phục vụ nhu cầu tức thời:

> “Hôm nay thị trường đang nóng, tôi muốn xem toàn bộ nhưng chưa muốn mua FULL tháng.”

Tỷ lệ giá có chủ ý:

- VIP Day: 100.000đ/ngày.
- FULL tháng: 1.000.000đ/tháng.

10 lần VIP Day tương đương giá FULL tháng, tạo điểm upsell tự nhiên cho user dùng thường xuyên.

---

# 8. KPI Tổng quan — nguyên tắc sản phẩm và bán hàng

Bốn KPI kỹ thuật trên Tổng quan luôn có thể cho user capped thấy **số lượng toàn thị trường**:

1. Đạt 4/4.
2. Từ 3 tín hiệu.
3. Từ 2 tín hiệu.
4. RVOL30 nổi bật.

Ví dụ:

> **Đạt 4/4**  
> **5 mã**  
> Toàn thị trường  
> **DS mã theo dõi của bạn: 0 mã**

Hoặc:

> **Từ 3 tín hiệu**  
> **36 mã**  
> Toàn thị trường  
> **DS mã theo dõi của bạn: 2 mã**

### Khi user click KPI

- Tổng số toàn thị trường vẫn được nhắc lại.
- Chỉ liệt kê danh tính + kỹ thuật các mã user có quyền xem.
- Không liệt kê ticker bị khóa.
- Nếu có 0 mã trong DS, dùng empty state giải thích thay vì bảng trắng.

Ví dụ:

> Thị trường hiện có 5 mã đạt 4/4 tín hiệu. Hiện chưa có mã nào trong DS mã theo dõi của bạn đạt điều kiện này.

CTA hợp lệ:

- `Quản lý DS mã theo dõi`
- `Mở rộng DS mã theo dõi`
- `Mở FULL 24 giờ · 100.000đ`

### Không được dùng dark pattern

- Không tạo số lượng giả.
- Không tạo khan hiếm giả.
- Không nói “sắp hết cơ hội”.
- Không hứa lợi nhuận.
- Không tiết lộ mã bị khóa để câu click.

Upsell phải dựa trên **dữ liệu thị trường thật tại thời điểm đó**.

---

# 9. DS mã theo dõi và lượt đổi

Business rule chi tiết nằm ở `CCC_WATCHLIST_MEMBERSHIP_RULES.md`.

Tóm tắt:

- DS giữ xuyên suốt gói.
- Chỉ quota đổi reset hàng tháng.
- ADD sau thời gian miễn phí = 1 lượt / mã.
- REMOVE = 0 lượt.
- Xóa rồi add lại = 1 lượt.
- FREE 10 mã / 3 lượt.
- Paid N mã / N lượt.
- FULL không giới hạn.

---

# 10. Nâng cấp

Khi nâng cấp:

- Giữ toàn bộ mã cũ.
- Ngày nâng cấp là anchor mới.
- Quota gói mới bắt đầu từ ngày nâng cấp.
- Phần capacity tăng thêm được bổ sung miễn phí trong 7 ngày.
- Không dùng 7 ngày nâng cấp để thay mã cũ miễn phí.

VIP Day không được xem là nâng cấp subscription và không áp quy tắc này.

---

# 11. Hạ gói

Không hạ gói giữa thời hạn.

Nếu user chọn gói thấp hơn, gói hiện tại tiếp tục đến hết thời hạn. Gói thấp hơn chỉ bắt đầu sau đó, với ngày bắt đầu mới của chính nó.

---

# 12. Gia hạn và Grace Period

Khi gói trả phí tới hạn:

- cho **2 ngày Grace Period**;
- giữ DS mã và quyền gói cũ trong Grace;
- không cấp quota chu kỳ mới trước khi thanh toán.

Nếu thanh toán trong Grace:

- tiếp tục gói;
- giữ anchor cũ;
- giữ DS;
- không có 7 ngày setup mới.

Nếu hết Grace không thanh toán:

- xóa DS trả phí;
- chuyển user về FREE mới;
- ngày chuyển về FREE là anchor mới;
- 7 ngày chọn lại 10 mã FREE;
- quota FREE = 3/tháng.

---

# 13. Quy tắc ngày 31

Nếu anchor = ngày 31 và tháng mục tiêu không có ngày 31, kỳ đó được đẩy sang **ngày 1 của tháng sau**.

Anchor logic vẫn là ngày 31 cho kỳ tiếp theo.

Ví dụ đã test:

`31/01 → 01/03 → 31/03 → 01/05`

---

# 14. Ma trận “market aggregate vs detail entitlement”

| Dữ liệu | FREE/BASIC/PLUS/PRO | FULL | VIP Day active |
|---|---|---|---|
| Số lượng KPI toàn thị trường | Có | Có | Có |
| Ticker ngoài DS từ KPI kỹ thuật | Không | Có | Có |
| Kỹ thuật mã trong DS | Có | Có | Có |
| Kỹ thuật toàn thị trường | Không | Có | Có |
| Public quote | Theo Public Contract | Theo Public Contract | Theo Public Contract |
| Fundamental Research | Public | Public | Public |

---

# 15. Funnel sản phẩm

Luồng chính:

`Guest / FREE → dùng 10 mã → mở rộng BASIC/PLUS/PRO → FULL`

Luồng nhu cầu tức thời:

`FREE / Paid capped → KPI thị trường nóng → VIP Day → trở lại gói nền`

Luồng user dùng VIP thường xuyên:

`nhiều VIP Day → FULL tháng`

VIP Day không phải để thay thế toàn bộ gói tháng; nó là cầu nối giữa nhu cầu tức thời và subscription dài hạn.

---

# 16. Nguyên tắc ngôn ngữ thương mại

Ưu tiên:

- “DS mã theo dõi”
- “Toàn thị trường”
- “Quyền xem kỹ thuật”
- “Lượt đổi mã”
- “Mở FULL 24 giờ”

Tránh copy khó hiểu:

- “scope”
- “entitlement” trong UI user
- “capacity” trong UI user
- “outside scope”
- quá nhiều thuật ngữ backend

---

# 17. Claims được phép và không được phép

### Được phép

- “Theo dõi tín hiệu thị trường.”
- “Scanner đang ghi nhận X mã đạt điều kiện.”
- “DS của bạn hiện có Y mã thuộc nhóm này.”
- “Mở toàn thị trường trong 24 giờ.”
- “Không cần thay đổi gói hiện tại.”

### Không được phép

- “Mã này chắc chắn tăng.”
- “Mua VIP để kiếm lợi nhuận.”
- “Tín hiệu đảm bảo thắng.”
- “Cơ hội cuối cùng” nếu không có sự kiện thật.

---

# 18. Implementation status

Tính đến 22/08/2026:

- Auth/Profile/Membership foundation: đã có.
- Watchlist DB + quota + RLS/RPC: đã có.
- VIP Day DB entitlement foundation: đã có.
- Overview entitlement RPC: đã có.
- VIP billing/payment activation: **chưa nối**.
- Email/Telegram delivery: triển khai ở phase tương ứng.

UI không được hiển thị nút “Mua thành công” hoặc kích hoạt VIP nếu billing chưa thực sự hoàn tất.
