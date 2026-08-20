# CCC WATCHLIST RULES v1.0

**Product:** Chuyện Chợ Chứng  
**Version:** 1.0  
**Status:** LOCKED  
**Effective date:** 2026-08-20  
**Parent:** `CCC_MEMBERSHIP_PERMISSION_MODEL_v1.0.md`

---

## 1. Purpose

Tài liệu này định nghĩa chính xác:

- Watchlist là gì;
- giới hạn theo từng gói;
- initial setup;
- cách tính lượt đổi mã;
- reset quota;
- upgrade/downgrade;
- anti-abuse;
- audit log;
- UI behavior.

Mục tiêu:

> User dễ hiểu, backend dễ enforce, không tạo lỗ hổng để một Watchlist nhỏ có thể xoay vòng xem gần toàn scanner universe.

---

## 2. Watchlist definition — LOCKED

Watchlist là danh sách symbol cá nhân user chọn để:

- xem chi tiết;
- theo dõi thường xuyên;
- làm access entitlement với Free/Basic/Plus/Pro;
- nhận alert nếu plan hỗ trợ;
- cá nhân hóa giao diện.

Watchlist **không thay đổi scanner universe**.

Xóa FPT khỏi Watchlist không làm backend ngừng quét FPT.

---

## 3. Limits — LOCKED

| Plan | Active Watchlist limit | Change quota / cycle |
|---|---:|---:|
| Free | 10 | 10 |
| Basic | 20 | 20 |
| Plus | 50 | 50 |
| Pro | 100 | 100 |
| Full Market | Không dùng Watchlist để giới hạn quyền xem | Không giới hạn quyền xem |

Với Full, Watchlist vẫn hữu ích cho:

- favorite;
- alert selection;
- priority display.

Nhưng không còn là điều kiện để mở Stock Detail.

---

## 4. Change quota definition — LOCKED

Một **lượt đổi mã** được tính khi:

> Sau khi initial setup hoàn tất, một symbol mới được kích hoạt vào Watchlist.

Ví dụ:

```text
HPG → VIX
```

= 1 lượt.

Không phải:

```text
Mở trang chỉnh Watchlist
```

= 1 lượt.

Quota tính theo **mã mới được đưa vào**.

---

## 5. Initial setup — LOCKED

User mới được thiết lập Watchlist lần đầu mà không tiêu quota.

Ví dụ Free:

```text
limit = 10
initial selection = 10
change_used = 0
```

Initial setup kết thúc khi user xác nhận:

> **Hoàn tất Watchlist**

Sau đó symbol mới được thêm vào sẽ tuân quota, trừ capacity mới do upgrade.

---

## 6. Action rules

| Action | Tốn quota? |
|---|---|
| Initial selection | Không |
| Mở trang Watchlist | Không |
| Search symbol | Không |
| Reorder | Không |
| Xóa symbol | Không |
| Thêm symbol mới sau initial setup | Có, 1 |
| Replace A → B | Có, 1 |
| Re-add mã cũ đã xóa | Có, 1 |
| Thêm vào slot mới do upgrade | Không |
| Downgrade deactivation | Không |
| Admin repair | Không, nếu là operation hệ thống được log |

---

## 7. Remove only

User:

```text
10 active → 9 active
```

Không tốn quota.

Lý do:

Không có symbol mới nào được entitlement.

---

## 8. Add after initial setup

User đang:

```text
9 / 10 active
```

và thêm VIX sau khi initial setup đã hoàn tất:

> Tốn 1 lượt.

Việc còn slot trống không đồng nghĩa thêm mới miễn quota.

---

## 9. Replace

User:

```text
HPG out
VIX in
```

= 1 lượt.

Nếu thay 3 mã:

```text
HPG → VIX
FPT → DGC
SSI → MBB
```

= 3 lượt.

---

## 10. Re-add old symbol — LOCKED

Nếu:

```text
FPT → VIX
```

= 1 lượt.

Sau đó:

```text
VIX → FPT
```

= thêm 1 lượt.

Không xây cơ chế “mã đã từng có trong tháng thì miễn”.

---

## 11. Upgrade capacity — LOCKED

Ví dụ:

```text
Free 10
→ Plus 50
```

User có thêm:

```text
40 slots mới
```

Lấp đầy 40 slots do upgrade:

> **Không tốn change quota.**

Recommended backend concept:

```text
old_limit = 10
new_limit = 50
upgrade_free_additions = 40
```

Khi capacity mới đã được sử dụng hết hoặc user hoàn tất upgrade setup, các symbol mới tiếp theo dùng quota bình thường.

---

## 12. Why upgrade additions are free

User vừa mua thêm capacity.

Nếu hệ thống:

```text
mở thêm 40 slot
→ lập tức trừ 40/50 lượt đổi
```

thì user bị phạt vì sử dụng quyền vừa mua.

Không được làm như vậy.

---

## 13. Quota cycle — LOCKED

Quota reset theo subscription cycle.

Ví dụ:

```text
18/08/2026 → 17/09/2026
```

Plus:

```text
change_limit = 50
```

Cycle sau reset `change_used`.

Không bắt buộc reset ngày 01.

---

## 14. Free cycle

Free cũng cần cycle rõ để quota deterministic.

System phải biết:

```text
cycle_start
cycle_end
```

UI phải hiển thị ngày reset.

---

## 15. Quota counters

Backend authoritative values:

```text
change_limit
change_used
change_remaining
```

Ví dụ:

```text
10 limit
3 used
7 remaining
```

UI:

> Còn **7/10 lượt đổi mã** trong chu kỳ này.

---

## 16. Confirmation before quota consumption — LOCKED UX

Trước khi thao tác chắc chắn tiêu quota:

> Thêm VIX sẽ sử dụng **1 lượt đổi mã**.  
> Bạn còn **7/10 lượt**.

CTA:

```text
[Xác nhận thêm VIX]
```

Không âm thầm trừ quota.

---

## 17. Watchlist capacity vs quota — LOCKED

Luôn hiển thị như hai khái niệm khác nhau:

```text
Watchlist
10 / 10 mã
```

```text
Lượt đổi
7 / 10 còn lại
```

Không gộp thành một progress bar.

---

## 18. Full capacity flow

Free:

```text
10 / 10 mã
```

User muốn thêm VIX.

UI:

> Watchlist đã đủ 10/10 mã.

Options:

```text
[Đổi một mã hiện tại]
[Nâng cấp gói]
```

Nếu còn quota, không ép upgrade.

---

## 19. Quota exhausted flow

Ví dụ:

```text
10 / 10 mã
0 / 10 lượt đổi
```

User không thể activate symbol mới trong cycle hiện tại.

UI:

> Bạn đã dùng hết lượt đổi.  
> Watchlist hiện tại vẫn hoạt động bình thường.  
> Quota reset vào 18/09/2026.

Options:

```text
[Nâng cấp gói]
[Đóng]
```

---

## 20. Exact search outside Watchlist

Search không tốn quota.

Ví dụ:

```text
VIX
Chứng khoán VIX
HOSE
```

Nếu locked:

> Mã này chưa nằm trong Watchlist của bạn.

Actions:

```text
[Đổi một mã]
[Nâng cấp]
```

Chỉ khi user xác nhận đưa VIX vào Watchlist mới tính quota.

---

## 21. Atomic replace — LOCKED TECHNICAL RULE

Không được:

1. remove HPG thành công;
2. add VIX thất bại;
3. user mất HPG;
4. quota vẫn bị trừ.

Recommended operation:

```text
replace_watchlist_symbol(old_symbol, new_symbol)
```

Backend transaction:

1. validate authenticated user;
2. validate plan;
3. validate active limit;
4. validate quota;
5. validate new symbol;
6. validate duplicate;
7. remove/add atomically;
8. increment quota atomically;
9. write log.

---

## 22. Concurrency — LOCKED

Nếu user dùng PC + mobile cùng lúc:

Backend phải ngăn:

- active count vượt limit;
- quota âm;
- duplicate symbol;
- double-spend quota.

Frontend counter không authoritative.

---

## 23. Duplicate symbols

Một user không được có cùng một symbol active hai lần.

Enforce bằng database constraint hoặc transaction logic.

---

## 24. Valid symbols

Chỉ symbol hợp lệ trong scanner universe / approved stock directory mới được thêm.

Nếu symbol bị delist/ngừng hỗ trợ:

- không silent replace;
- không tự tiêu quota;
- cần migration/system handling riêng.

---

## 25. Data model suggestion

### Current items

```text
watchlist_items
---------------
id
user_id
symbol
status
added_at
removed_at
added_reason
subscription_id
created_at
updated_at
```

Suggested statuses:

```text
ACTIVE
REMOVED
INACTIVE_DUE_TO_PLAN
```

### Change log

```text
watchlist_change_log
--------------------
id
user_id
cycle_start
cycle_end
action
old_symbol
new_symbol
quota_delta
source
created_at
```

Suggested actions:

```text
INITIAL_ADD
UPGRADE_CAPACITY_ADD
REPLACE
REMOVE
RE_ADD
DOWNGRADE_DEACTIVATE
ADMIN_REPAIR
```

---

## 26. History — LOCKED

Không hard-delete Watchlist history khi user remove.

Lý do:

- audit quota;
- support;
- downgrade;
- fraud/abuse investigation;
- analytics.

Current active list và history có thể tách table nếu implementation thấy phù hợp.

---

## 27. Entitlement relation

Free/Basic/Plus/Pro:

```text
ACTIVE watchlist
=
protected Stock Detail entitlement
```

Nếu symbol không active:

```text
get_stock_detail(symbol)
→ LOCKED
```

Full:

```text
protected detail entitlement = full scanner universe
```

---

## 28. Notification relation

Plus/Pro:

Alert-eligible symbols mặc định nằm trong active Watchlist.

Remove symbol:

- detail entitlement dừng;
- alert cho symbol đó dừng, trừ khi Product Spec tương lai định nghĩa khác.

Full:

Alert selection độc lập hơn vì detail entitlement = all market.

---

## 29. Downgrade — LOCKED

Ví dụ:

```text
Pro
80 active / 100
→ Plus
limit 50
```

System:

1. không xóa history;
2. báo user cần giảm còn 50;
3. user chọn mã giữ;
4. extras → `INACTIVE_DUE_TO_PLAN`;
5. sau effective time, extras không còn protected detail;
6. không tốn change quota vì downgrade deactivation.

Recommended state:

```text
WATCHLIST_REDUCTION_REQUIRED
```

---

## 30. Paid expiry → Free

Nếu paid hết hạn và active >10:

UI:

> Tài khoản đã chuyển về Free.  
> Vui lòng chọn 10 mã muốn tiếp tục theo dõi.

Trong thời gian reduction-required:

- market aggregate vẫn xem;
- paid alerts dừng;
- không leak protected detail ngoài Free entitlement;
- history giữ nguyên.

---

## 31. Admin repair

Admin có thể:

- inspect Watchlist;
- inspect quota log;
- sửa trạng thái bất thường.

Admin repair:

- không tiêu user quota nếu là system correction;
- bắt buộc audit log.

---

## 32. Anti-abuse — LOCKED

Quota tồn tại để chặn:

```text
Free 10 slots
→ đổi vô hạn
→ xem hàng trăm symbol/tháng
```

Quota enforce backend-side.

Ẩn nút frontend không phải bảo mật.

---

## 33. Privacy

Watchlist là dữ liệu cá nhân của user.

Không public.

Chỉ:

- chính user;
- authorized service;
- authorized admin khi cần vận hành

được truy cập.

---

## 34. Mobile UX

Quản lý Watchlist phải mobile-first đủ dùng:

- search;
- count 10/10;
- quota 7/10;
- replace rõ;
- remove rõ;
- confirm quota;
- không bắt user dùng bảng desktop co nhỏ.

---

## 35. Acceptance criteria

- [ ] Free active limit 10.
- [ ] Basic 20.
- [ ] Plus 50.
- [ ] Pro 100.
- [ ] Initial setup = 0 quota.
- [ ] Remove-only = 0 quota.
- [ ] Add after setup = 1 quota.
- [ ] Replace A→B = 1 quota.
- [ ] Re-add = 1 quota.
- [ ] Upgrade capacity additions = 0 quota.
- [ ] Quota reset theo cycle.
- [ ] UI hiện remaining + reset date.
- [ ] Backend chống race condition.
- [ ] Replace atomic.
- [ ] Duplicate bị chặn.
- [ ] Remove không tác động scanner universe.
- [ ] History được giữ.
- [ ] Downgrade không random-delete.
- [ ] Full detail access không phụ thuộc Watchlist.

---

## 36. Change control

Agent không được tự:

- đổi quota;
- tính quota theo “lần chỉnh danh sách”;
- cho swap vô hạn;
- miễn re-add;
- hard-delete history;
- gắn Watchlist remove với scanner universe.

Thay đổi cần Product Owner approval + version mới.
