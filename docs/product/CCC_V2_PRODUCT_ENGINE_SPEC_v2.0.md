# CCC V2 — PRODUCT, REALTIME & SIGNAL ENGINE SPEC v2.0

**Product:** Chuyện Chợ Chứng (CCC)  
**Version:** 2.0  
**Status:** LOCKED IMPLEMENTATION BASELINE  
**Effective date:** 2026-09-12  
**Target first live session:** Monday, 2026-09-14  
**Owner:** Product Owner — Chuyện Chợ Chứng  
**Primary implementation target:** `manhcang2026/vnstock-market-scanner`  
**Recommended path in source:** `docs/product/CCC_V2_PRODUCT_ENGINE_SPEC_v2.0.md`

---

# 0. Authority

Tài liệu này là **source of truth cho CCC Version 2** đối với:

- realtime market-data architecture;
- Market Session Engine;
- Volume Engine V2;
- Price Engine V2;
- CCC Signal Engine V2;
- WebSocket behavior;
- stock-detail chart behavior;
- signal state + Vietnamese conclusion;
- signal heat bar;
- technical entitlement theo user/watchlist/plan;
- nguyên tắc bảo vệ logic nội bộ;
- phạm vi release V2 đầu tiên.

Tài liệu này **không phải một cuộc redesign UI/UX**.

Khi có xung đột, áp dụng theo thứ tự:

1. Quyết định rõ ràng mới nhất của Product Owner.
2. `CCC_V2_PRODUCT_ENGINE_SPEC_v2.0.md` đối với engine/realtime/signal behavior của CCC V2.
3. `CCC_WATCHLIST_RULES_v1.0.md` đối với Watchlist và change quota.
4. `CCC_MEMBERSHIP_PERMISSION_MODEL_v1.0.md` đối với quyền truy cập.
5. `CCC_UIUX_MASTER.md` đối với UI/UX tổng thể còn lại.
6. `CCC_COMPONENT_RULES.md`.
7. `CCC_PAGE_PATTERNS.md`.
8. Hành vi production hiện hữu nếu chưa được tài liệu V2 thay thế.
9. Sở thích cá nhân của coder/designer/AI.

> **Do not redesign Chuyện Chợ Chứng because the engine changed.**
>
> CCC V2 thay đổi trí thông minh bên trong nhiều hơn thay đổi bề ngoài.

---

# 1. Why CCC V2 exists

CCC V1 dùng nhiều tín hiệu kỹ thuật độc lập và biểu diễn theo dạng số lượng điều kiện đạt được, ví dụ `2/4`, `3/4`, `4/4`.

Cách này có ba hạn chế:

1. user phải tự hiểu nhiều tín hiệu rời rạc;
2. tín hiệu giá cũ không phản ánh tốt “thời điểm dòng tiền bắt đầu làm giá chuyển động”;
3. số lượng tín hiệu đạt được không kể được câu chuyện diễn biến của một mã theo thời gian.

CCC V2 chuyển tư duy từ:

```text
4 independent checks
        ↓
signal count
        ↓
0/4 → 4/4
```

sang:

```text
Market activity
      ↓
Dòng tiền xuất hiện
      ↓
Giá phản ứng / xác nhận
      ↓
Momentum duy trì
      ↓
Suy yếu / kết thúc

hoặc

Volume mạnh + giá xấu
      ↓
Áp lực bán
```

CCC V2 phải trả lời câu hỏi quan trọng hơn:

> **“Mã này đang ở trạng thái gì ngay lúc này?”**

không chỉ:

> “Có bao nhiêu điều kiện đang đúng?”

---

# 2. Product philosophy — LOCKED

## 2.1 Complex inside, simple outside

Engine có thể sử dụng nhiều dữ liệu và phép đánh giá nội bộ.

User không cần nhìn toàn bộ cách CCC tính.

Nguyên tắc:

```text
INTERNAL INTELLIGENCE
        ↓
CCC ENGINE
        ↓
SIMPLE VIETNAMESE CONCLUSION
        ↓
USER USES OWN METHOD TO DECIDE
```

CCC là công cụ **phát hiện và diễn giải trạng thái thị trường**.

CCC không thay thế hệ thống giao dịch riêng của user.

User có thể:

- đọc trạng thái CCC;
- mở biểu đồ;
- kết hợp price action;
- hỗ trợ/kháng cự;
- MA;
- Wyckoff;
- Fibonacci;
- fundamental;
- hoặc phương pháp cá nhân khác;

sau đó tự quyết định.

### Product positioning

> **CCC phát hiện điều đáng chú ý. Người dùng tự ra quyết định.**

---

## 2.2 Objective data remains visible

Không được hiểu “simple outside” là giấu hết dữ liệu.

CCC vẫn phải hiển thị các chỉ số khách quan, quen thuộc và dễ hiểu như hiện tại, ví dụ:

- mã;
- tên công ty;
- sàn;
- giá hiện tại;
- % thay đổi;
- khối lượng hiện tại / khối lượng lũy kế;
- MA10;
- MA200;
- các field cơ bản hiện đang thuộc product contract;
- thời gian cập nhật;
- freshness/data status khi cần.

Các chỉ số cơ bản này giúp user:

- hiểu bối cảnh;
- đối chiếu trạng thái CCC;
- áp dụng phương pháp riêng.

Điểm khác biệt của V2 là:

> **Câu kết luận tiếng Việt của CCC trở thành thông tin quan trọng nhất trong vùng signal.**

---

## 2.3 CCC does not expose its recipe

Không expose công khai:

- exact RVOL threshold;
- exact Price5 threshold;
- exact Price15 threshold;
- exact breakout threshold;
- weighting;
- scoring weights;
- liquidity filter formula;
- hysteresis constants;
- confidence calculation;
- proprietary state-transition recipe;
- exact trigger-combination rules.

Các thông tin trên là **CCC proprietary intelligence**.

Tài liệu public chỉ định nghĩa:

- loại metric;
- ý nghĩa;
- data contract;
- state output;
- system behavior.

Không định nghĩa exact recipe.

---

# 3. Repository security rule — CRITICAL

Repository hiện tại có thể public.

Do đó:

> **Không commit bí mật thuật toán CCC vào public documentation, public frontend hoặc frontend bundle.**

Không được hard-code proprietary threshold/weight trong JavaScript gửi xuống browser.

Frontend chỉ cần nhận kết quả đã được server tính:

```text
signal_state
signal_level
signal_timestamp
signal_summary
```

Các threshold/weight thực tế phải:

- tồn tại server-side;
- có thể chỉnh bằng configuration;
- không được expose qua public API;
- không được serialise vào frontend payload;
- không được ghi đầy đủ vào public Markdown.

Nếu CCC muốn bảo vệ engine ở mức cao hơn, phần evaluation proprietary nên chạy ở:

```text
ccc-realtime-01
```

hoặc service/repository private riêng.

Public repository có thể giữ:

- interface;
- schema;
- client code;
- generic orchestration;

nhưng không nên chứa recipe đầy đủ nếu recipe được coi là lợi thế cạnh tranh.

---

# 4. V2 scope — what changes and what stays

## 4.1 Changes

CCC V2 thay đổi lớn ở backend:

- SSI trở thành canonical Vietnam market-data source;
- WebSocket-first realtime architecture;
- Market Session Engine;
- Volume Engine V2;
- Price Engine V2;
- Signal State Machine;
- realtime subscription model;
- chart realtime pipeline;
- server-side technical entitlement;
- signal-event persistence;
- feed-health/Data Trust;
- future indicator-pack architecture.

## 4.2 Stays

CCC V2 **không được redesign sản phẩm một cách toàn diện**.

Giữ tối đa:

- navigation hiện tại;
- routes hiện tại;
- header;
- search behavior;
- Market Pulse layout hiện tại;
- desktop shell;
- mobile information hierarchy;
- scanner-table density;
- dark/light behavior hiện tại;
- Watchlist workflow;
- membership mental model;
- public fundamental screens;
- typography/design DNA;
- signal-bar visual pattern hiện user đã quen.

### UI rule

> **80–90% giao diện nên tạo cảm giác quen thuộc.**

User phải cảm nhận:

- dữ liệu nhanh hơn;
- trạng thái rõ hơn;
- chart hữu ích hơn;

chứ không phải:

- website mới hoàn toàn;
- phải học lại navigation;
- phải hiểu thêm hàng loạt thuật ngữ.

---

# 5. Existing product hierarchy remains valid

Data/access hierarchy vẫn là:

```text
PUBLIC LAYER
Market Quote + Fundamental Research

MEMBERSHIP LAYER
CCC Technical Intelligence

PERSONALIZATION LAYER
Watchlist + Alerts + Account
```

## Public Market Quote

Có thể tiếp tục cho phép user xem với toàn scanner universe:

- ticker;
- company;
- exchange;
- current price;
- percentage change;
- current accumulated volume;
- các public fields khác theo contract hiện hành.

## Public Fundamental Research

Giữ nguyên nguyên tắc hiện tại.

## Protected CCC Technical Intelligence

V2 mở rộng khái niệm này bao gồm:

- CCC signal state;
- signal heat/intensity;
- advanced flow metrics;
- advanced price momentum metrics;
- technical indicator packs;
- technical discovery identities;
- technical alerts;
- signal event history theo quyền;
- các derived metrics proprietary.

---

# 6. Canonical realtime architecture — LOCKED

Kiến trúc chuẩn:

```text
                    ┌─────────────────────────┐
                    │ SSI Market Data         │
                    │ WebSocket + REST repair │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ ccc-realtime-01         │
                    │ Realtime Market State   │
                    └────────────┬────────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
        Market Session       Volume Engine     Price Engine
            Engine               V2               V2
                │                │                │
                └────────────────┼────────────────┘
                                 ▼
                       CCC Signal Engine V2
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
             Current State                Signal Events
                   │                           │
                   ▼                           ▼
          CCC WebSocket/SSE               Persistence
                   │
                   ▼
               Browser
```

## Core principle

Không sử dụng kiến trúc:

```text
SSI
 ↓
poll repeatedly
 ↓
Supabase
 ↓
browser polls Supabase
```

cho realtime board.

Supabase không phải realtime firehose chính.

---

# 7. Realtime data responsibilities

## 7.1 SSI

SSI là canonical provider cho Vietnam market data trong CCC V2.

Primary realtime:

```text
SSI WebSocket
```

REST dùng cho:

- historical bootstrap;
- backfill;
- reconnect gap repair;
- verification;
- baseline build/rebuild.

Không dùng REST polling dày đặc thay WebSocket nếu WebSocket đang khỏe.

## 7.2 `ccc-realtime-01`

Realtime VPS/service chịu trách nhiệm:

- giữ current state của scanner universe;
- nhận SSI realtime feed;
- aggregate tick thành candle;
- quản lý session;
- tính metrics;
- chạy CCC Signal Engine;
- phát delta tới browser;
- kiểm soát technical entitlement;
- ghi selected events/state xuống persistent storage;
- thực hiện reconnect/recovery;
- monitor feed health.

Không ghi mọi tick vào Supabase.

## 7.3 Supabase

Supabase ưu tiên cho:

- auth;
- user;
- plans;
- Watchlist;
- entitlement metadata;
- stock metadata;
- fundamentals;
- baseline summary nếu phù hợp;
- latest scanner snapshot/selective state;
- signal-event history;
- daily history;
- audit/business data.

Không sử dụng Supabase Free như kho raw 1-minute all-market lâu dài.

---

# 8. WebSocket behavior — LOCKED

## 8.1 No page refresh

WebSocket phải update component tại chỗ.

Ví dụ user đang xem HPG:

```text
Browser
  │
  └─ subscribe symbol:HPG
```

khi HPG thay đổi:

```text
server → delta HPG → browser → update UI
```

Không:

- reload page;
- reset scroll;
- reset chart state;
- mất tab;
- mất filter.

## 8.2 Subscription by need

Không broadcast toàn bộ 800 mã đầy đủ tới mọi user.

Một browser có thể subscribe nhiều channel logic:

```text
market:pulse
watchlist:<user>
scanner:<scope>
symbol:HPG
alerts:<user>
```

Nếu user đang ở Stock Detail HPG:

- HPG nhận data chi tiết cần thiết;
- Watchlist có thể nhận lightweight state;
- market pulse có thể nhận aggregate;
- 700+ mã không liên quan không cần gửi full technical payload.

## 8.3 Switching symbol

Khi user chuyển:

```text
HPG → SSI
```

client phải:

```text
unsubscribe symbol:HPG
subscribe symbol:SSI
```

Không tạo connection mới vô hạn.

## 8.4 Scanner page

Scanner toàn thị trường không nên nhận full snapshot 800 rows mỗi tick.

Dùng:

```text
delta update
```

ví dụ:

```text
HPG price changed
SSI state changed
VIX signal level changed
```

Browser patch đúng row.

Có thể batch delta theo nhịp ngắn để tránh render quá nhiều.

---

# 9. Market Session Engine — LOCKED ARCHITECTURE

Không viết scattered time checks kiểu:

```text
if time > ...
if hour == ...
```

trong từng metric.

Phải có một Market Session Engine dùng chung.

Mỗi market state trả về tối thiểu:

```text
exchange
trading_date
session_type
session_id
session_start
session_end
elapsed_valid_trading_minutes
is_continuous
is_auction
is_break
```

---

# 10. Exchange/session behavior

## 10.1 HOSE

Conceptual sessions:

```text
OPEN_AUCTION
AM_CONTINUOUS
LUNCH_BREAK
PM_CONTINUOUS
CLOSE_AUCTION
CLOSED
```

Rules:

- 09:00–09:15 không coi là normal continuous 15-minute window;
- ATO có thể được đánh giá bằng Opening/ATO volume logic riêng;
- continuous momentum bắt đầu sau ATO;
- Price5/RVOL rolling bắt đầu sau đủ valid continuous minutes;
- lunch reset rolling momentum window;
- ATC tách khỏi normal continuous rolling window.

## 10.2 HNX

Conceptual sessions:

```text
AM_CONTINUOUS
LUNCH_BREAK
PM_CONTINUOUS
CLOSE_AUCTION
CLOSED
```

Có thể đánh giá opening rolling flow ngay từ đầu continuous session.

## 10.3 UPCoM

Conceptual sessions:

```text
AM_CONTINUOUS
LUNCH_BREAK
PM_CONTINUOUS
CLOSED
```

Không áp HOSE auction semantics cho UPCoM.

---

# 11. Lunch-break rule — CRITICAL

Không được tạo rolling window giả qua nghỉ trưa.

Sai:

```text
13:05 compares with 11:xx
```

để tạo Price15/RVOL15.

Đúng:

```text
13:00 = new continuous momentum session
13:05 = only 5 valid PM minutes
13:15 = first full PM 15-minute window
```

### Important distinction

**Day/session cumulative volume** không reset lúc nghỉ trưa.

**Rolling momentum windows** reset theo continuous session.

---

# 12. Volume Engine V2

Volume Engine sử dụng nhiều perspective khác nhau.

## 12.1 DayRVOL / Dòng tiền phiên

Concept:

```text
today cumulative volume from session open to t
------------------------------------------------
average cumulative volume to same valid market time
over prior valid sessions
```

User-facing có thể dùng wording đơn giản như:

```text
Dòng tiền phiên
```

Helper nếu cần:

```text
KL tích lũy / TB cùng thời điểm
```

Không cần công khai recipe đầy đủ.

## 12.2 RVOL30

Concept:

```text
latest rolling 30 valid trading minutes
----------------------------------------
average same rolling market-time window
across prior valid sessions
```

RVOL30 đóng vai trò:

- confirmation;
- sustained activity;
- smoothing;
- context.

## 12.3 RVOL15

Concept:

```text
latest rolling 15 valid trading minutes
----------------------------------------
average same rolling market-time window
across prior valid sessions
```

RVOL15 đóng vai trò:

- fast detection;
- early flow anomaly;
- internal signal evaluation.

RVOL15 không bắt buộc phải được show public cho mọi user.

## 12.4 Opening volume logic

Vì session khác nhau, opening logic không được dùng một công thức clock-time duy nhất.

HNX/UPCoM có thể dùng:

```text
Opening RVOL5
Opening RVOL10
```

sau đủ valid minutes.

HOSE ATO dùng dedicated opening/auction comparison.

Sau đó continuous session mới chuyển sang rolling RVOL logic.

## 12.5 Historical-session coverage

Baseline phải biết:

```text
historical_sessions_available
historical_sessions_target
```

Ví dụ conceptual:

```text
8 / 10 sessions
```

Không giả định mã mới niêm yết hoặc mã bị đình chỉ luôn có đủ lịch sử.

Signal Engine có thể giảm confidence hoặc suppress một số evaluation khi baseline coverage quá thấp.

Exact policy server-side configurable.

## 12.6 Illiquid/restricted instruments

Phải có data-quality/liquidity gate.

Không để:

- vài lệnh nhỏ;
- missing candle;
- suspended symbol;
- rare trade;

tạo RVOL cực lớn và bị hiểu thành cơ hội thật.

Exact filter là proprietary server-side logic.

---

# 13. Price Engine V2

## 13.1 Why old price logic is insufficient

Price signal V1 từng dựa mạnh vào thay đổi so với previous close.

Metric này vẫn hữu ích làm **display/context**.

Nhưng nó không đủ để phát hiện:

> “dòng tiền vừa bắt đầu làm giá phản ứng”.

V2 bổ sung short-horizon price behavior nội bộ.

## 13.2 Price5

Concept:

```text
current_price
---------------------- - 1
price 5 valid trading minutes ago
```

Dùng nội bộ để phát hiện phản ứng nhanh.

## 13.3 Price15

Concept:

```text
current_price
----------------------- - 1
price 15 valid trading minutes ago
```

Dùng nội bộ cho short-term confirmation/context.

## 13.4 Breakout context

Engine có thể đánh giá:

- rolling local high;
- prior short-window high;
- breakout confirmation;
- breakdown context.

Exact rule không public.

## 13.5 Trigger anchor

Khi engine phát hiện activity đáng chú ý, có thể lưu internal anchor:

```text
trigger_time
trigger_price
trigger_context
```

Từ đó engine theo dõi xem giá:

- xác nhận;
- không xác nhận;
- suy yếu;
- đảo chiều.

Trigger data không bắt buộc show public.

---

# 14. CCC Signal Engine V2

Signal Engine nhận input từ:

```text
Market Session Engine
Volume Engine
Price Engine
Liquidity/Data Quality
Trend Context
Current State History
```

và output:

```text
signal_state
signal_level
signal_timestamp
signal_summary_vi
signal_reason_code_internal
```

Frontend **không tự tính signal state**.

---

# 15. Signal states — USER-FACING STANDARD

## 15.1 `NORMAL`

Internal state.

Không cần show thành một alert lớn.

User có thể chỉ thấy:

```text
Bình thường
```

hoặc không có special state tùy component.

## 15.2 `FLOW_APPEARING`

Vietnamese canonical label:

> **Dòng tiền đang xuất hiện**

Ý nghĩa user-facing:

> Hoạt động giao dịch đang trở nên đáng chú ý, nhưng diễn biến giá chưa đủ để CCC xác nhận trạng thái mạnh hơn.

Không public threshold.

## 15.3 `FLOW_PRICE_CONFIRMED`

Canonical label:

> **Dòng tiền & giá đã xác nhận**

Đây là **primary positive state** của CCC V2.

Ý nghĩa:

> CCC phát hiện sự đồng thuận đủ mạnh giữa hoạt động giao dịch và phản ứng giá theo engine nội bộ.

Không đồng nghĩa:

- khuyến nghị mua;
- đảm bảo tăng giá;
- điểm mua bắt buộc.

## 15.4 `MOMENTUM_MAINTAINED`

Canonical label:

> **Xu hướng đang được duy trì**

Ý nghĩa:

> Một trạng thái đáng chú ý đã xuất hiện trước đó và engine đánh giá diễn biến hiện tại vẫn đang được duy trì.

## 15.5 `MOMENTUM_WEAKENING`

Canonical label:

> **Động lượng đang suy yếu**

Ý nghĩa:

> Cường độ của trạng thái trước đó đang giảm hoặc giá không còn phản ứng tốt như trước.

## 15.6 `SELLING_PRESSURE`

Canonical label:

> **Áp lực bán đang tăng**

Ý nghĩa:

> Hoạt động giao dịch mạnh nhưng phản ứng giá có tính tiêu cực theo engine.

Đây là bearish/risk state riêng.

Không được gộp volume lớn vào bullish flow chỉ vì volume cao.

---

# 16. State transition philosophy

Exact state machine recipe là proprietary.

Public implementation contract chỉ yêu cầu:

```text
NORMAL
  ↓
FLOW_APPEARING
  ↓
FLOW_PRICE_CONFIRMED
  ↓
MOMENTUM_MAINTAINED
  ↓
MOMENTUM_WEAKENING
```

và bearish branch:

```text
ANY RELEVANT STATE
        ↓
SELLING_PRESSURE
```

Engine phải có hysteresis/debounce để tránh:

```text
A → B → A → B
```

mỗi vài giây do nhiễu.

Exact confirmation count/time window là server-side config.

---

# 17. Signal level / heat bar — LOCKED UX DIRECTION

User đã quen signal bar hiện tại.

**Không thay component bằng visual hoàn toàn mới.**

Giữ concept:

```text
segmented / heat-style signal bar
```

nhưng thay semantics.

V1:

```text
segments = number of independent signals
```

V2:

```text
segments = normalized CCC signal intensity / confidence level
```

## 17.1 Important

`signal_state` và `signal_level` là hai field khác nhau.

- `signal_state` = CCC kết luận điều gì đang xảy ra.
- `signal_level` = cường độ/độ đáng chú ý dùng để render heat bar.

State label là authoritative.

Heat bar là quick visual cue.

## 17.2 Preserve familiar geometry

Nếu component hiện tại dùng 4 segment:

```text
□ □ □ □
■ □ □ □
■ ■ □ □
■ ■ ■ □
■ ■ ■ ■
```

ưu tiên giữ số segment/layout hiện tại để giảm UI churn.

Không cần display:

```text
3/4
4/4
```

nếu số đó làm user hiểu sai rằng đang đếm 4 rule cũ.

## 17.3 Colors

Không định nghĩa lại palette tùy tiện trong spec này.

Phải dùng CCC Design System hiện tại.

Color semantics phải giúp phân biệt:

- neutral;
- emerging;
- positive confirmed;
- maintained;
- weakening;
- selling/risk.

Không thay toàn bộ màu website chỉ để phục vụ V2.

---

# 18. Scanner UI — MINIMAL CHANGE RULE

Scanner hiện tại tiếp tục là primary discovery surface.

Default row giữ các chỉ số cơ bản mà user đã quen.

Conceptual row:

```text
Mã
Giá
% thay đổi
Khối lượng
MA10
MA200
[existing basic fields]
CCC heat bar
CCC trạng thái
Thời gian cập nhật/tín hiệu khi cần
```

Không bắt buộc row phải đúng thứ tự trên nếu current production layout khác.

### Required V2 change

Khu vực V1:

```text
2/4
3/4
4/4
```

được chuyển dần sang:

```text
heat bar
+
Vietnamese CCC status
```

Ví dụ:

```text
HPG
27.40
+1.8%
18.2M
MA10 26.9
MA200 28.1
████
Dòng tiền & giá đã xác nhận
```

---

# 19. Do not overload scanner

Không mặc định thêm hàng loạt cột:

- Price5;
- Price15;
- RVOL15;
- RVOL30;
- breakout;
- trigger price;
- score;
- confidence;
- internal reasons.

Các metric này có thể:

- internal only;
- nằm trong optional indicator pack;
- nằm trong Stock Detail;
- hoặc được mở theo plan/quyền sau này.

Default scanner phải vẫn scan nhanh bằng mắt.

---

# 20. Stock Detail

Stock Detail là nơi user chuyển từ:

```text
CCC discovery
```

sang:

```text
user's own analysis
```

Do đó page này phải cho user đủ context khách quan nhưng không tiết lộ recipe CCC.

---

# 21. Chart V2

Chart là một phần quan trọng của CCC V2.

Mục tiêu:

> Cho user thấy **CCC phát hiện khi nào**, sau đó user tự đánh giá diễn biến giá theo phương pháp của họ.

## 21.1 Minimum chart data

Intraday chart nên hỗ trợ:

- price/candlestick;
- volume;
- suitable intraday timeframe;
- realtime update;
- existing/basic MA overlay khi phù hợp;
- CCC signal marker.

## 21.2 CCC marker

Ví dụ:

```text
10:17
CCC phát hiện tín hiệu
```

hoặc state-specific marker:

```text
10:17
Dòng tiền & giá đã xác nhận
```

Không cần marker giải thích:

```text
RVOL15 crossed X
Price5 crossed Y
Breakout threshold Z
```

## 21.3 Why timestamp matters

User có thể nhìn:

```text
CCC signal at 10:17
```

sau đó dùng phương pháp riêng và quyết định:

```text
tôi chỉ tham gia nếu setup cá nhân xác nhận lúc 10:20
```

CCC trở thành detection tool, không phải black-box buy/sell instruction.

---

# 22. Indicator architecture — FUTURE READY

UI có thể chuẩn bị mô hình:

```text
Indicator / Bộ chỉ báo
```

không cần hoàn thiện toàn bộ trước first V2 launch.

Possible packs:

```text
BASIC
FLOW
MOMENTUM
BREAKOUT
FUTURE_PACK_X
```

## BASIC

Có thể gồm các thông tin user đã quen:

- price;
- volume;
- MA10;
- MA200;
- basic change/context.

## FLOW

Có thể mở additional flow views/derived metrics.

## MOMENTUM

Có thể mở short-horizon momentum metrics.

## BREAKOUT

Có thể mở advanced breakout context.

Exact contents có thể điều chỉnh sau.

---

# 23. Indicator-pack UI rule

Không tạo giao diện hoàn toàn khác cho từng user.

Dùng cùng một UI shell.

User có quyền pack nào thì:

- control pack đó available;
- data pack đó được server cho phép;
- chart/table optional field đó có thể bật.

User không có quyền:

- không nhận protected payload;
- UI có thể hiện locked state/CTA nếu product muốn.

Không được:

```text
send all data → CSS hide it
```

vì user có thể đọc bằng DevTools.

---

# 24. Technical entitlement architecture

Không tính scanner metrics per user.

Sai:

```text
User A → compute 800
User B → compute 800
User C → compute 800
```

Đúng:

```text
SSI
 ↓
CCC computes canonical 800-symbol state ONCE
 ↓
authorization/subscription layer
 ↓
user-specific visibility
```

---

# 25. Watchlist remains entitlement scope

Rules trong:

`CCC_WATCHLIST_RULES_v1.0.md`

tiếp tục có hiệu lực.

Concept:

```text
Free/Basic/Plus/Pro
Watchlist = active technical entitlement set
```

Full Market:

```text
technical scope not constrained by Watchlist
```

nhưng Watchlist vẫn hữu ích cho:

- favorites;
- alerts;
- priority.

V2 không được tự ý thay Watchlist quota.

---

# 26. Search outside Watchlist

User vẫn có thể search mã ngoài technical entitlement.

Ví dụ Free user search DGC:

Có thể xem:

- public quote;
- public fundamental data.

Protected technical section:

```text
locked
```

CTA conceptual:

```text
Thêm DGC vào Watchlist để theo dõi tín hiệu CCC
```

Nếu Watchlist full:

```text
Đổi mã hoặc nâng gói
```

Exact copy tuân Monetization UX docs.

---

# 27. Market-wide discovery for limited plans

Limited-plan user vẫn cần biết CCC thực sự scan toàn thị trường.

Có thể show aggregate:

```text
12 mã đang được xác nhận
28 mã có dòng tiền đáng chú ý
9 mã có áp lực bán tăng
```

Identity ngoài entitlement có thể:

- masked;
- locked;
- limited;

theo membership contract.

Không cần gửi protected technical details của tất cả symbols cho browser.

---

# 28. Alerts V2

Alert không còn dựa cứng vào:

```text
3/4
4/4
```

Alert dựa vào meaningful state transition.

Conceptual events:

```text
FLOW_APPEARING
FLOW_PRICE_CONFIRMED
MOMENTUM_WEAKENING
SELLING_PRESSURE
```

Không alert mỗi tick/minute.

Không spam:

```text
same state repeated
same symbol repeated
```

Alert phải respect:

- plan;
- Watchlist;
- alert entitlement;
- user settings.

---

# 29. Alert copy philosophy

Alert user-facing đơn giản.

Ví dụ:

```text
HPG — Dòng tiền & giá đã xác nhận
Giá hiện tại: 27.40
+1.8%
10:17
```

Không bắt buộc show:

- exact RVOL;
- exact threshold;
- Price5;
- Price15;
- scoring recipe.

---

# 30. Golden Board / Bảng vàng V2

Bảng vàng vẫn hữu ích nếu đổi vai trò.

Không nên chỉ là:

```text
top symbols with most old signals
```

Nên trở thành:

> **timestamped CCC signal journal + outcome history**

Suggested event record:

```text
symbol
signal_state
detected_at
price_at_signal
session
signal_level
later_outcome_fields
```

Outcome có thể cập nhật sau:

- max move after signal;
- closing move;
- later state;
- end-of-day context.

## Critical

Signal event phải được ghi ở thời điểm thật.

Không được chọn lại sau khi biết kết quả vì sẽ tạo survivorship/cherry-picking.

Bảng vàng có ba giá trị:

1. replay/learning cho user;
2. backtest/quality measurement cho CCC;
3. transparency/proof cho sản phẩm.

Bảng vàng hoàn chỉnh **không bắt buộc** cho first Monday V2 release.

Nhưng signal-event persistence nên được chuẩn bị sớm.

---

# 31. Baseline Engine V2

Không tiếp tục phụ thuộc vào baseline cũ như source of truth duy nhất nếu canonical source đã chuyển sang SSI.

Recommended rebuild:

```text
SSI historical intraday
        ↓
normalize market sessions
        ↓
canonical minute timeline
        ↓
Volume Baseline Engine V2
```

Baseline target có thể dựa trên latest valid prior sessions.

Exact N được cấu hình server-side.

User-facing có thể show data-coverage count nếu cần.

---

# 32. Historical intraday rebuild

Recommended bootstrap:

- lấy SSI 1-minute historical data;
- đủ số phiên để xây baseline đáng tin;
- normalize theo exchange/session;
- kiểm tra missing bars;
- phân biệt “không giao dịch” và “missing data”;
- build cumulative/rolling baseline;
- validate representative symbols.

Không mix provider một cách âm thầm trong cùng baseline active.

Old snapshot data có thể giữ để:

- QA;
- comparison;
- fallback investigation.

Không lấy old provider data và SSI data trộn không kiểm soát thành một baseline.

---

# 33. Intraday candle handling

Realtime service aggregate:

```text
tick → 1m candle
```

Sau đó có thể derive:

```text
5m
15m
30m
```

Không cần lưu mọi raw tick dài hạn.

Current session 1m candles nên được giữ in-memory / local state đủ để tính:

- Price5;
- Price15;
- breakout context;
- rolling volume;
- chart realtime.

---

# 34. Storage strategy

Do not use Supabase as an all-market tick archive.

Recommended conceptual retention:

```text
Raw tick:
transient / short recovery buffer

1m candle:
local VPS storage, rolling retention

5m/15m candle:
longer local retention

Daily OHLC:
long-term

Signal events:
long-term

Business/user data:
Supabase
```

Exact retention days không khóa trong spec này.

Nên đo dung lượng thực tế sau vài phiên trước khi cố định.

Parquet/compressed columnar storage phù hợp cho historical local candle archive.

---

# 35. Realtime feed health / Data Trust

CCC phải phân biệt:

```text
LIVE
DELAYED
DEGRADED
OFFLINE
```

Không coi một mã thanh khoản thấp “không có trade mới” là toàn feed bị chết.

Feed-health nên đánh giá từ nhiều dấu hiệu:

- connection heartbeat;
- last provider message;
- provider timestamp drift;
- market activity;
- sentinel/active instruments;
- reconnect state;
- gap-repair state.

UI Data Trust hiện có có thể được tận dụng.

---

# 36. Reconnect behavior

Khi SSI WebSocket disconnect:

```text
disconnect detected
       ↓
mark feed degraded
       ↓
reconnect
       ↓
detect time gap
       ↓
REST backfill missing interval
       ↓
idempotent repair
       ↓
continuity check
       ↓
resume LIVE
```

Không:

- giả vờ dữ liệu vẫn LIVE;
- silently skip missing window;
- phát signal dựa trên continuity bị hỏng.

---

# 37. Provider consistency

SSI là canonical source.

Nếu sau này KBS/VCI được dùng:

- validator;
- diagnostic;
- controlled fallback.

Không tự động trộn provider giữa phiên trong derived baseline/signal mà không có explicit normalization policy.

Đặc biệt volume-derived metrics rất nhạy với provider inconsistency.

---

# 38. Market Pulse — KEEP CURRENT STRUCTURE

Market Pulse **không nằm trong phạm vi redesign V2 đầu tiên**.

Giữ cấu trúc hiện tại nếu đang hoạt động ổn.

Không để việc nghiên cứu:

- S&P 500;
- Nikkei;
- Hang Seng;
- Gold;
- WTI;
- TradingView widgets;

làm chậm CCC V2 core release.

Nếu sau này thêm TradingView/global context, làm thành enhancement riêng.

V2 first release tập trung vào:

```text
Vietnam scanner intelligence
```

---

# 39. MA10 / MA200 role in V2

MA10/MA200 vẫn rất hữu ích và user đã quen.

Giữ hiển thị.

Nhưng engine philosophy thay đổi:

> MA10/MA200 là **technical context**, không bắt buộc là những “vote ngang nhau” với realtime flow/price event.

Một mã dưới MA200 vẫn có thể có realtime event đáng chú ý.

CCC không được bỏ qua một event chỉ vì một long-term MA context không thuận lợi, trừ khi proprietary engine chủ động dùng nó như một phần weighting/filter.

User vẫn được nhìn MA10/MA200 để tự đánh giá.

---

# 40. Fundamental role

Fundamental Research vẫn là layer riêng.

Không trộn score fundamental thành realtime signal chỉ để tạo một con số tổng hợp.

User có thể:

```text
CCC finds realtime opportunity
       ↓
user checks chart
       ↓
user checks fundamentals if desired
       ↓
user decides
```

---

# 41. User experience target

Trong tối đa vài giây, user phải trả lời được:

1. mã nào đáng chú ý?
2. CCC đang nhìn thấy trạng thái gì?
3. giá/volume/MA cơ bản đang ở đâu?
4. tín hiệu xảy ra lúc nào?
5. tôi có muốn mở chart để đánh giá bằng phương pháp riêng không?

Nếu UI bắt user học Price5/RVOL15 trước khi hiểu ý nghĩa, UX đã thất bại.

---

# 42. Mobile behavior

Mobile giữ ưu tiên thông tin:

```text
Ticker
Price / % change
CCC heat bar
Vietnamese status
Signal/update time
```

Các field phụ có thể:

- secondary line;
- expandable;
- detail view.

Không cố nhét toàn bộ desktop technical metrics vào một row mobile.

---

# 43. Desktop behavior

Desktop có nhiều không gian hơn nhưng vẫn phải giữ density.

Không quay lại lỗi:

```text
left light
middle empty
right heavy
```

Không thêm cột chỉ vì backend có metric mới.

Metric mới phải chứng minh giá trị UX trước khi trở thành default column.

---

# 44. Optional column customization

Future enhancement:

```text
Tùy chỉnh cột
```

User có entitlement phù hợp có thể bật thêm metric.

Default scanner vẫn đơn giản.

Technical pack không được phá default layout.

---

# 45. Server API / realtime payload principle

Frontend payload phải chứa đủ để render, không chứa recipe.

Conceptual public/protected payload:

```json
{
  "symbol": "HPG",
  "price": 27400,
  "change_pct": 1.8,
  "volume": 18200000,
  "ma10": 26900,
  "ma200": 28100,
  "signal_state": "FLOW_PRICE_CONFIRMED",
  "signal_level": 4,
  "signal_summary_vi": "Dòng tiền & giá đã xác nhận",
  "signal_at": "2026-09-14T10:17:00+07:00",
  "data_status": "LIVE"
}
```

Đây là ví dụ interface, không phải field list bắt buộc cuối cùng.

Payload không gửi:

```text
thresholds
weights
internal scoring formula
private reason tree
```

---

# 46. Internal signal record

Server internal object có thể phong phú hơn:

```text
symbol
session
current_state
previous_state
state_entered_at
trigger_anchor
volume_features
price_features
trend_context
liquidity_context
baseline_coverage
internal_score
internal_reason_codes
config_version
engine_version
```

Không serialize object này nguyên xi ra browser.

---

# 47. Version every signal event

Mỗi persisted signal event nên biết:

```text
engine_version
config_version
```

Lý do:

Sau này threshold/weight thay đổi, CCC vẫn biết tín hiệu lịch sử được sinh ra bởi engine nào.

Điều này rất quan trọng cho:

- backtest;
- audit;
- quality comparison;
- Golden Board;
- debugging.

---

# 48. Config, not hard-code

Các threshold/tunable values phải đặt trong server configuration.

Ví dụ conceptual keys:

```text
FLOW_TRIGGER_THRESHOLD
PRICE_CONFIRM_FAST_THRESHOLD
PRICE_CONFIRM_SLOW_THRESHOLD
BREAKOUT_CONFIRM_MODE
SELL_PRESSURE_THRESHOLD
LIQUIDITY_MIN_GATE
STATE_HYSTERESIS_WINDOW
BASELINE_TARGET_SESSIONS
```

Tên có thể thay đổi khi implementation.

Không khóa numerical value trong public spec.

---

# 49. Backtest philosophy

Không chọn threshold chỉ vì “nghe hợp lý”.

Sau khi V2 chạy:

- capture signal events;
- đo outcome sau +5m;
- +10m;
- +15m;
- end of session;
- phân nhóm liquidity;
- phân nhóm time-of-day;
- phân nhóm exchange.

Sau đó tuning config.

Architecture không cần đổi chỉ vì threshold thay đổi.

---

# 50. First-release threshold policy

Để kịp Monday:

- chọn conservative initial configuration;
- giữ tất cả threshold server-configurable;
- không tối ưu quá mức trước khi có live sample;
- ưu tiên false-positive control;
- không hard-code deep assumptions vào UI.

First Monday là:

> **V2 live validation session**

không phải kết thúc quá trình tuning.

---

# 51. Release target — Monday 2026-09-14

## MUST HAVE

First V2 session phải ưu tiên:

- SSI realtime connected;
- Market Session Engine;
- correct exchange/session handling;
- Volume Engine core;
- Price Engine core;
- CCC Signal State output;
- Vietnamese status;
- scanner realtime update;
- familiar basic indicators;
- heat-bar behavior;
- Stock Detail basic realtime chart;
- CCC signal timestamp/marker;
- Watchlist/plan compatibility;
- feed-health visibility;
- rollback path.

## SHOULD HAVE

Nếu không làm chậm release:

- signal-event persistence;
- basic Golden Board event schema;
- reconnect gap repair;
- chart historical bootstrap;
- server-side pack entitlement skeleton.

## CAN WAIT

Không để các việc sau block Monday:

- full Golden Board UI;
- Telegram redesign;
- email redesign;
- many indicator packs;
- global Market Pulse redesign;
- TradingView integration;
- long-term multi-year intraday chart;
- perfect threshold backtest;
- extensive animation/polish;
- large UI refactor.

---

# 52. Suggested implementation order

## Phase V2.0-A — Documentation + Contracts

- lock this spec;
- map current V1 fields to V2;
- define server payload;
- define state enum;
- define session enum;
- define config boundary.

## Phase V2.0-B — SSI Bootstrap

- confirm credentials/runtime;
- historical 1m pull;
- normalize symbols/exchange;
- checkpoint downloader;
- build clean historical dataset.

## Phase V2.0-C — Session Engine

- HOSE sessions;
- HNX sessions;
- UPCoM sessions;
- lunch reset;
- auction handling;
- unit tests using fixed timestamps.

## Phase V2.0-D — Volume Baseline V2

- cumulative baseline;
- rolling-window baseline;
- coverage tracking;
- missing-data normalization;
- representative-symbol QA.

## Phase V2.0-E — Realtime Engine

- SSI WebSocket;
- in-memory symbol state;
- 1m candle aggregation;
- heartbeat;
- reconnect;
- gap detection.

## Phase V2.0-F — Price + Volume Features

- current-session feature calculation;
- no lunch stitching;
- auction-safe behavior;
- internal metrics.

## Phase V2.0-G — Signal Engine

- state machine;
- hysteresis;
- signal_level;
- Vietnamese summary;
- event transition output;
- config versioning.

## Phase V2.0-H — CCC Realtime Gateway

- authenticated WebSocket/SSE;
- subscriptions;
- Watchlist authorization;
- scanner delta;
- symbol detail;
- market/status channel.

## Phase V2.0-I — Minimal UI integration

- preserve layout;
- replace old signal-count meaning;
- heat bar;
- Vietnamese status;
- realtime patching;
- chart marker;
- responsive QA.

## Phase V2.0-J — Production rehearsal

- simulated session tests;
- reconnect;
- stale feed;
- user plan tests;
- mobile;
- desktop;
- rollback.

---

# 53. Acceptance tests — ENGINE

Minimum engine QA:

### Session

- HOSE ATO is not treated as ordinary 15-minute continuous window.
- HOSE first continuous Price/RVOL window requires enough valid minutes.
- HNX/UPCoM opening calculations start from valid continuous session.
- 13:00 resets rolling momentum.
- day cumulative volume does not reset at lunch.
- HOSE/HNX auction behavior does not contaminate continuous rolling metrics.

### Data

- missing provider bar is not automatically assumed zero trade;
- duplicate event is idempotent;
- reconnect gap can be repaired;
- out-of-order data does not corrupt current candle;
- historical coverage is tracked.

### Signal

- state cannot oscillate every update because of tiny boundary changes;
- selling-pressure branch exists;
- same state does not generate repeated event spam;
- signal event records actual detection time;
- engine/config version are retained.

---

# 54. Acceptance tests — REALTIME UI

### Stock Detail

Open HPG.

When HPG changes:

- price updates without page refresh;
- chart updates;
- signal state updates if changed;
- scroll position preserved;
- filters/tab preserved.

When unrelated symbol changes:

- no unnecessary Stock Detail rerender;
- no full-page refresh.

Switch HPG → SSI:

- HPG detail subscription ends;
- SSI detail subscription starts;
- no WebSocket connection leak.

---

# 55. Acceptance tests — USER ENTITLEMENT

For each plan:

- public quote accessible according to current product rule;
- fundamentals accessible according to current product rule;
- protected technical intelligence only for authorized scope;
- Watchlist changes follow v1.0 rules;
- frontend does not receive hidden advanced payload;
- direct socket/API request cannot bypass plan;
- Full Market behavior remains distinct from Watchlist alert selection.

---

# 56. Acceptance tests — UI preservation

Before release compare V1 vs V2:

- routes unchanged unless explicitly approved;
- header behavior unchanged;
- Market Pulse not redesigned;
- scanner remains dense;
- mobile remains familiar;
- table column explosion does not occur;
- user can identify price/volume/MA as before;
- new CCC status is visually prominent;
- heat bar feels like evolution of current signal bar.

---

# 57. Data Trust acceptance

During healthy session:

```text
LIVE
```

During disconnect:

```text
DEGRADED / OFFLINE
```

During repair:

```text
DEGRADED
```

After continuity restored:

```text
LIVE
```

No signal generation from knowingly broken continuity unless explicitly supported by safe fallback policy.

---

# 58. DO NOT DO — LOCKED

Do not:

1. redesign the whole website for V2;
2. replace navigation without Product Owner approval;
3. change Market Pulse just because new feeds are available;
4. add every internal metric as scanner column;
5. show proprietary threshold/weight publicly;
6. calculate protected signal in browser;
7. ship secret config in frontend JavaScript;
8. broadcast full protected 800-symbol payload to every user;
9. compute scanner separately for every user;
10. poll Supabase as primary realtime mechanism;
11. write every market tick to Supabase;
12. stitch rolling momentum through lunch break;
13. treat HOSE ATO as ordinary continuous trading;
14. silently mix provider data in active baseline;
15. treat no trade on illiquid symbol as feed outage;
16. treat high volume as bullish by definition;
17. alert repeatedly without state transition;
18. expose all advanced indicator packs to unauthorized user;
19. remove Watchlist rules because engine changed;
20. let Monday deadline be blocked by optional polish.

---

# 59. Product copy standard

Preferred canonical Vietnamese states:

```text
Dòng tiền đang xuất hiện
Dòng tiền & giá đã xác nhận
Xu hướng đang được duy trì
Động lượng đang suy yếu
Áp lực bán đang tăng
```

Copy có thể được UX-polish sau nhưng semantic meaning không được thay đổi tùy tiện.

Không dùng wording khẳng định:

```text
Nên mua
Chắc chắn tăng
Điểm mua
Mua ngay
```

trừ khi sản phẩm tương lai có decision riêng về investment-advice positioning.

---

# 60. User mental model

CCC V2 phải tạo mental model:

```text
CCC continuously scans the market
        ↓
CCC notices something meaningful
        ↓
CCC tells me the current state in Vietnamese
        ↓
I inspect objective data
        ↓
I open the chart
        ↓
I apply my own method
        ↓
I decide
```

Đây là UX/product model chuẩn của V2.

---

# 61. Future: indicator packs

Sau core V2 có thể phát triển:

```text
CCC Flow Pack
CCC Momentum Pack
CCC Breakout Pack
```

hoặc tên thương mại khác.

Pack có thể được:

- included by plan;
- admin-granted;
- sold separately;
- used for beta cohort.

UI shell không cần thay.

Backend entitlement mở pack tương ứng.

---

# 62. Future: advanced chart

Sau first release có thể bổ sung:

- 1m / 5m / 15m selectable;
- richer signal event replay;
- signal lifecycle markers;
- historical event navigation;
- indicator pack overlays;
- saved chart preferences.

Không biến first V2 release thành TradingView clone.

---

# 63. Future: Golden Board analytics

Potential outcomes:

```text
price +5m
price +10m
price +15m
max favorable move
max adverse move
close change
next-session behavior
```

Dữ liệu này giúp CCC tự cải thiện engine.

Không cần show tất cả cho user.

---

# 64. Future: signal quality research

Có thể nghiên cứu:

- thresholds theo liquidity bucket;
- thresholds theo time-of-day;
- opening behavior;
- exchange-specific behavior;
- trend-context weighting;
- market-regime adjustment;
- state-duration quality;
- false breakout behavior.

Những nghiên cứu này không yêu cầu redesign UI.

---

# 65. Working model for Product Owner + AI/Codex

Để giảm cognitive load:

Product Owner chủ yếu quyết định:

1. sản phẩm có đúng ý không?
2. chi phí có chấp nhận được không?
3. có triển khai bước tiếp theo không?

AI/technical workflow chịu trách nhiệm:

- research;
- architecture;
- specification;
- implementation task;
- review;
- QA;
- regression analysis.

Codex/dev không được tự reinterpret product rule nếu spec đã rõ.

Prompt principle:

> Implement according to `docs/product/CCC_V2_PRODUCT_ENGINE_SPEC_v2.0.md`.  
> Preserve existing CCC UI/UX unless this spec explicitly requires a change.  
> Do not expose proprietary signal thresholds or scoring logic to the browser.

---

# 66. Definition of CCC V2 first successful release

CCC V2 first release được coi là thành công khi:

```text
1. SSI realtime is stable enough for live session.
2. Market sessions are interpreted correctly.
3. Volume/price features update continuously.
4. CCC produces semantic states.
5. Browser updates without refresh.
6. User still recognizes the existing CCC interface.
7. Basic objective metrics remain visible.
8. Vietnamese CCC conclusion is prominent.
9. Stock chart helps user independently evaluate the signal.
10. Watchlist/plan entitlement remains enforced.
11. Feed problems are visible instead of silently corrupting signals.
12. Proprietary engine details are not exposed to unauthorized clients.
```

---

# 67. Final V2 principle — LOCKED

> **CCC V2 không phải website mới.**
>
> **CCC V2 là CCC hiện tại với một realtime intelligence engine tốt hơn.**

User vẫn nhìn thấy sản phẩm quen thuộc:

```text
Giá
% thay đổi
Khối lượng
MA10
MA200
các dữ liệu cơ bản quen thuộc
```

nhưng bây giờ CCC bổ sung một kết luận dễ hiểu:

```text
Dòng tiền đang xuất hiện
Dòng tiền & giá đã xác nhận
Xu hướng đang được duy trì
Động lượng đang suy yếu
Áp lực bán đang tăng
```

Phía sau kết luận đó có thể là engine ngày càng tinh vi.

Phía trước user vẫn có một trải nghiệm:

```text
nhanh
gọn
quen thuộc
dễ hiểu
có đủ dữ liệu để tự quyết định
```

Đây là nền tảng của **Chuyện Chợ Chứng Version 2**.

---

# Appendix A — V1 → V2 semantic migration

| V1 concept | V2 direction |
|---|---|
| 4 independent signals | semantic realtime state |
| `0/4 ... 4/4` | heat/intensity + Vietnamese conclusion |
| price vs previous close as primary signal | daily change stays context; short-horizon price engine adds confirmation |
| volume condition as isolated check | Volume Engine models flow over market-time windows |
| MA200 as equal signal vote | MA10/MA200 become visible technical context; engine may still use context internally |
| table polling mindset | WebSocket delta |
| Supabase-centered realtime | VPS realtime state + Supabase persistence |
| static signal result | signal lifecycle |
| signal table only | signal + chart timestamp/replay |
| same technical payload concept | server-side user entitlement |

---

# Appendix B — Public vs proprietary boundary

## Safe to document publicly

- architecture;
- state names;
- input categories;
- session semantics;
- payload schema;
- entitlement rules;
- storage responsibilities;
- UI behavior;
- chart behavior;
- reliability behavior.

## Do not document publicly

- production threshold values;
- weights;
- feature coefficients;
- exact score formula;
- exact state transition recipe;
- secret heuristics;
- proprietary liquidity gates;
- anti-noise tuning values;
- private provider credentials;
- internal tokens/secrets.

---

# Appendix C — Recommended source changes after this document is accepted

Do not rewrite all legacy docs immediately.

Recommended sequence:

```text
1. Add:
   docs/product/CCC_V2_PRODUCT_ENGINE_SPEC_v2.0.md

2. Keep:
   docs/product/CCC_WATCHLIST_RULES_v1.0.md
   docs/product/CCC_MEMBERSHIP_PERMISSION_MODEL_v1.0.md

3. Keep CCC_UIUX_MASTER.md as visual/layout authority,
   but mark its V1 "Current signal truth" section as superseded by V2
   when implementation begins.

4. Later, after V2 production stabilizes:
   update CCC_UIUX_MASTER to a formal V2-compatible revision.
```

Reason:

> Avoid mixing an engine migration with a large documentation/UI rewrite before first live validation.

---

# Appendix D — Monday priority mantra

If a task does not help one of these, it is not Monday-critical:

```text
DATA CORRECT
SESSION CORRECT
SIGNAL CORRECT
REALTIME STABLE
ENTITLEMENT SAFE
UI FAMILIAR
ROLLBACK READY
```

Everything else can follow after the first stable V2 sessions.
