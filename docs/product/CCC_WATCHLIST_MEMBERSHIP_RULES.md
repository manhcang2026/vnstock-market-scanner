# CCC Watchlist & Membership Rules

**Project:** Chuyện Chợ Chứng / Stock Market Scanner  
**Status:** Business logic locked  
**Version:** 1.0  
**Date:** 2026-08-22  
**Purpose:** Tài liệu chuẩn hóa logic Watchlist, quota đổi mã, chu kỳ gói, nâng cấp, gia hạn, hết hạn và gói FREE/FULL. Tài liệu này dùng làm nguồn tham chiếu cho database, RLS/RPC, frontend, billing, alert và nội dung hướng dẫn người dùng sau này.

---

## 1. Nguyên tắc cốt lõi

### 1.1. Scanner Universe và Watchlist là hai lớp hoàn toàn khác nhau

- **Scanner Universe** là danh sách mã cố định do backend/code quản lý.
- Hệ thống tiếp tục quét, tính toán và lưu dữ liệu cho toàn bộ Scanner Universe.
- **Watchlist** chỉ là danh sách cá nhân của từng user.
- User thêm/xóa mã khỏi Watchlist **không được làm thay đổi Scanner Universe**.
- Frontend không được dùng thao tác Watchlist để xóa, tắt quét hoặc ngừng lưu dữ liệu của bất kỳ mã nào trong Scanner Universe.

Ví dụ:

- Backend đang quét 800 mã.
- User FREE chỉ có Watchlist 10 mã.
- Backend vẫn quét đủ 800 mã.
- User FREE chỉ được xem/theo dõi 10 mã thuộc quyền Watchlist của mình.

---

## 2. Các khái niệm cần dùng thống nhất

### 2.1. Watchlist Capacity

Số lượng mã tối đa mà user được phép giữ đồng thời trong Watchlist theo gói hiện tại.

Ví dụ:

- FREE: 10 mã.
- Gói 50: 50 mã.
- Gói 100: 100 mã.
- FULL: không giới hạn.

### 2.2. Monthly Symbol Change Quota

Số lượng **mã mới được ADD vào Watchlist** mà user được phép thực hiện trong một chu kỳ quota tháng sau giai đoạn khởi tạo miễn phí.

Quota:

- **Không tính theo số lần bấm Save.**
- **Không tính theo số lần chỉnh cả danh sách.**
- **Không trừ khi REMOVE mã.**
- **Chỉ trừ khi ADD một mã mới vào Watchlist**, trừ các trường hợp miễn phí được quy định trong tài liệu này.

### 2.3. Initial Setup Window

Khoảng thời gian **7 ngày** kể từ ngày bắt đầu một gói mới để user hoàn thiện Watchlist ban đầu mà **không bị trừ quota đổi mã**.

### 2.4. Grace Period

Khoảng thời gian **2 ngày sau khi gói trả phí hết hạn** để user hoàn tất thanh toán gia hạn.

Trong Grace Period:

- Giữ nguyên Watchlist.
- Giữ nguyên quyền xem của gói cũ.
- Giữ nguyên quyền cảnh báo của gói cũ.
- **Không cấp quota tháng mới** cho tới khi thanh toán gia hạn thành công.

### 2.5. Plan Anchor Date

Ngày mốc dùng để tính:

- chu kỳ quota tháng;
- ngày reset quota;
- kỳ gia hạn;
- các mốc thời gian của gói.

Đối với user mới: Plan Anchor Date = ngày bắt đầu gói.  
Đối với nâng cấp: Plan Anchor Date mới = ngày nâng cấp có hiệu lực.

---

## 3. Quy tắc gói FREE

Khi user tạo tài khoản mới và được kích hoạt gói FREE:

- Watchlist Capacity = **10 mã**.
- Initial Setup Window = **7 ngày**.
- Trong 7 ngày đầu:
  - được ADD miễn phí tối đa 10 mã;
  - ADD trong giai đoạn này không trừ quota.
- Sau 7 ngày:
  - mọi mã mới ADD vào Watchlist đều trừ quota;
  - kể cả Watchlist chưa đủ 10 mã.
- Monthly Symbol Change Quota = **3 mã/tháng**.
- Watchlist **không reset hàng tháng**.
- Chỉ quota đổi mã được reset theo chu kỳ tháng.

Ví dụ:

User tạo tài khoản ngày 10/08.

- Từ 10/08 đến hết thời gian setup 7 ngày: có thể thêm tối đa 10 mã miễn phí.
- Sau thời gian setup:
  - nếu đang có 7 mã và add thêm 1 mã mới → trừ 1 quota;
  - nếu xóa 1 mã → không trừ quota;
  - nếu add lại chính mã vừa xóa → trừ 1 quota.
- Đến kỳ reset tháng tiếp theo: Watchlist giữ nguyên, chỉ quota 3 mã được cấp lại.

---

## 4. Quy tắc gói trả phí giới hạn số mã

Đối với gói trả phí có capacity N mã:

- Watchlist Capacity = **N mã**.
- Monthly Symbol Change Quota = **N mã/tháng**.
- Initial Setup Window = **7 ngày**.
- Trong 7 ngày đầu:
  - được ADD miễn phí tối đa capacity của gói.
- Sau 7 ngày:
  - mọi ADD mới đều trừ quota;
  - kể cả Watchlist chưa dùng hết capacity.

Ví dụ gói 50:

- Capacity = 50.
- Quota đổi = 50 mã/tháng.
- User có 7 ngày đầu để chọn tối đa 50 mã miễn phí.
- Nếu hết 7 ngày mà mới chọn 35 mã:
  - 35 mã hiện tại vẫn giữ nguyên;
  - mã thứ 36 add sau đó sẽ trừ 1 quota;
  - không có chuyện 15 slot còn trống tiếp tục được add miễn phí.

---

## 5. Quy tắc ADD và REMOVE

### 5.1. REMOVE

REMOVE mã khỏi Watchlist:

- không trừ quota;
- không tạo lại quota;
- không hoàn quota đã dùng trước đó.

Ví dụ:

- User còn 8 quota.
- Xóa HPG.
- Quota vẫn = 8.

### 5.2. ADD

Sau thời gian miễn phí:

- mỗi mã mới được ADD vào Watchlist = **trừ 1 quota**;
- nếu ADD 5 mã trong một lần Save = trừ 5 quota;
- quota tính theo số mã ADD thực tế, không tính theo số request hay số lần Save.

### 5.3. Xóa rồi thêm lại cùng mã

Nếu đã hết thời gian miễn phí:

- REMOVE HPG → không trừ quota.
- ADD lại HPG → trừ 1 quota.

Không có ngoại lệ chỉ vì đó là mã đã từng nằm trong Watchlist.

### 5.4. Không đủ quota

Nếu một request muốn ADD nhiều mã hơn số quota còn lại:

- từ chối toàn bộ request ADD đó;
- không thực hiện một phần;
- không để Watchlist rơi vào trạng thái nửa thành công, nửa thất bại.

Ví dụ:

- Còn 2 quota.
- User muốn ADD 3 mã.
- Kết quả: reject toàn bộ 3 mã.

---

## 6. Watchlist không reset hàng tháng

Đây là nguyên tắc rất quan trọng.

Khi đến kỳ reset tháng:

- **KHÔNG xóa Watchlist.**
- **KHÔNG bắt user chọn lại Watchlist.**
- **KHÔNG đưa Watchlist về trạng thái ban đầu.**
- Chỉ reset bộ đếm quota đổi mã.

Ví dụ:

User gói 50 đang có 47 mã.

Đến ngày reset quota:

- 47 mã vẫn còn nguyên.
- Quota đổi được cấp lại theo gói.
- User tiếp tục sử dụng Watchlist hiện tại.

---

## 7. Chu kỳ reset quota

Quota reset theo **Plan Anchor Date**, không theo tháng dương lịch.

Ví dụ:

User bắt đầu gói ngày 10/08:

- kỳ tiếp theo: 10/09;
- tiếp theo: 10/10;
- v.v.

Nếu user mua gói 12 tháng:

- gói có thời hạn 12 tháng;
- nhưng quota vẫn reset **mỗi tháng** theo Plan Anchor Date;
- không chờ hết 12 tháng mới reset quota.

---

## 8. Quy tắc ngày 31

Nếu Plan Anchor Date là ngày 31:

- tháng nào có ngày 31 → dùng ngày 31;
- tháng nào không có ngày 31 → ưu tiên chuyển mốc sang **ngày 1 của tháng sau**;
- không dùng ngày cuối tháng làm mốc thay thế cố định.

Ví dụ:

Plan Anchor Date = 31/01.

- kỳ tháng 2 không có ngày 31;
- mốc tương ứng được tính sang **01/03**;
- nguyên tắc anchor vẫn dựa trên ngày 31 cho các kỳ tiếp theo;
- không biến vĩnh viễn Plan Anchor Date thành ngày 1.

Logic thực tế khi code phải bảo đảm không phát sinh reset quota hai lần hoặc bỏ sót kỳ quanh các tháng thiếu ngày 31.

---

## 9. Nâng cấp gói

Khi user nâng cấp từ gói thấp lên gói cao hơn:

### 9.1. Watchlist cũ

- Giữ nguyên toàn bộ các mã đang có.
- Không bắt user chọn lại từ đầu.
- Không xóa Watchlist.

### 9.2. Capacity tăng thêm

Ví dụ:

- Gói cũ: 50 mã.
- Gói mới: 100 mã.
- Capacity tăng thêm: 50 mã.

User được phép dùng **phần capacity tăng thêm** miễn phí trong **7 ngày kể từ ngày nâng cấp**.

Trong 7 ngày đó:

- được ADD miễn phí tối đa phần capacity tăng thêm;
- không trừ quota khi bổ sung phần capacity mới.

Sau 7 ngày:

- phần capacity tăng thêm nào chưa dùng hết không còn miễn phí;
- mọi ADD mới tiếp theo đều trừ quota.

### 9.3. Quota sau nâng cấp

Ngày nâng cấp trở thành **Plan Anchor Date mới**.

Kể từ ngày nâng cấp:

- quota áp dụng theo gói mới;
- chu kỳ quota tháng mới bắt đầu từ ngày nâng cấp;
- mốc reset tiếp theo tính từ ngày nâng cấp.

Ví dụ:

- User gói 50.
- Nâng lên gói 100 ngày 22/08.
- Từ 22/08:
  - capacity = 100;
  - quota theo gói 100;
  - anchor mới = 22;
  - reset tiếp theo = 22/09.

---

## 10. Hạ gói

Không hạ gói ngay khi gói hiện tại vẫn còn thời hạn.

Nếu user muốn chuyển xuống gói thấp hơn:

- gói hiện tại tiếp tục có hiệu lực đến hết hạn;
- user vẫn giữ toàn bộ quyền của gói hiện tại trong thời gian còn lại;
- gói thấp hơn chỉ bắt đầu khi gói cũ kết thúc;
- ngày bắt đầu gói thấp hơn trở thành Plan Anchor Date của gói mới.

Không cần xử lý ép giảm Watchlist giữa thời hạn gói hiện tại.

---

## 11. Gói FULL

Gói FULL có toàn bộ quyền và **không áp hạn mức kỹ thuật**.

FULL:

- không giới hạn Watchlist Capacity;
- không giới hạn ADD;
- không giới hạn REMOVE;
- không có Monthly Symbol Change Quota;
- không cần Initial Setup Window để phục vụ quota;
- không giới hạn phạm vi xem;
- mở toàn bộ quyền Email Alert;
- mở toàn bộ quyền Telegram Alert;
- các quyền membership khác được mở toàn bộ theo thiết kế sản phẩm.

Trong database nên biểu diễn FULL bằng logic rõ ràng, ví dụ:

- `full_market_access = true`;
- `watchlist_limit = null`;
- `change_limit = null`;

Không dùng các con số giả rất lớn để mô phỏng "không giới hạn".

---

## 12. Gia hạn gói trả phí đúng hạn

Khi user gia hạn liên tục:

- Watchlist giữ nguyên.
- Plan Anchor Date giữ nguyên.
- Chu kỳ quota giữ nguyên theo ngày gốc của gói.
- Không mở lại Initial Setup Window.
- Không cho chọn Watchlist ban đầu lại.
- Không reset Watchlist.

Ví dụ:

User bắt đầu gói ngày 15/08 và gia hạn liên tục.

Plan Anchor Date vẫn là ngày 15.

Quota tiếp tục reset theo:

- 15/09;
- 15/10;
- 15/11;
- v.v.

---

## 13. Hết hạn gói trả phí và Grace Period 2 ngày

Khi tới ngày hết hạn gói trả phí:

- hệ thống phải hiển thị thông báo rõ ràng rằng gói đã tới hạn;
- user có **2 ngày Grace Period** để hoàn tất thanh toán.

Trong 2 ngày Grace Period:

- Watchlist trả phí vẫn được giữ nguyên;
- user vẫn được xem theo quyền gói cũ;
- Email/Telegram alert của gói cũ vẫn được giữ;
- **không cấp quota tháng mới**;
- không thay đổi Plan Anchor Date.

Thông báo cần nêu rõ:

> Nếu không hoàn tất thanh toán trước khi Grace Period kết thúc, Watchlist của gói trả phí sẽ bị mất và tài khoản sẽ được chuyển về FREE.

---

## 14. Thanh toán trong Grace Period

Nếu user thanh toán thành công trong Grace Period:

- giữ nguyên Watchlist;
- giữ nguyên gói;
- giữ nguyên Plan Anchor Date cũ;
- chu kỳ tiếp tục theo ngày gốc;
- quota mới được kích hoạt theo chu kỳ gốc sau khi thanh toán thành công;
- không mở lại 7 ngày setup;
- không coi là một gói mới.

---

## 15. Không thanh toán sau Grace Period

Nếu Grace Period kết thúc mà user chưa thanh toán:

### 15.1. Gói trả phí

- gói trả phí chấm dứt;
- quyền trả phí bị thu hồi;
- Watchlist của gói trả phí bị xóa;
- quyền alert trả phí bị thu hồi.

### 15.2. Chuyển về FREE

User được chuyển về một kỳ FREE mới.

Ngày chuyển về FREE trở thành:

- ngày bắt đầu FREE mới;
- Plan Anchor Date mới của FREE;
- ngày bắt đầu Initial Setup Window 7 ngày.

User:

- được chọn lại tối đa 10 mã FREE;
- có 7 ngày để ADD 10 mã đầu miễn phí;
- sau 7 ngày áp quota FREE = 3 mã/tháng.

**Không tự động lấy 10 mã từ Watchlist trả phí cũ.**

Lý do:

- hệ thống không thể tự biết user muốn giữ 10 mã nào;
- user phải chủ động chọn Watchlist FREE mới.

---

## 16. Trường hợp quay lại sau khi đã bị trả về FREE

Nếu user đã bị downgrade về FREE do không gia hạn, sau đó mua lại gói trả phí:

- coi là một lần tham gia gói trả phí mới;
- ngày mua lại là Plan Anchor Date mới;
- được áp dụng Initial Setup Window 7 ngày của gói mới;
- Watchlist FREE hiện tại có thể được giữ làm nền, nhưng phần quyền/capacity mới phải tuân theo logic của gói mới;
- phần capacity tăng thêm được bổ sung miễn phí trong 7 ngày.

Việc chuyển đổi dữ liệu Watchlist khi mua lại phải bảo đảm không làm mất các mã hợp lệ đang có nếu không cần thiết.

---

## 17. FREE là ngoại lệ về quota

Không được suy `change_limit` bằng cách mặc định:

`change_limit = watchlist_limit`

vì FREE là ngoại lệ:

| Gói | Watchlist Capacity | Monthly Symbol Change Quota |
|---|---:|---:|
| FREE | 10 | 3 |
| Gói N mã | N | N |
| FULL | Không giới hạn | Không giới hạn |

Do đó trong database cần lưu độc lập:

- `watchlist_limit`
- `change_limit`

Không hard-code công thức duy nhất cho tất cả plan.

---

## 18. Quy tắc tính quota đề xuất cho backend

Backend phải là nơi quyết định quota.

Frontend chỉ:

- hiển thị quota;
- gửi yêu cầu thay đổi Watchlist;
- hiển thị kết quả.

Frontend **không được tự quyết định**:

- user còn quota hay không;
- ADD này có tính quota hay không;
- user có vượt capacity hay không;
- user đang trong 7 ngày setup hay không;
- user đang trong Grace Period hay không.

Các kiểm tra trên phải được thực hiện bằng database/RPC/backend transaction.

---

## 19. Yêu cầu transaction khi thay đổi Watchlist

Một thao tác cập nhật Watchlist cần được xử lý nguyên tử.

Backend/RPC phải kiểm tra trong cùng transaction:

1. User đã đăng nhập.
2. Subscription hiện tại hợp lệ.
3. Gói hiện tại.
4. Trạng thái ACTIVE / GRACE / EXPIRED.
5. Watchlist Capacity.
6. Initial Setup Window.
7. Upgrade free addition window nếu có.
8. Số mã ADD thực tế.
9. Quota còn lại.
10. Không vượt capacity.
11. Các symbol hợp lệ và thuộc Scanner Universe.
12. Thực hiện ADD/REMOVE.
13. Cập nhật quota.
14. Ghi audit/history nếu cần.

Nếu bất kỳ điều kiện nào thất bại:

- rollback toàn bộ;
- không cập nhật quota một phần;
- không cập nhật Watchlist một phần.

---

## 20. Quy tắc xác định số mã ADD

Khi user gửi Watchlist mới:

- `old_set` = Watchlist trước khi thay đổi.
- `new_set` = Watchlist user muốn lưu.

Cần tính:

- `removed = old_set - new_set`
- `added = new_set - old_set`

Quota chỉ dựa trên:

- `count(added)`

Không dựa trên:

- `count(removed)`
- tổng số phần tử thay đổi
- số lần bấm Save.

Ví dụ:

Watchlist cũ:

`HPG, FPT, SSI, VNM`

Watchlist mới:

`FPT, SSI, MWG, VCB`

Kết quả:

- removed = HPG, VNM
- added = MWG, VCB
- quota sử dụng = **2**

---

## 21. Quy tắc 7 ngày setup

### User mới

Bắt đầu tính từ ngày kích hoạt gói.

Trong 7 ngày:

- ADD tối đa capacity mà không mất quota.

Sau 7 ngày:

- mọi ADD mới trừ quota.

### Nâng cấp

Chỉ phần **capacity tăng thêm** được miễn phí trong 7 ngày kể từ ngày nâng cấp.

Không được dùng cửa sổ nâng cấp để thay toàn bộ các mã cũ miễn phí.

Ví dụ:

- trước nâng cấp có 50 mã;
- nâng lên 100;
- 50 slot tăng thêm được add miễn phí;
- nếu user xóa 10 mã cũ rồi add 10 mã khác:
  - 10 mã thay cho phần cũ phải được xem xét theo quota;
  - không được coi toàn bộ 10 mã đó là capacity tăng thêm miễn phí.

Backend cần phân biệt rõ:

- free additions do capacity tăng;
- symbol changes của Watchlist đã tồn tại.

---

## 22. Grace Period và quota

Trong Grace Period:

- Watchlist giữ nguyên.
- Quyền gói cũ giữ nguyên.
- Không reset/cấp quota tháng mới trước khi user thanh toán.

Nếu thanh toán:

- quota kích hoạt theo chu kỳ gốc.

Nếu không thanh toán:

- downgrade FREE;
- Watchlist trả phí bị xóa;
- FREE mới bắt đầu từ ngày downgrade.

Điều này ngăn user sử dụng quota mới trong 2 ngày Grace rồi không gia hạn.

---

## 23. Trạng thái subscription nên hỗ trợ

Tối thiểu nên có logic tương đương:

- `ACTIVE`
- `GRACE`
- `EXPIRED`
- `SUSPENDED` nếu sau này cần
- `CANCELLED` nếu sau này cần

Ý nghĩa:

### ACTIVE
Gói đang hoạt động bình thường.

### GRACE
Đã tới hạn thanh toán nhưng đang trong 2 ngày gia hạn.

### EXPIRED
Grace Period đã kết thúc mà chưa thanh toán.

Khi chuyển EXPIRED:

- thực hiện logic downgrade FREE theo quy định.

---

## 24. Dữ liệu nên lưu để tránh tính sai về sau

Các trường nghiệp vụ nên có hoặc có logic tương đương:

### Subscription

- `user_id`
- `plan_id`
- `status`
- `started_at`
- `plan_anchor_date`
- `cycle_start`
- `cycle_end`
- `change_used`
- `setup_window_end`
- `initial_setup_completed`
- `grace_started_at`
- `grace_end_at`
- `upgrade_started_at`
- `upgrade_free_additions_remaining`
- `upgrade_free_additions_end_at`

### Watchlist

- `user_id`
- `symbol`
- `added_at`
- `removed_at` hoặc trạng thái active nếu dùng history
- nguồn ADD:
  - initial setup
  - normal quota
  - upgrade free addition
  - admin/system nếu cần

### Watchlist Change Log / Audit

Nên lưu:

- user
- thời điểm
- symbol
- action ADD/REMOVE
- quota cost
- reason/source
- subscription id
- plan id
- cycle id hoặc cycle_start

Audit giúp:

- giải quyết khiếu nại;
- kiểm tra quota;
- debug;
- làm lịch sử thay đổi trong tương lai.

---

## 25. Security / RLS nguyên tắc

Watchlist là dữ liệu user-specific.

Bắt buộc:

- RLS bật.
- User chỉ SELECT được Watchlist của chính mình.
- User không được tự set `user_id`.
- User không được tự sửa `change_used`.
- User không được tự sửa `plan_id`.
- User không được tự đổi `subscription.status`.
- Các thao tác ảnh hưởng quota nên đi qua RPC/backend transaction.
- Không tin dữ liệu quota từ frontend.
- Publishable key có thể nằm ở frontend, nhưng quyền truy cập phải được khóa bằng RLS/RPC.

---

## 26. Admin / Super Admin

Phải giữ ranh giới sau:

### User

Chỉ quản lý:

- Watchlist của chính mình;
- thông tin cá nhân được cho phép;
- cài đặt alert của chính mình trong quyền gói.

### Admin

Có thể quản lý nghiệp vụ user theo quyền được cấp, nhưng:

- không được làm thay đổi Scanner Universe thông qua Watchlist.

### Super Admin / Backend

Quản lý:

- Scanner Universe;
- plan configuration;
- subscription;
- billing;
- các thao tác hệ thống đặc biệt.

---

## 27. Nội dung cần hiển thị cho user trên UI

Trang Watchlist nên cho user thấy rõ:

- Gói hiện tại.
- Watchlist Capacity.
- Số mã đang dùng.
- Số slot còn trống.
- Quota đổi mã tháng này.
- Quota đã dùng.
- Quota còn lại.
- Ngày reset quota tiếp theo.
- Nếu đang setup:
  - còn bao nhiêu ngày miễn phí.
- Nếu đang trong upgrade window:
  - còn bao nhiêu slot upgrade miễn phí;
  - ngày hết hạn bổ sung miễn phí.
- Nếu đang Grace:
  - ngày/giờ hết Grace;
  - cảnh báo Watchlist sẽ bị mất nếu không gia hạn.

---

## 28. Cách giải thích đơn giản cho người dùng

Nội dung hướng dẫn sau này có thể dựa trên cách nói sau:

### Watchlist không bị reset mỗi tháng

Danh sách mã bạn đang theo dõi sẽ được giữ nguyên trong suốt thời gian gói còn hiệu lực. Mỗi tháng hệ thống chỉ cấp lại số lượt đổi mã, không yêu cầu bạn chọn lại Watchlist.

### Đổi mã được tính như thế nào?

- Xóa mã: không mất lượt.
- Thêm mã mới: mất 1 lượt.
- Xóa rồi thêm lại cùng mã: vẫn tính 1 lượt.
- Thay 5 mã cùng lúc: mất 5 lượt.

### 7 ngày đầu

Khi bắt đầu gói, bạn có 7 ngày để hoàn thiện Watchlist ban đầu mà không mất lượt đổi.

### Khi gói hết hạn

Bạn có thêm 2 ngày để gia hạn. Trong thời gian này Watchlist vẫn được giữ. Nếu hết 2 ngày vẫn chưa thanh toán, Watchlist trả phí sẽ bị xóa và tài khoản chuyển về FREE.

---

## 29. Ví dụ hoàn chỉnh

### Ví dụ A — FREE

User tạo tài khoản ngày 05/08.

- Capacity: 10.
- Setup miễn phí: 7 ngày.
- Quota đổi: 3/tháng.
- User chọn 8 mã trong 7 ngày.
- Sau 7 ngày add thêm mã thứ 9 → mất 1 quota.
- Xóa mã thứ 3 → không mất quota.
- Add lại mã thứ 3 → mất thêm 1 quota.
- Đến kỳ reset quota → Watchlist giữ nguyên, quota trở lại 3.

### Ví dụ B — Gói 50

User bắt đầu gói ngày 12/08.

- Capacity: 50.
- Quota: 50/tháng.
- 7 ngày đầu add miễn phí.
- User chọn đủ 50 mã.
- Sau đó xóa 4 mã → quota vẫn 50.
- Add 4 mã khác → quota còn 46.
- Đến 12/09 → Watchlist giữ nguyên, quota được reset theo chu kỳ.

### Ví dụ C — Nâng 50 lên 100

User nâng cấp ngày 22/08.

- 50 mã cũ giữ nguyên.
- Capacity mới: 100.
- Có thêm 50 slot.
- Trong 7 ngày có thể add miễn phí phần capacity tăng thêm.
- Anchor mới: 22/08.
- Reset quota tiếp theo theo mốc 22/09.

### Ví dụ D — Hết hạn nhưng đóng tiền trong Grace

Gói hết hạn ngày 15/09.

- Grace: 2 ngày.
- Trong Grace:
  - giữ Watchlist;
  - giữ quyền gói;
  - chưa cấp quota mới.
- User thanh toán trước khi Grace kết thúc.
- Watchlist giữ nguyên.
- Anchor vẫn theo ngày 15.
- Gói tiếp tục bình thường.

### Ví dụ E — Không đóng tiền

Gói hết hạn ngày 15/09.

- Hết Grace vẫn chưa thanh toán.
- Watchlist trả phí bị xóa.
- User chuyển về FREE vào ngày downgrade.
- Ngày downgrade trở thành anchor FREE mới.
- User có 7 ngày để chọn lại 10 mã FREE.
- Sau đó quota = 3/tháng.

---

## 30. Những điều tuyệt đối không được làm

- Không reset Watchlist mỗi tháng.
- Không tính quota theo số lần Save.
- Không trừ quota khi REMOVE.
- Không cho frontend tự tính quota cuối cùng.
- Không tự giữ 10 mã bất kỳ khi downgrade về FREE.
- Không để user sửa `change_used` trực tiếp.
- Không để Watchlist tác động đến Scanner Universe.
- Không cấp quota mới trong Grace trước khi user thanh toán.
- Không reset Plan Anchor Date khi user gia hạn liên tục.
- Không dùng logic `change_limit = watchlist_limit` cho FREE.
- Không giới hạn gói FULL bằng số giả.

---

## 31. Trạng thái logic hiện tại

Các quy tắc trong tài liệu này được xem là **business logic đã chốt** và phải là nguồn tham chiếu trước khi triển khai:

1. Security hardening.
2. Watchlist tables.
3. RLS.
4. RPC transaction.
5. Membership enforcement.
6. Scanner entitlement.
7. Email/Telegram alerts.
8. Billing và renewal.
9. Trang hướng dẫn người dùng.

Nếu implementation và tài liệu này có điểm mâu thuẫn, cần dừng lại đối chiếu business rule trước khi tiếp tục.

---

## 32. Ghi chú triển khai

Tài liệu này mô tả **nghiệp vụ**.

Tên bảng, tên cột, tên RPC và cấu trúc migration có thể thay đổi trong quá trình triển khai, nhưng **không được thay đổi hành vi nghiệp vụ** nếu chưa có quyết định mới.

Khi business rule thay đổi:

1. cập nhật tài liệu này trước;
2. ghi version/date;
3. sau đó mới sửa database/backend/frontend tương ứng.


---

## 33. VIP Day — temporary entitlement overlay (v1.1 addendum, 2026-08-22)

VIP Day có giá **100.000đ / 24 giờ** và cấp quyền FULL tạm thời.

VIP Day không phải subscription nền và không được:

- thay `plan_id` hiện tại;
- thay Plan Anchor Date;
- reset `change_used`;
- tạo setup window mới;
- xóa hoặc thay DS mã theo dõi nền;
- thay ngày hết hạn gói nền.

Trong thời gian VIP Day hoạt động, effective technical entitlement = FULL.

Hết 24 giờ, user trở lại đúng subscription, DS mã, quota và chu kỳ đã có trước VIP.

Ví dụ:

`FREE + DS 10 mã -> VIP Day 24h -> FREE + đúng DS 10 mã cũ`

`PLUS + DS 50 mã -> VIP Day 24h -> PLUS + đúng DS 50 mã cũ`

VIP Day không thay đổi các quy tắc Watchlist ở các mục phía trên; nó chỉ tạm thời mở rộng **quyền xem**.
