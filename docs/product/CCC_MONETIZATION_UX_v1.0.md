# CCC MONETIZATION UX v1.0

**Product:** Chuyện Chợ Chứng  
**Version:** 1.0  
**Status:** LOCKED  
**Effective date:** 2026-08-20  
**Parents:**  
- `CCC_MEMBERSHIP_PERMISSION_MODEL_v1.0.md`
- `CCC_WATCHLIST_RULES_v1.0.md`

---

## 1. Purpose

Tài liệu này định nghĩa trải nghiệm thương mại cho Chuyện Chợ Chứng:

- Free vẫn nhìn thấy sức mạnh thật của scanner;
- user hiểu rõ ranh giới giữa public quote/fundamental và protected technical intelligence;
- paywall xuất hiện ở đúng thời điểm;
- Plus là gói conversion chính;
- locked data không bị leak;
- pricing và upgrade flow nhất quán;
- không dùng dark pattern.

Core idea:

> **Market Quote và Fundamental Research là public. Chỉ CCC Technical Intelligence được bảo vệ theo technical entitlement.**

---

## 2. Monetization philosophy — LOCKED

Không dùng mô hình:

> Free gần như không thấy gì.

Thay vào đó:

```text
PUBLIC MARKET QUOTE + FUNDAMENTAL RESEARCH
→ mọi plan, mọi mã khi có dữ liệu thật
```

```text
CCC TECHNICAL INTELLIGENCE
→ theo technical entitlement của plan
```

Free phải đủ tốt để user:

- tin scanner đang chạy thật;
- thấy aggregate thật;
- dùng full technical detail cho 10 mã;
- hiểu sản phẩm;
- có động lực nâng cấp tự nhiên.

Paid monetizes:

- technical coverage;
- số mã trong technical scope;
- automation alert;
- full-market access.

---

## 3. Core conversion loop

```text
User thấy aggregate toàn thị trường
        ↓
Thấy có nhóm tín hiệu đáng chú ý
        ↓
Muốn biết đó là mã nào
        ↓
Một phần nằm trong entitlement
        ↓
Phần còn lại bị locked
        ↓
User hiểu coverage hiện tại
        ↓
Đổi mã hoặc nâng gói
```

Không cần pop-up quảng cáo trên mọi page load.

---

## 4. Market Overview — FREE FOR ALL

Mọi plan thấy ví dụ:

```text
TOÀN THỊ TRƯỜNG

4/4           14 mã
3/4           38 mã
2/4          126 mã
RVOL30 sớm    21 mã
```

Đây là dữ liệu aggregate thật từ scanner universe.

Không đặt ổ khóa trên chính các aggregate count.

Lý do:

> Aggregate là quyền của mọi user.

---

## 5. Watchlist summary

Gần Market Overview nên có block riêng:

```text
WATCHLIST CỦA TÔI

10 / 10 mã
2 mã đang đạt ≥3 tín hiệu
Còn 7 / 10 lượt đổi
```

UI phải làm rõ:

```text
Toàn thị trường ≠ Watchlist của tôi
```

User Free không được hiểu nhầm hệ thống chỉ quét 10 mã.

---

## 6. Locked signal group — LOCKED UX

Ví dụ:

```text
14 mã đạt 4/4
```

Free có 2 entitled symbols.

Khi click:

```text
14 mã đang đạt 4/4

TRONG PHẠM VI KỸ THUẬT CỦA BẠN
✓ FPT
✓ SSI

NGOÀI PHẠM VI KỸ THUẬT
🔒 •••
🔒 •••
🔒 •••
...
```

Summary:

```text
Bạn xem được 2 / 14 mã
Còn 12 technical discovery identities ngoài phạm vi
```

---

## 7. Large locked groups

Không render 40–50 dòng `•••`.

### Nếu locked_count ≤ 8

Có thể render từng placeholder.

### Nếu locked_count > 8

Ví dụ:

```text
🔒 •••
🔒 •••
🔒 •••
🔒 •••

+ 34 technical discovery identities khác ngoài phạm vi
```

Mục tiêu:

- trực quan;
- tạo tò mò;
- không làm page dài vô nghĩa.

---

## 8. Never leak masked ticker — LOCKED

Không được:

```text
backend trả VIX
→ frontend đổi thành XXX
```

Phải:

```text
backend không trả protected ticker
```

Frontend chỉ biết:

```text
locked_count
```

Security và UX phải cùng một logic.

---

## 9. Exact search outside entitlement

User chủ động search:

```text
VIX
```

Public directory có thể trả:

```text
VIX
Chứng khoán VIX
HOSE
23.500 · +1,2% · KL 2.450.000
Fundamental Research (nếu có dữ liệu thật)
```

Nếu ngoài entitlement:

```text
🔒 CCC Technical Intelligence chưa nằm trong phạm vi của bạn.

Watchlist: 10 / 10
Còn 7 / 10 lượt đổi
```

Actions:

```text
[Đổi một mã trong Watchlist]
[Xem gói nâng cấp]
```

Trả Public Market Quote và Public Fundamental Research; không trả protected technical metrics.

---

## 10. Protected fields in locked search

Locked card không được show:

- KLTB10 hoặc KL ngày/KLTB10;
- signal count;
- RVOL30;
- MA10/MA200 và khoảng cách;
- CCC Signal Rail;
- technical discovery identities;
- technical alerts.

Locked state vẫn phải show public identity, current price, percentage change, current accumulated volume và Public Fundamental Research khi có dữ liệu thật.

---

## 11. Main upgrade triggers — LOCKED

Paywall mạnh chỉ nên xuất hiện ở intent-driven moments.

### Trigger 1 — User mở nhóm tín hiệu toàn thị trường

Ví dụ:

> 14 mã đạt 4/4

nhưng không có technical entitlement cho toàn bộ identities trong nhóm.

### Trigger 2 — User muốn mở kỹ thuật của mã ngoài technical entitlement

Ví dụ VIX.

### Trigger 3 — Watchlist full

```text
10 / 10 mã
```

user muốn thêm.

### Trigger 4 — Change quota exhausted

```text
0 / 10 lượt đổi
```

user muốn thay thêm.

Không biến website thành “cánh đồng ổ khóa”.

---

## 12. Upgrade dialog — LOCKED CONTENT

Dialog phải trả lời:

1. User đang ở gói nào?
2. Hạn mức hiện tại?
3. Đang bị chặn vì lý do gì?
4. Gói cao hơn đem lại gì?
5. CTA là gì?

Ví dụ:

```text
Bạn đang dùng Free

Theo dõi chi tiết: 10 / 10 mã
Lượt đổi còn lại: 7 / 10

Nâng cấp Plus:
✓ 50 mã
✓ 50 lượt đổi / chu kỳ
✓ Email
✓ Telegram

300.000đ / tháng

[Xem gói Plus]
[Để sau]
```

---

## 13. Plus positioning — LOCKED

Plus là plan được ưu tiên trên pricing UI.

Badge:

> **Phổ biến nhất**

Core message:

> **50 mã + cảnh báo Email & Telegram**

Có thể dùng message:

> **Tín hiệu tìm đến bạn.**

Nhưng không biến thành hứa hẹn lợi nhuận.

---

## 14. Pricing table — LOCKED v1.0

| Feature | Free | Basic | Plus ⭐ | Pro | Full Market |
|---|---:|---:|---:|---:|---:|
| Giá/tháng | 0đ | 100k | 300k | 500k | 1.000k |
| Market aggregate toàn universe | ✓ | ✓ | ✓ | ✓ | ✓ |
| Market Quote | Public | Public | Public | Public | Public |
| Fundamental Research | Public | Public | Public | Public | Public |
| CCC Technical Intelligence | 10 | 20 | 50 | 100 | Toàn thị trường |
| Watchlist technical entitlement | 10 | 20 | 50 | 100 | Không giới hạn technical scope |
| Lượt đổi/cycle | 10 | 20 | 50 | 100 | Không giới hạn technical scope |
| Email alert | — | — | ✓ | ✓ | ✓ |
| Telegram alert | — | — | ✓ | ✓ | ✓ |
| Kế thừa toàn bộ Plus | — | — | ✓ | ✓ | ✓ |

Pro copy:

> Bao gồm toàn bộ tính năng Plus.

Full copy:

> Bao gồm toàn bộ tính năng Pro.

---

## 15. Free value proposition

Nên nói:

```text
FREE

10 mã trong phạm vi CCC Technical
10 lượt đổi mỗi chu kỳ
Xem tổng quan toàn thị trường
0đ
```

Không nói:

> “Chỉ được 10 mã”.

---

## 16. Basic value proposition

```text
BASIC

20 mã
20 lượt đổi
Xem tổng quan toàn thị trường
100.000đ / tháng
```

Basic tăng capacity nhưng chưa có automation alert.

---

## 17. Plus value proposition

```text
PLUS

50 mã
50 lượt đổi
Email
Telegram
300.000đ / tháng
```

Đây là gói chủ lực để convert.

---

## 18. Pro value proposition

```text
PRO

100 mã
100 lượt đổi
Email
Telegram
Toàn bộ tính năng Plus
500.000đ / tháng
```

Không được làm Pro thiếu feature Plus.

---

## 19. Full Market value proposition

```text
FULL MARKET

CCC Technical Intelligence toàn scanner universe
Email + Telegram
Toàn bộ tính năng Pro
1.000.000đ / tháng
```

Không nói:

> 800 mã vĩnh viễn.

Dùng:

> Toàn scanner universe

và có thể hiện count động:

> Hiện tại ~800 mã.

---

## 20. Watchlist full flow

Ví dụ Free:

```text
10 / 10 mã
```

User muốn thêm VIX.

UI:

```text
Watchlist đã đạt giới hạn

10 / 10 mã đang theo dõi

Để thêm VIX:
• Đổi một mã hiện tại — dùng 1 lượt đổi
• Nâng cấp để tăng số mã

[Đổi mã]
[Xem gói]
```

Nếu user còn quota, phải cho phép replace.

---

## 21. Change quota exhausted

```text
Bạn đã dùng hết lượt đổi trong chu kỳ này

10 / 10 lượt đã sử dụng
Reset vào 18/09/2026

Watchlist hiện tại vẫn hoạt động bình thường.

[Nâng cấp gói]
[Đóng]
```

Không làm user tưởng 10 mã hiện tại bị khóa.

---

## 22. Upgrade success UX

Free → Plus:

```text
Bạn đã nâng cấp lên Plus

Quyền mới:
✓ 50 mã
✓ 50 lượt đổi / chu kỳ
✓ Email
✓ Telegram

Bạn có thể thêm 40 mã vào capacity vừa mở
mà không sử dụng lượt đổi.
```

Điểm “thêm slot mới không tốn quota” phải rõ.

---

## 23. Downgrade UX

Nếu:

```text
Watchlist hiện tại = 80
New plan limit = 50
```

UI:

```text
Gói Plus cho phép 50 mã

Trước khi gói mới có hiệu lực,
hãy chọn 50 mã muốn tiếp tục theo dõi.

[Chọn mã giữ lại]
```

Không:

- random remove;
- silent delete;
- mất history.

---

## 24. Expiry UX

Paid hết hạn:

```text
Gói Pro đã hết hạn

Tài khoản trở về Free:
• 10 mã
• 10 lượt đổi / chu kỳ
• Email/Telegram tạm dừng

Hãy chọn 10 mã muốn giữ trong Watchlist.
```

Market aggregate vẫn xem được.

---

## 25. Coverage language

Có thể dùng:

```text
Bạn xem được 8 / 14 mã trong nhóm này
```

Hoặc:

```text
Độ phủ Watchlist: 8 / 14
```

Không nên mặc định dùng wording gây áp lực kiểu:

> “Bạn đang bỏ lỡ 43% cơ hội.”

Ưu tiên trung tính.

---

## 26. No dark patterns — LOCKED

Không dùng:

- fake countdown;
- fake scarcity;
- fake discount;
- fake signal;
- popup upgrade mỗi page load;
- nút đóng bị giấu;
- misleading CTA;
- ép upgrade khi user vẫn có quyền replace hợp lệ.

Conversion phải đến từ product value thật.

---

## 27. No investment-advice wording

Không dùng:

- “Nâng cấp để không bỏ lỡ lợi nhuận”
- “Mua ngay để bắt đáy”
- “14 cơ hội chắc chắn tăng”
- “Tín hiệu mua”

Có thể dùng:

- “14 mã đạt 4/4 điều kiện scanner”
- “12 technical discovery identities ngoài phạm vi”
- “Nâng cấp để tăng phạm vi theo dõi”

---

## 28. Overview membership hierarchy

Recommended:

```text
DATA TRUST

TOÀN THỊ TRƯỜNG
14 mã 4/4 · 38 mã 3/4 · ...

WATCHLIST CỦA TÔI
10/10 mã
2 mã ≥3 tín hiệu
7/10 lượt đổi còn lại

CÁC MÃ ĐÁNG CHÚ Ý TRONG WATCHLIST
...
```

Market aggregate là product value, không phải pricing banner.

---

## 29. Scanner membership modes

Với Free/Basic/Plus/Pro, có thể có 2 concept:

```text
Watchlist của tôi
```

và:

```text
Toàn thị trường
```

Nhưng:

- mọi mode → public identity/quote rows;
- Watchlist mode → entitled technical fields;
- market-wide mode → public rows + technical aggregate/locked state;
- không tải protected full technical rows.

Full:

- full technical market mode, không tự động alert mọi mã.

Exact v19 layout sẽ test trên staging.

---

## 30. Industry / Fundamental

Hai route này là Public Fundamental Research.

Rule:

- public cho mọi symbol khi field thật tồn tại;
- giữ missing-data, freshness và score-coverage rules;
- không trộn hoặc đưa signal count, CCC Signal Rail, RVOL30, MA10, MA200 hay technical signal columns vào research table;
- nếu một interaction mở CCC Technical Intelligence, phần đó vẫn kiểm tra technical entitlement riêng.

Public Research không phải lối bypass vì protected technical fields không thuộc research payload.

---

## 31. Stock Detail deep link

Nếu user mở URL của locked symbol:

Không flash data rồi mới hide.

Backend trả public quote/fundamental và technical locked state ngay.

UI:

```text
VIX · Chứng khoán VIX
23.500 · +1,2% · KL 2.450.000

Cơ bản · Public

Kỹ thuật · 🔒 Ngoài phạm vi hiện tại.

[Quản lý Watchlist]
[Xem gói nâng cấp]
```

---

## 32. Alert upsell

Free/Basic có thể thấy:

> **Từ Plus: nhận cảnh báo tín hiệu qua Email & Telegram.**

Không giả lập rằng user đã nhận alert.

---

## 33. Alert onboarding after Plus upgrade

Sau upgrade:

```text
Bật cảnh báo?

[Thêm Email]
[Kết nối Telegram]

Bạn có thể làm sau trong Cài đặt.
```

Không bắt buộc configure alert mới được dùng website.

---

## 34. Pricing page order

Recommended:

1. title;
2. một câu giải thích model;
3. plan cards;
4. comparison gọn;
5. Watchlist + change quota explanation;
6. Email/Telegram;
7. FAQ;
8. disclaimer.

Không mở đầu bằng bảng feature khổng lồ.

---

## 35. FAQ bắt buộc

### Scanner có chỉ quét số mã trong gói của tôi?

> Không. Hệ thống vẫn quét toàn scanner universe. Market Quote và Fundamental Research là public; gói của bạn quyết định phạm vi CCC Technical Intelligence và theo dõi cá nhân.

### Lượt đổi mã là gì?

> Mỗi symbol mới được đưa vào Watchlist sau thiết lập ban đầu tính 1 lượt.

### Xóa mã có tính lượt không?

> Không.

### Nâng gói rồi thêm các slot mới có tính lượt không?

> Không.

### Từ gói nào có Email + Telegram?

> Plus trở lên.

---

## 36. Manual payment MVP

Phase đầu có thể:

```text
[Xem gói Plus]
→ hướng dẫn thanh toán / liên hệ
→ Admin xác nhận
→ subscription active
```

UI không giả vờ payment automation nếu chưa có.

---

## 37. Recommended analytics events

Có thể track privacy-respecting events:

```text
pricing_view
locked_group_open
locked_stock_search
watchlist_limit_hit
change_quota_limit_hit
upgrade_cta_click
plan_selected
subscription_activated
alert_setup_started
alert_setup_completed
```

Không cần log protected ticker vào analytics nếu không cần.

---

## 38. Conversion metrics

Theo dõi:

- Free → paid conversion;
- Free → Plus conversion;
- locked group → pricing click;
- locked search → replace;
- locked search → upgrade;
- watchlist limit → upgrade;
- alert setup completion;
- paid renewal.

Plus là conversion target chính.

---

## 39. Staging test states

`test.chuyenchochung.com` phải test tối thiểu:

1. Free, Watchlist 6/10.
2. Free, 10/10, quota 7/10.
3. Free, 10/10, quota 0/10.
4. Plus, 38/50.
5. Pro, 100/100.
6. Full.
7. Expired paid → reduction required.
8. Downgrade over limit.
9. Signal group có visible + locked.
10. Signal group 0 visible + nhiều locked.

Trước khi auth thật xong có thể mock các state này trên staging, nhưng phải đánh dấu test.

---

## 40. Acceptance criteria

- [ ] Free thấy aggregate toàn thị trường.
- [ ] Free dùng full supported technical detail cho 10 entitled symbols.
- [ ] Mọi plan thấy Public Market Quote và Fundamental Research cho mọi mã khi có dữ liệu thật.
- [ ] Locked group cho thấy total/visible/locked.
- [ ] Browser response không chứa protected locked ticker.
- [ ] Exact search show public identity/quote/fundamental nhưng không leak protected technical metrics.
- [ ] Plus được highlight là recommended.
- [ ] Pro kế thừa Plus.
- [ ] Full kế thừa Pro.
- [ ] Email/Telegram bắt đầu từ Plus.
- [ ] Upgrade prompt chỉ xuất hiện ở intent-driven moments.
- [ ] Replace vẫn được cung cấp nếu còn quota.
- [ ] Capacity và quota là hai khái niệm rõ.
- [ ] Không dark pattern.
- [ ] Không investment-guarantee wording.
- [ ] Downgrade/expiry giữ history.
- [ ] Industry/Fundamental là Public Research và không chứa technical columns.
- [ ] Deep link không flash protected data.

---

## 41. Out of scope v1.0

Chưa định nghĩa:

- coupon;
- sale campaign;
- annual billing;
- affiliate/referral;
- payment gateway tự động;
- trial ngoài Free;
- add-on symbols;
- enterprise pricing;
- personalized AI investment recommendation;
- ads.

---

## 42. Change control

Agent không được tự:

- đổi plan price;
- đổi quota;
- thêm paywall popup;
- lộ locked ticker;
- tạo discount giả;
- bỏ feature Plus khỏi Pro/Full;
- làm Free mất Market Intelligence aggregate.

Mọi thay đổi cần Product Owner approval + version mới.
