# CCC MEMBERSHIP & PERMISSION MODEL v1.0

**Product:** Chuyện Chợ Chứng  
**Version:** 1.0  
**Status:** LOCKED  
**Effective date:** 2026-08-20  
**Applies to:** v19 staging and later  
**Parent architecture:** scanner universe remains backend-controlled; frontend/user actions never remove symbols from scanner universe.

---

## 1. Product principle

Chuyện Chợ Chứng tách dữ liệu và quyền truy cập thành 3 lớp:

```text
SCANNER UNIVERSE
        │
        ├── PUBLIC MARKET QUOTE + FUNDAMENTAL RESEARCH
        │      → mọi user xem được cho mọi mã khi dữ liệu thật tồn tại
        │
        ├── CCC TECHNICAL INTELLIGENCE
        │      → được bảo vệ theo technical entitlement của từng gói
        │
        └── PERSONALIZATION
               → Watchlist + Alerts + Account
```

### Market Intelligence — FREE FOR ALL

Mọi user đều được thấy dữ liệu tổng hợp toàn scanner universe, ví dụ:

- tổng số mã scanner đang quản lý;
- số mã đạt 4/4;
- số mã đạt 3/4;
- số mã đạt 2/4;
- số mã RVOL30 sớm;
- thời gian cập nhật;
- trạng thái dữ liệu;
- nội dung giải thích tín hiệu.

Ngoài aggregate, mọi user được xem **Public Market Quote** cho mọi mã: ticker, company/display name, exchange, current price, percentage change và current accumulated volume.

**Public Fundamental Research** cũng công khai khi có field thật: industry/`website_group`, fundamental score và coverage, tăng trưởng lợi nhuận/doanh thu/quý, ROE, ROA, debt/equity, debt/assets, P/E, P/B, freshness tài chính, lịch sử quý và BCTC link. Missing-data rule hiện tại không đổi.

### CCC Technical Intelligence — THEO GÓI

Technical entitlement từng mã gồm:

- KL ngày / KLTB10;
- MA10, MA200;
- RVOL30;
- 4 tín hiệu;
- signal count và CCC Signal Rail;
- technical discovery identities;
- technical alerts.

> Market quote is public.
>
> Fundamental research is public.
>
> CCC technical intelligence is protected.

---

## 2. Commercial plans — LOCKED

| Plan code | Tên | Giá/tháng | Phạm vi CCC Technical | Watchlist | Lượt đổi/cycle | Email | Telegram |
|---|---|---:|---:|---:|---:|---|---|
| `FREE` | Free | 0đ | 10 mã | 10 | 10 | Không | Không |
| `BASIC` | Basic | 100.000đ | 20 mã | 20 | 20 | Không | Không |
| `PLUS` | Plus | 300.000đ | 50 mã | 50 | 50 | Có | Có |
| `PRO` | Pro | 500.000đ | 100 mã | 100 | 100 | Có | Có |
| `FULL` | Full Market | 1.000.000đ | Toàn scanner universe | Không dùng Watchlist để giới hạn technical scope | Không giới hạn technical scope | Có | Có |

`PLUS` là gói được ưu tiên trên pricing UI với nhãn:

> **Phổ biến nhất**

Tên hiển thị có thể đổi sau; permission phải dựa vào `plan_code`, không dựa vào text UI.

---

## 3. Feature inheritance — LOCKED

Nguyên tắc:

> Gói cao hơn luôn có toàn bộ tính năng của gói thấp hơn.

```text
FREE
  ↓
BASIC = FREE + capacity cao hơn
  ↓
PLUS = BASIC + capacity cao hơn + Email + Telegram
  ↓
PRO = PLUS + capacity cao hơn
  ↓
FULL = PRO + CCC Technical Intelligence toàn scanner universe
```

Bắt buộc:

- Pro có toàn bộ tính năng Plus.
- Full có toàn bộ tính năng Pro.
- Không được tạo tình huống Pro nhiều mã hơn nhưng thiếu một tính năng đã có ở Plus.

---

## 4. Permission dimensions — LOCKED

Không gộp toàn bộ permission vào một biến `watchlist_limit`.

Hệ thống phải phân biệt:

```text
VIEW ENTITLEMENT
WATCHLIST ENTITLEMENT
CHANGE QUOTA
ALERT ENTITLEMENT
```

### View entitlement

Số symbol user được nhận protected CCC Technical Intelligence. View entitlement không giới hạn Public Market Quote hoặc Public Fundamental Research.

### Watchlist entitlement

Số symbol active trong danh sách cá nhân.

Với Free/Basic/Plus/Pro:

```text
active watchlist set = technical entitlement set
```

Với Full:

```text
technical entitlement = all scanner universe
```

Watchlist của Full chỉ còn phục vụ:

- favorite;
- priority;
- alert selection;
- cá nhân hóa.

### Change quota

Số symbol mới được kích hoạt vào Watchlist sau initial setup trong một cycle.

Chi tiết: `CCC_WATCHLIST_RULES_v1.0.md`.

### Alert entitlement

- Free: không Email/Telegram.
- Basic: không Email/Telegram.
- Plus: Email + Telegram.
- Pro: kế thừa toàn bộ Plus.
- Full: kế thừa toàn bộ Pro.

---

## 5. Full Market alert rule

Full được xem toàn scanner universe nhưng không mặc định gửi alert cho toàn bộ thị trường.

Nguyên tắc:

- alert là opt-in;
- user chọn symbol/rule;
- có thể lọc theo 4/4, RVOL30 sớm, watchlist ưu tiên;
- hệ thống có thể dùng digest/rate-limit để chống spam;
- các biện pháp vận hành không được làm Full mất quyền alert đã kế thừa từ Pro.

---

## 6. Market aggregate API — LOCKED

Mọi plan được nhận aggregate toàn thị trường.

Ví dụ:

```json
{
  "total_symbols": 800,
  "signal_4of4_count": 14,
  "signal_3of4_count": 38,
  "signal_2of4_count": 126,
  "rvol30_early_count": 21,
  "updated_at": "..."
}
```

Không hard-code `800`; production UI có thể hiển thị count động.

---

## 7. Signal-group access — LOCKED

Ví dụ toàn thị trường có 14 mã đạt 4/4.

Free có 2 mã trong entitlement.

Backend được trả:

```json
{
  "group": "4of4",
  "total_count": 14,
  "visible_count": 2,
  "locked_count": 12,
  "visible_items": [
    {"symbol": "FPT"},
    {"symbol": "SSI"}
  ]
}
```

Backend **không được trả symbol thật của 12 mã bị khóa**.

### Forbidden

```json
{"symbol":"VIX","locked":true}
```

rồi frontend đổi thành `•••`.

### Correct

Frontend chỉ nhận:

```text
locked_count = 12
```

Protected identities không xuất hiện trong Network/DevTools.

---

## 8. Public stock directory, quote and research — ALLOWED

User có thể search chính xác và xem public identity/quote/research của mọi mã.

Ví dụ:

```text
VIX
Chứng khoán VIX
HOSE
23.500 · +1,2% · KL 2.450.000
CCC Technical Intelligence: 🔒 Ngoài phạm vi
```

Public response có thể chứa:

- symbol;
- display_name/company_name;
- exchange;
- current price;
- percentage change;
- current accumulated volume;
- các field Fundamental Research thật được định nghĩa ở Mục 1.

Không chứa:

- KLTB10 hoặc KL ngày/KLTB10;
- MA10/MA200 và khoảng cách;
- RVOL30/sessions;
- bốn technical signals, signal count hoặc CCC Signal Rail;
- technical discovery identities hoặc technical alerts nếu chưa được entitlement.

User biết `VIX` và chủ động search là khác với việc hệ thống enumerate các mã đang 4/4.

---

## 9. Technical detail access — LOCKED SECURITY RULE

Không được:

```text
fetch 800 full technical rows
→ browser nhận tất cả
→ JS/CSS giấu phần không được xem
```

Phải:

```text
request
  ↓
backend entitlement check
  ↓
AUTHORIZED → trả protected technical detail
LOCKED     → không trả protected technical detail
```

Frontend không phải security boundary.

---

## 10. Page-level entitlement

Permission áp dụng xuyên toàn sản phẩm.

### Overview

- mọi user thấy market aggregate;
- public identity/quote vẫn hiển thị cho mọi mã khi phù hợp với page pattern;
- chỉ entitled symbols được CCC Technical Intelligence;
- technical discovery ngoài entitlement chỉ hiện locked count/placeholder, không enumerate protected identities.

### Scanner

Free/Basic/Plus/Pro:

- public identity/quote rows có thể hiển thị cho mọi mã;
- technical fields chỉ hiện cho entitled symbols;
- market-wide technical discovery có thể trả aggregate/count;
- không tải full protected technical rows.

Full:

- xem toàn scanner universe.

### Industry Comparison

Đây là Public Fundamental Research. Không đưa technical fields vào research table để bypass entitlement.

### Fundamental Screener

Đây là Public Fundamental Research. Không đưa technical fields vào research table để bypass entitlement.

### Stock Detail

Public identity, quote và Fundamental Research vẫn hiển thị. Backend check technical entitlement trước khi trả CCC Technical Intelligence.

---

## 11. Entitled symbol = full supported technical detail

Nếu một symbol nằm trong entitlement của user:

> User được xem đầy đủ CCC Technical Intelligence mà sản phẩm hiện hỗ trợ cho symbol đó.

Free 10 mã không phải “10 mã nhưng technical detail bị cắt nhỏ”.

Mục tiêu: public quote/fundamental tạo giá trị nghiên cứu rộng; Free trải nghiệm technical value thật; paid mua **technical coverage + automation**, không phải mua từng technical field.

---

## 12. Subscription lifecycle

Recommended states:

```text
FREE
ACTIVE
PENDING
EXPIRED
CANCELLED
SUSPENDED
```

New account:

```text
plan_code = FREE
```

MVP paid activation cho phép Admin kích hoạt thủ công:

- plan;
- cycle_start;
- cycle_end.

Payment gateway tự động không bắt buộc trong v1.0.

---

## 13. Billing cycle

Paid quota reset theo subscription cycle, ví dụ:

```text
18/08 → 17/09
```

Không bắt buộc reset ngày 01 hàng tháng.

Free cũng nên có cycle rõ để quota deterministic.

---

## 14. Upgrade — LOCKED

Ví dụ:

```text
FREE 10 → PLUS 50
```

User có thêm 40 capacity mới.

Việc điền các slot mới do upgrade:

> **không tính change quota.**

Khi Plus/Pro/Full active:

- Email/Telegram entitlement bật;
- user vẫn phải cấu hình channel/preference trước khi nhận.

---

## 15. Downgrade — LOCKED PRINCIPLE

Ví dụ:

```text
PRO 100 → PLUS 50
```

user đang có 80 active symbols.

Không được:

- random delete 30 mã;
- hard delete Watchlist history.

Phải:

1. yêu cầu user chọn tối đa 50 mã giữ active;
2. phần còn lại chuyển inactive do plan;
3. history giữ nguyên;
4. protected technical detail ngoài active set dừng sau khi downgrade có hiệu lực; public quote/fundamental không bị ảnh hưởng.

Recommended state:

```text
WATCHLIST_REDUCTION_REQUIRED
```

---

## 16. Paid expiry → Free

Khi paid plan hết hạn:

- quyền quay về Free;
- market aggregate vẫn xem;
- Public Market Quote và Fundamental Research vẫn xem;
- Email/Telegram paid alerts dừng;
- nếu Watchlist >10, user chọn 10 mã giữ active;
- history không bị xóa.

---

## 17. Role vs membership — LOCKED

Role:

```text
USER
ADMIN
SUPER_ADMIN
```

Membership:

```text
FREE
BASIC
PLUS
PRO
FULL
```

Role và plan là hai trục khác nhau.

Không dùng membership để cấp Admin.

Không dùng Watchlist action để thay đổi scanner universe.

---

## 18. Recommended `plans` model

```text
plans
-----
id
plan_code
display_name
price_vnd
billing_interval
view_limit
watchlist_limit
change_limit
full_market_access
email_alerts
telegram_alerts
is_recommended
is_active
sort_order
created_at
updated_at
```

Full nên dùng:

```text
full_market_access = true
```

không hard-code universe = 800.

---

## 19. Recommended `subscriptions` model

```text
subscriptions
-------------
id
user_id
plan_id
status
cycle_start
cycle_end
activated_at
cancelled_at
created_by
created_at
updated_at
```

---

## 20. Security — LOCKED

Khi v19 cutover:

- browser không được public-select các protected technical fields trong `stock_snapshot` hoặc nguồn tương đương;
- API/RPC phải project public quote/fundamental riêng khỏi protected technical payload nếu cùng nguồn vật lý;
- dùng Supabase RLS/RPC/Edge Function hoặc secure backend;
- entitlement check dựa trên authenticated user;
- frontend không chứa `service_role`;
- publishable key chỉ an toàn khi RLS/API thực sự enforce permission.

---

## 21. Transition v18.5 → v19

Không khóa v18.5 production ngay khi dựng staging.

```text
qly.chuyenchochung.com
→ v18.5 stable
```

```text
test.chuyenchochung.com
→ v19 staging
→ permission API mới
```

Chỉ khi v19 sẵn sàng production:

1. deploy v19;
2. test Free/Basic/Plus/Pro/Full;
3. chặn legacy protected technical full-table access;
4. verify DevTools không enumerate locked data;
5. giữ rollback v18.5.

---

## 22. Pricing versioning

Giá v1.0:

- Basic: 100.000đ/tháng
- Plus: 300.000đ/tháng
- Pro: 500.000đ/tháng
- Full Market: 1.000.000đ/tháng

Giá phải nằm trong config/database, không hard-code rải rác.

---

## 23. Out of scope v1.0

Chưa thuộc spec này:

- payment gateway tự động;
- annual pricing;
- coupon;
- affiliate/referral;
- add-on +10 mã;
- enterprise/team plan;
- exact email provider;
- exact Telegram implementation;
- refund automation.

---

## 24. Acceptance criteria

- [ ] New user mặc định Free.
- [ ] Free protected technical detail tối đa 10 active symbols.
- [ ] Basic = 20.
- [ ] Plus = 50 + Email + Telegram.
- [ ] Pro = 100 + toàn bộ Plus features.
- [ ] Full xem CCC Technical Intelligence toàn scanner universe + toàn bộ Pro features.
- [ ] Mọi plan thấy market aggregate.
- [ ] Mọi plan thấy Public Market Quote và Public Fundamental Research cho mọi mã khi field thật tồn tại.
- [ ] Locked signal-group API không trả protected ticker.
- [ ] Exact public search trả public quote/fundamental nhưng không trả protected technical metrics.
- [ ] Industry/Fundamental là public research và không chứa technical columns để bypass entitlement.
- [ ] Frontend không phải lớp security duy nhất.
- [ ] Upgrade capacity không tiêu change quota.
- [ ] Downgrade/expiry không xóa Watchlist history.
- [ ] Paid alerts dừng khi entitlement hết hiệu lực.

---

## 25. Change control

Các mục `LOCKED` chỉ đổi khi:

1. Product Owner đồng ý;
2. tăng version Product Spec;
3. đánh giá migration;
4. commit Git.

Agent không được tự đổi pricing, quota, inheritance hoặc permission model.
