# CCC SSI V3 - Canonical Market Data & Signal Contract

**Dự án:** Chuyện Chợ Chứng (CCC)  
**Ngày chốt:** 24/09/2026  
**Trạng thái:** APPROVED FOR DATABASE DESIGN - ĐÃ CHỐT ĐỂ THIẾT KẾ DATABASE  
**Vai trò:** Source of Truth - Nguồn quy chuẩn cho phần market-data, calculation, baseline, auction, signal, EOD và chart  
**Thay thế:** `CCC_Supabase_Current_Data_Audit_Before_SSI_Rebuild_20260924.md` ở vai trò tài liệu định hướng triển khai mới. Tài liệu audit cũ vẫn có thể giữ làm hồ sơ hiện trạng trước rebuild.

> Tài liệu này phân biệt rõ **HỆ CŨ (Legacy System - Hệ thống cũ)** và **HỆ MỚI (SSI V3 System - Hệ thống SSI V3)**.  
> Từ thời điểm chốt, mọi migration/schema/code mới phải tuân theo tài liệu này, trừ khi Product Owner chốt thay đổi bằng văn bản sau đó.

---

# 0. Executive Summary - Tóm tắt quyết định

## 0.1 Mục tiêu rebuild

Chuyển phần market-data của CCC sang **SSI-only (chỉ dùng SSI)** để đạt các mục tiêu:

1. Chart realtime có các nút thời gian 5m, 15m, 30m, 1h, 1D.
2. Dữ liệu intraday chuyển từ snapshot 5 phút sang dữ liệu gốc 1 phút.
3. `Day RVOL (Khối lượng tương đối trong ngày)` chạy từng phút và so cumulative volume cùng thời điểm với baseline lịch sử.
4. Giữ `RVOL30`, thêm `RVOL15`, cả hai chạy rolling từng phút.
5. Tách ATO/ATC thành auction metrics riêng, không coi là rolling window thông thường.
6. Giữ `Price5` và `Price15` để đo momentum giá ngắn hạn.
7. Bỏ bộ 4 signal V1; dùng configurable state-based signal engine.
8. Giữ MA10 và MA200.
9. Baseline ưu tiên 10 phiên, chấp nhận 9/10 và 8/10; dùng quy tắc `break blocks (cụm gián đoạn dữ liệu)`.
10. EOD dùng SSI REST làm lịch sử chuẩn; không ép tổng volume daily bằng tổng volume minute.
11. Ngày điều chỉnh giá tham chiếu vẫn lưu dữ liệu/chart nhưng pause signal trong ngày; chỉ reset volume baseline khi có structural adjustment được chứng minh.
12. Supabase mới chỉ là PostgreSQL tạm để xây và audit; sau khoảng 5 phiên ổn định liên tục sẽ bắt đầu chuyển sang PostgreSQL trên VPS.

---

# 1. Canonical Principles - Nguyên tắc bất biến

## 1.1 SSI là nguồn market-data duy nhất

```text
SSI ONLY
```

- Không trộn KBS, VCI hoặc market-data Supabase cũ vào SSI V3.
- Không fallback sang provider cũ khi SSI thiếu dữ liệu.
- SSI thiếu gì thì ghi nhận thiếu đúng như vậy.
- `Missing != Zero (Thiếu dữ liệu không đồng nghĩa bằng 0)`.
- Không nội suy giá/volume để che lỗ dữ liệu.

## 1.2 Raw data is immutable - Dữ liệu SSI gốc không bị sửa

Raw OHLCV lấy từ SSI phải được giữ nguyên.

Không được:

- sửa minute volume để ép khớp daily volume;
- sửa giá để làm đẹp chart;
- chèn dữ liệu provider khác;
- biến missing thành zero;
- viết lại lịch sử raw chỉ vì calculation rule thay đổi.

## 1.3 Calculated data is reproducible - Dữ liệu tính toán phải tái tạo được

Mọi metric/tín hiệu cần biết:

- nguồn market-data;
- baseline sessions used;
- config version;
- engine version;
- quality/trust status;
- reason codes khi không đủ điều kiện.

## 1.4 Browser không truy cập trực tiếp NEW market database

Luồng public vẫn là:

```text
Frontend
   -> CCC API / WebSocket
      -> Market Database
```

Supabase mới không trở thành nguồn đọc trực tiếp của browser.

## 1.5 Supabase cũ vẫn giữ user-system

Các khối sau tiếp tục thuộc Supabase cũ:

- Auth (Xác thực)
- Profiles (Hồ sơ)
- Plans / Subscriptions (Gói / Đăng ký)
- VIP / Temporary Access Passes (Quyền tạm thời)
- User Watchlist (Danh sách theo dõi)
- Stock Metadata (Thông tin mã/doanh nghiệp)
- Financial / BCTC (Dữ liệu tài chính)

---

# PART A - LEGACY SYSTEM / HỆ CŨ

# 2. Hệ cũ đang có gì

Snapshot audit ngày 23/09/2026 ghi nhận schema `public` có 20 bảng + 1 view.

## 2.1 Nhóm Market Data cũ

| Table - Bảng | Vai trò cũ | Vấn đề chính |
|---|---|---|
| `intraday_snapshots` (Ảnh chụp trong phiên) | Price + cumulative volume theo slot 5 phút | Chỉ 5 phút, không đủ làm canonical 1m |
| `daily_history` (Lịch sử ngày) | Close + Volume | Không có Open/High/Low |
| `daily_baseline` (Baseline ngày) | Previous close, MA10, MA200, AVG volume | Một số khái niệm volume bị dùng lẫn nghĩa |
| `intraday_volume_baseline_10` (Baseline cumulative cùng thời điểm) | Avg cumulative volume theo 5 phút | Ý tưởng tốt nhưng resolution cũ 5m |
| `rvol30_baseline` (Baseline RVOL30) | Avg rolling volume 30m | Refresh/cấu trúc cũ, chưa có RVOL15 |
| `stock_snapshot` (Trạng thái mã hiện tại) | Kết quả scanner V1 | Chứa hard-coded 4 signals |
| `latest_daily_baseline` (View baseline mới nhất) | Gộp baseline | `avg_volume_10` đổi nghĩa theo thời điểm |

## 2.2 Nhóm Signal / History cũ

| Table - Bảng | Vai trò cũ | Hướng mới |
|---|---|---|
| `golden_board_daily` (Bảng vàng) | Ghi mã đạt 4/4 signal | Thay bằng Signal Events + Market Movers |
| `scan_runs` (Nhật ký quét) | Log scanner | Giữ concept, thiết kế lại Ops Log |
| `daily_history_sync_state` (Trạng thái đồng bộ) | Theo dõi backfill | Giữ concept checkpoint/resume |

## 2.3 Nhóm Metadata / Fundamental cần giữ

- `stock_metadata`
- `financial_latest`
- `financial_quarterly`
- `market_pulse_current` cần audit dependency riêng, không xem là market-data scanner core.

## 2.4 Nhóm User / Entitlement cần giữ

- `plans`
- `profiles`
- `subscriptions`
- `temporary_access_passes`
- `user_watchlist`
- `watchlist_change_log`

## 2.5 `stocks` legacy

`stocks` chỉ có 257 mã trong khi `stock_metadata` có 800 mã ở thời điểm audit. Đây là legacy candidate, không được bê sang market-data SSI mới như source of truth.

---

# 3. Hệ cũ lưu dữ liệu intraday như thế nào

`intraday_snapshots` lưu:

```text
1 symbol (mã)
× 1 slot 5-minute (mốc 5 phút)
× 1 trading day (ngày giao dịch)
```

Các field cũ chính:

| Field - Trường | Vietnamese - Tiếng Việt |
|---|---|
| `trading_date` | Ngày giao dịch |
| `time_slot` | Mốc 5 phút |
| `symbol` | Mã cổ phiếu |
| `exchange` | Sàn |
| `current_price` | Giá hiện tại |
| `volume_accumulated` | Khối lượng tích lũy |
| `updated_at` | Thời điểm cập nhật |
| `data_status` | Trạng thái dữ liệu |

Điểm tốt cần giữ: dữ liệu được append theo thời điểm, tức hệ thống có lịch sử intraday chứ không chỉ một row current-state.

Điểm phải bỏ: resolution 5 phút không còn là canonical storage của hệ mới.

---

# 4. Daily history cũ và giới hạn

`daily_history` chỉ lưu:

```text
Close (Giá đóng cửa)
Volume (Khối lượng ngày)
```

Không có:

```text
Open (Giá mở cửa)
High (Giá cao nhất)
Low (Giá thấp nhất)
```

Do đó daily history cũ không đủ làm chart nến OHLCV chuẩn.

---

# 5. Baseline và RVOL cũ

## 5.1 MA10 / MA200 cũ

```text
MA10  = average Close của tối đa 10 phiên gần nhất
MA200 = average Close của tối đa 200 phiên gần nhất
```

Logic này được giữ về mặt ý nghĩa, nhưng nguồn history chuyển sang SSI DailyOhlc.

## 5.2 Daily Volume % cũ bị đặt tên gây nhầm

Trong phiên, hệ cũ thực chất gần với:

```text
current cumulative volume
/
average cumulative volume at same time
```

nhưng field lại mang tên `daily_volume_pct`, dễ bị hiểu nhầm thành current volume / average full-day volume.

Hệ mới bỏ sự nhập nhằng này và dùng tên `day_rvol` rõ nghĩa.

## 5.3 RVOL30 cũ

Ý tưởng:

```text
RVOL30
=
Volume của rolling 30-minute window hiện tại
/
Average volume của đúng rolling 30-minute window lịch sử
```

Hệ mới giữ ý tưởng này, đổi resolution về 1 phút, bổ sung RVOL15 và phase-awareness theo SSI.

---

# 6. Bộ signal V1 cũ - RETIRED / NGỪNG DÙNG

Bộ V1 hard-code:

```text
Price Change >= +3%
Daily Volume >= 200%
Price > MA200
RVOL30 >= 200%
```

`signal_count` đếm 0/4 đến 4/4.

Quy tắc 4/4 này **không còn là signal contract của SSI V3**.

Những ý tưởng history từ `golden_board_daily` vẫn đáng giữ:

- first hit (lần đầu đạt);
- last hit (lần cuối đạt);
- hit count (số lần đạt);
- latest observed state (trạng thái quan sát mới nhất);
- max RVOL (RVOL cao nhất);
- signal version (phiên bản tín hiệu).

---

# PART B - SSI V3 SYSTEM / HỆ MỚI

# 7. Source Ownership - Quyền sở hữu nguồn dữ liệu

## 7.1 Sơ đồ tổng thể song ngữ

```text
                         SSI MARKET DATA
                    DỮ LIỆU THỊ TRƯỜNG SSI
                              |
            +-----------------+-----------------+
            |                 |                 |
            v                 v                 v
     SSI FastConnect     IntradayOhlc       DailyOhlc
     Realtime Stream     REST 1-minute      REST Daily
     Luồng realtime      Lịch sử 1 phút     Dữ liệu ngày
            |                 |                 |
            v                 v                 v
      LIVE / HOT DATA    MINUTE HISTORY      DAILY HISTORY
      Dữ liệu đang chạy  Lịch sử từng phút   Lịch sử ngày
            |                 |                 |
            +------------+----+----------+------+
                         |               |
                         v               v
                CANONICAL MARKET DATA   CHART DATA
                Dữ liệu thị trường      Dữ liệu biểu đồ
                chuẩn của CCC
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
   VOLUME METRICS   PRICE METRICS    MA METRICS
   Chỉ số KL        Chỉ số giá       Chỉ số MA
   Day RVOL         Price5           MA10
   RVOL15           Price15          MA200
   RVOL30
          +--------------+---------------+
                         |
                         v
                 AUCTION METRICS
                 Chỉ số ATO / ATC
                         |
                         v
                STOCK CURRENT STATE
                Trạng thái mã hiện tại
                         |
                         v
             CONFIGURABLE SIGNAL ENGINE
             Bộ máy tín hiệu cấu hình được
                         |
         +---------------+----------------+
         |               |                |
         v               v                v
 CURRENT SIGNAL     SIGNAL EVENTS     MARKET MOVERS
 Tín hiệu hiện tại Lịch sử tín hiệu  Bảng mã nổi bật
```

## 7.2 SSI FastConnect - Luồng realtime SSI

FastConnect là authority cho:

- current quote (giá hiện tại);
- cumulative live volume (khối lượng tích lũy realtime);
- live chart state (trạng thái chart đang chạy);
- Price5 / Price15 realtime;
- intraday current metrics;
- SSI provider session;
- ATO/ATC evidence.

FastConnect **không** là canonical historical source sau EOD cho ordinary minute bars.

## 7.3 SSI IntradayOhlc - Lịch sử 1 phút SSI

IntradayOhlc REST là authority cho:

- canonical minute OHLCV;
- historical 1m chart;
- Day RVOL historical denominator;
- RVOL15 denominator;
- RVOL30 denominator;
- replay / backtest của metric intraday.

## 7.4 SSI DailyOhlc - Dữ liệu ngày SSI

DailyOhlc REST là authority cho:

- canonical Daily OHLCV;
- chart 1D;
- MA10 / MA200 source;
- official daily volume của CCC;
- official daily Open/High/Low/Close.

---

# 8. Chart Contract - Quy chuẩn biểu đồ

## 8.1 Nút timeframe trên chart

Các nút người dùng:

```text
5m  - 5 phút
15m - 15 phút
30m - 30 phút
1h  - 1 giờ
1D  - 1 ngày
```

Đây là **display resolution (độ phân giải hiển thị)**, không phải 5 bộ canonical storage độc lập.

## 8.2 Canonical storage cho chart

Hệ thống lưu chuẩn:

```text
1-minute OHLCV (OHLCV 1 phút)
Daily OHLCV (OHLCV ngày)
```

Aggregation:

```text
1m -> 5m
1m -> 15m
1m -> 30m
1m -> 1h
DailyOhlc -> 1D
```

## 8.3 Historical target - Mục tiêu lịch sử

Mục tiêu nếu SSI cho phép lấy đủ:

```text
1-minute OHLCV từ 01/01/2025 đến hiện tại
Daily OHLCV từ 01/01/2025 đến hiện tại
```

Nếu SSI thiếu row/minute lịch sử thì lưu missing/gap, không dùng legacy provider để vá.

---

# 9. Minute Data Contract - Quy chuẩn dữ liệu 1 phút

Logical identity:

```text
symbol + trading_date + minute
```

Nhóm field tối thiểu:

| English field | Tiếng Việt | Vai trò |
|---|---|---|
| `symbol` | Mã cổ phiếu | Identity |
| `exchange` | Sàn giao dịch | Identity/context |
| `trading_date` | Ngày giao dịch | Identity |
| `minute` | Phút giao dịch | Identity |
| `open` | Giá mở của phút | SSI OHLC |
| `high` | Giá cao nhất phút | SSI OHLC |
| `low` | Giá thấp nhất phút | SSI OHLC |
| `close` | Giá đóng của phút | SSI OHLC |
| `volume` | Khối lượng phút | SSI volume |
| `source` | Nguồn dữ liệu | Provenance |
| `source_endpoint` | Endpoint nguồn | Provenance |
| `provider_time` | Thời gian từ provider | Audit |
| `quality_status` | Trạng thái chất lượng | Quality |
| `is_final` | Đã chốt lịch sử hay chưa | Lifecycle |
| `updated_at` | Thời điểm cập nhật | Ops |

Không tạo fake bar cho phút SSI không cung cấp.

---

# 10. Market Session & Exchange Rules - Phiên giao dịch và quy tắc theo sàn

## 10.1 Session semantics phụ thuộc SSI

CCC không xem giờ hard-code là nguồn sự thật cho trạng thái thị trường.

Ưu tiên:

```text
SSI session/data state
    -> CCC observes
       -> CCC acts
```

Clock chỉ phục vụ:

- timeout (quá hạn);
- health monitoring (giám sát sức khỏe);
- retry/backoff (thử lại/giãn tải);
- safety watchdog (bảo vệ vận hành).

## 10.2 Exchange-aware - Nhận biết từng sàn

Window hợp lệ của các metric phụ thuộc:

- exchange (HOSE/HNX/UPCOM);
- provider session;
- ATO/continuous/lunch/ATC/post-trading;
- dữ liệu SSI thực sự available.

Không cross lunch cho:

- RVOL15;
- RVOL30;
- Price5;
- Price15.

ATO/ATC không được xem là ordinary rolling window.

---

# 11. Day RVOL - Khối lượng tương đối trong ngày

## 11.1 Định nghĩa

`Day RVOL` chạy từng phút.

Tại phút `T`:

```text
Day RVOL(T)
=
Cumulative volume hôm nay từ đầu phiên -> T
/
Average cumulative volume từ đầu phiên -> cùng T
của các baseline sessions hợp lệ
```

Ví dụ:

```text
Hôm nay tới 10:15      = 1,800,000
Baseline cùng 10:15    = 1,200,000
Day RVOL               = 1.50x = 150%
```

## 11.2 Tần suất cập nhật

```text
09:31 -> Day RVOL
09:32 -> Day RVOL
09:33 -> Day RVOL
...
```

Day RVOL là time-series 1 phút, không phải metric chỉ refresh theo block 5 phút.

## 11.3 Không dùng full-day average làm denominator trong phiên

Không dùng:

```text
current cumulative volume
/
average full-day volume
```

cho định nghĩa Day RVOL realtime.

---

# 12. RVOL15 - Khối lượng tương đối 15 phút

## 12.1 Định nghĩa

Tại phút `T`:

```text
RVOL15(T)
=
Volume rolling 15-minute window hiện tại
/
Average volume của đúng 15-minute window đó
trong baseline sessions hợp lệ
```

Ví dụ lúc 10:00:

```text
09:45 -> 10:00 hôm nay
/
Average 09:45 -> 10:00 của baseline sessions
```

## 12.2 Tần suất

RVOL15 nhích từng phút:

```text
10:00
10:01
10:02
...
```

## 12.3 Vai trò

RVOL15 ưu tiên phát hiện sớm dòng tiền/áp lực giao dịch mới xuất hiện.

---

# 13. RVOL30 - Khối lượng tương đối 30 phút

Định nghĩa tương tự RVOL15 nhưng rolling window 30 phút:

```text
RVOL30(T)
=
Volume rolling 30-minute window hiện tại
/
Average volume của đúng 30-minute window đó
trong baseline sessions hợp lệ
```

RVOL30 nhích từng phút và thường đóng vai trò xác nhận/duy trì mạnh hơn RVOL15.

---

# 14. Price5 / Price15 - Biến động giá 5/15 phút

## 14.1 Price5

```text
price5_pct
=
(current_price / price_5_minutes_ago - 1) * 100
```

## 14.2 Price15

```text
price15_pct
=
(current_price / price_15_minutes_ago - 1) * 100
```

## 14.3 Quy tắc

- chạy theo minute;
- không cross lunch;
- không kéo xuyên auction boundary một cách giả tạo;
- nếu chưa đủ window thì metric = NULL;
- không dùng giá phút cũ để fill window bị thiếu một cách âm thầm.

Vai trò chính: phân biệt volume tăng kèm giá tăng, volume tăng kèm giá giảm, và high-volume price absorption (hấp thụ khối lượng lớn nhưng giá chưa chạy).

---

# 15. MA10 / MA200 - Trung bình động 10/200 phiên

## 15.1 Giữ nguyên ý nghĩa

```text
MA10  = average Close của 10 phiên hoàn tất hợp lệ
MA200 = average Close của 200 phiên hoàn tất hợp lệ
```

Nguồn mới: SSI DailyOhlc.

## 15.2 Current-day price không tự động chèn vào MA

MA dùng completed daily history; current price được dùng để tính distance:

```text
ma10_distance_pct
=
(current_price / ma10 - 1) * 100

ma200_distance_pct
=
(current_price / ma200 - 1) * 100
```

## 15.3 Reference adjustment

Raw SSI price không sửa. Khi có reference-price adjustment lớn làm đứt mặt bằng giá, lớp technical adjusted price được dùng nội bộ cho MA/technical comparison theo quy tắc ở phần 23.

---

# 16. ATO - Opening Auction / Phiên khớp lệnh định kỳ mở cửa

ATO là auction metric riêng.

Các field/metric logical:

| English | Tiếng Việt |
|---|---|
| `ato_volume` | Khối lượng ATO |
| `ato_rvol` | RVOL riêng của ATO |
| `ato_price` | Giá ATO/mở cửa |
| `ato_gap_pct` | % chênh giá ATO so với giá tham chiếu ngày |
| `ato_baseline_sessions_used` | Số phiên baseline ATO |
| `ato_quality` | Chất lượng bằng chứng ATO |

`ato_gap_pct` phải dùng **SSI reference price của ngày** làm denominator khi available, không dùng raw previous close nếu reference price đã được điều chỉnh.

---

# 17. ATC - Closing Auction / Phiên khớp lệnh định kỳ đóng cửa

ATC là auction metric riêng.

Các field/metric logical:

| English | Tiếng Việt |
|---|---|
| `atc_volume` | Khối lượng ATC |
| `atc_rvol` | RVOL riêng của ATC |
| `atc_volume_share_pct` | Tỷ trọng ATC trong volume ngày |
| `atc_price_impact_pct` | % tác động giá của ATC |
| `atc_baseline_sessions_used` | Số phiên baseline ATC |
| `atc_quality` | Chất lượng bằng chứng ATC |

`atc_price_impact_pct` so ATC price với giá ngay trước ATC, không so previous close.

`atc_volume_share_pct` dùng official daily volume từ SSI DailyOhlc làm denominator khi DailyOhlc available.

Post-trading volume không được trộn vào ATC metric.

---

# 18. Baseline Selection Policy - Chính sách chọn phiên baseline

## 18.1 Target

Mục tiêu:

```text
10 valid previous sessions
10 phiên lịch sử hợp lệ gần nhất
```

Không cộng phiên hiện tại vào `sessions_used`.

## 18.2 Coverage tiers - Mức độ phủ

```text
10 sessions -> FULL                 (Đầy đủ)
 9 sessions -> ACCEPTABLE           (Chấp nhận)
 8 sessions -> ACCEPTABLE_MINIMUM   (Tối thiểu chấp nhận)
 0-7         -> INSUFFICIENT         (Không đủ)
```

Áp dụng cho ordinary continuous baselines:

- Day RVOL;
- RVOL15;
- RVOL30.

## 18.3 Break Blocks - Cụm gián đoạn dữ liệu

Baseline builder đi lùi qua lịch sử và được phép vượt tối đa:

```text
2 missing-data break blocks
2 cụm gián đoạn dữ liệu
```

`break block` là một cụm liên tiếp của các session unavailable/unproven.

Nếu gặp break block thứ 3 trước khi có đủ baseline hợp lệ thì baseline fail quality rule.

## 18.4 Intentional exclusion không phải break block

Các phiên bị loại có chủ đích vì reference adjustment/corporate action không được tính là missing-data break block.

Phân biệt:

```text
MISSING / UNPROVEN  -> có thể tạo break block
INTENTIONAL_EXCLUSION -> không tính break block
```

## 18.5 Per-metric validity - Hợp lệ theo từng metric

Một session có thể:

```text
MA10/MA200: VALID
Day RVOL:   INVALID
RVOL15:     INVALID
RVOL30:     INVALID
```

Không dùng một `whole_day_is_valid` duy nhất để loại tất cả metric.

---

# 19. Data Quality & Trust - Chất lượng và độ tin cậy

Hệ mới cần lưu/derive tối thiểu:

| English | Tiếng Việt |
|---|---|
| `quality_status` | Trạng thái chất lượng |
| `metrics_trusted` | Metric có đủ tin cậy hay không |
| `reason_codes` | Mã lý do |
| `baseline_sessions_used` | Số phiên baseline thực dùng |
| `baseline_target_sessions` | Mục tiêu số phiên |
| `baseline_coverage_pct` | % độ phủ baseline |
| `break_blocks` | Số cụm gián đoạn |
| `source` | Nguồn |
| `source_endpoint` | Endpoint nguồn |
| `is_final` | Đã chốt hay chưa |
| `config_version` | Phiên bản cấu hình |
| `engine_version` | Phiên bản engine |

Strong signal không được phát khi metric bắt buộc đang untrusted/insufficient.

---

# 20. Signal Engine V3 - Bộ máy tín hiệu V3

## 20.1 Bỏ 4 checkbox cũ

Không còn mô hình:

```text
1/4, 2/4, 3/4, 4/4
```

## 20.2 State model - Mô hình trạng thái

Giữ cấu trúc state-based:

| State | Tiếng Việt / Ý nghĩa |
|---|---|
| `NORMAL` | Bình thường, chưa có tín hiệu nổi bật |
| `WATCHING` | Theo dõi, volume/biến động bắt đầu đáng chú ý |
| `FLOW_APPEARING` | Dòng tiền đang xuất hiện |
| `FLOW_PRICE_CONFIRMED` | Dòng tiền và giá cùng xác nhận |
| `MOMENTUM_MAINTAINED` | Động lượng được duy trì |
| `MOMENTUM_WEAKENING` | Động lượng suy yếu |
| `SELLING_PRESSURE` | Áp lực bán, volume mạnh đi kèm giá giảm |

## 20.3 Signal inputs - Dữ liệu đầu vào

Signal engine có thể dùng:

- Day RVOL;
- RVOL15;
- RVOL30;
- Price5;
- Price15;
- MA10/MA200 context;
- ATO metrics;
- ATC metrics;
- data quality/trust;
- recent-high / momentum context nếu được cấu hình.

## 20.4 Reason codes - Mã lý do

Logical reason codes nên bao gồm các nhóm:

```text
DAY_RVOL_ELEVATED            - Day RVOL tăng cao
RVOL15_ELEVATED / STRONG     - RVOL15 tăng/cao mạnh
RVOL30_ELEVATED / STRONG     - RVOL30 tăng/cao mạnh
PRICE5_UP / DOWN             - Price5 tăng/giảm
PRICE15_UP / DOWN            - Price15 tăng/giảm
HIGH_VOLUME_PRICE_ABSORPTION - Volume cao nhưng giá hấp thụ/chưa chạy
ATO_RVOL_STRONG              - ATO volume tương đối mạnh
ATO_GAP_UP / DOWN            - Gap ATO tăng/giảm
ATC_RVOL_STRONG              - ATC RVOL mạnh
ATC_VOLUME_SHARE_HIGH        - Tỷ trọng volume ATC cao
ATC_PRICE_UP / DOWN          - ATC kéo/đạp giá
ABOVE_MA10 / BELOW_MA10      - Trên/dưới MA10
ABOVE_MA200 / BELOW_MA200    - Trên/dưới MA200
METRICS_UNTRUSTED            - Metric không đủ tin cậy
BASELINE_INCOMPLETE          - Baseline chưa đủ
REFERENCE_ADJUSTMENT_DAY     - Ngày điều chỉnh giá tham chiếu
```

## 20.5 Thresholds configurable - Ngưỡng cấu hình được

Không hard-code threshold rải trong source code.

Cấu hình phải có versioning và có thể thay đổi mà không đổi schema.

Tương lai hỗ trợ user/VIP personalization:

```text
Scalping / Lướt sóng
Swing / Giao dịch trung hạn
Long-term / Đầu tư dài hạn
```

Nguyên tắc:

- canonical market state vẫn dùng chung;
- personalization là overlay theo user;
- user threshold không sửa canonical raw market data.

---

# 21. Signal Events & Market Movers - Lịch sử tín hiệu và Bảng mã nổi bật

## 21.1 Signal event

Khi state thay đổi đáng kể, ghi event:

```text
NORMAL -> WATCHING
WATCHING -> FLOW_APPEARING
FLOW_APPEARING -> FLOW_PRICE_CONFIRMED
...
```

Signal event lưu ít nhất:

- symbol;
- trading date/time;
- previous state;
- new state;
- reason codes;
- relevant metric snapshot;
- config version;
- engine version;
- quality/trust.

## 21.2 Market Movers - Bảng mã nổi bật

Thay thế tư duy Golden Board 4/4.

Có thể thống kê:

- first signal time (thời điểm tín hiệu đầu);
- price at first signal (giá tại tín hiệu đầu);
- price after 15m / 30m (giá sau 15/30 phút);
- end-of-day price (giá cuối ngày);
- maximum favorable move (mức tăng thuận lợi lớn nhất);
- maximum adverse move (mức giảm bất lợi lớn nhất);
- final state (trạng thái cuối phiên);
- max RVOL / max momentum metrics.

Mục tiêu: CCC có dữ liệu để tự đánh giá thành tích tín hiệu theo ngày/tuần/tháng.

---

# 22. EOD - End of Day / Chốt dữ liệu cuối ngày

## 22.1 Nguyên tắc quan trọng nhất

SSI đã lưu ý daily volume có thể không bằng tổng volume cộng từ từng minute bar.

CCC **không ép hai lớp này bằng nhau**.

Quyền sở hữu:

```text
DailyOhlc    owns the day.
DailyOhlc    quyết định dữ liệu ngày.

IntradayOhlc owns the minutes.
IntradayOhlc quyết định dữ liệu từng phút.

FastConnect  owns live and auction evidence.
FastConnect  quyết định realtime và bằng chứng ATO/ATC.
```

Ba lớp được reconcile/audit nhưng không forced-equal.

## 22.2 Ví dụ discrepancy hợp lệ

```text
SUM(IntradayOhlc minute volume) = 7,820,000
DailyOhlc official volume       = 7,950,000
Difference                      =   130,000
```

Không được:

- cộng 130,000 vào phút cuối;
- scale lại toàn bộ minute volume;
- sửa ATC volume để khớp;
- thay DailyOhlc bằng minute sum.

## 22.3 EOD pipeline - Quy trình chốt cuối ngày

```text
1. FREEZE LIVE STATE
   Khóa trạng thái realtime của phiên
        |
2. WAIT FOR SSI DATA AVAILABILITY
   Chờ SSI REST thực sự available
        |
3. FETCH INTRADAYOHLC + DAILYOHLC
   Lấy lịch sử phút + ngày
        |
4. FINALIZE CANONICAL HISTORY
   Đóng minute history + daily history
        |
5. RECONCILE / AUDIT
   Đối chiếu, không ép bằng nhau
        |
6. FINALIZE AUCTION + SIGNAL HISTORY
   Chốt ATO/ATC + lịch sử tín hiệu
        |
7. BUILD NEXT-SESSION BASELINES
   Tạo baseline cho phiên kế tiếp
```

## 22.4 EOD không chạy vì một giờ cố định

Không coi `16:05` hay một clock time cố định là điều kiện đủ để finalize.

Điều kiện logic:

```text
SSI session has ended
AND
required SSI REST data is available/proven
-> finalize
```

Nếu SSI REST chưa available thì retry/backoff/checkpoint.

## 22.5 Reconciliation fields - Trường đối chiếu

Logical fields:

| English | Tiếng Việt |
|---|---|
| `minute_volume_sum` | Tổng volume cộng từ minute bars |
| `daily_volume_authoritative` | Volume ngày chính thức từ DailyOhlc |
| `volume_diff` | Chênh lệch tuyệt đối |
| `volume_diff_pct` | Chênh lệch % |
| `reconciliation_status` | Trạng thái đối chiếu |

Các status có thể gồm:

```text
MATCH                 - Khớp
DIFFERENT_EXPECTED    - Khác nhưng trong phạm vi chấp nhận/audit
LARGE_DIFFERENCE      - Chênh lớn, cần audit
MISSING_INTRADAY      - Thiếu IntradayOhlc
MISSING_DAILY         - Thiếu DailyOhlc
```

Khác biệt không tự động đồng nghĩa dữ liệu sai.

---

# 23. Reference Adjustment / GDKHQ - Điều chỉnh giá tham chiếu

## 23.1 Không đồng nhất GDKHQ với signal pause

`Ex-right date / Ngày GDKHQ` có thể chỉ để chốt quyền họp/biểu quyết và không nhất thiết làm đổi mặt bằng giá.

CCC chỉ pause signal khi có **reference-price adjustment (điều chỉnh giá tham chiếu)** ảnh hưởng price basis.

## 23.2 Raw data vẫn lưu đầy đủ

Ngày adjustment vẫn lưu:

- minute OHLCV;
- daily OHLCV;
- live quote;
- ATO/ATC evidence;
- volume;
- reference price;
- audit metadata.

Không xóa ngày này khỏi database.

## 23.3 Chart vẫn hiển thị

Chart giữ raw SSI data và đánh marker/banner:

```text
REFERENCE ADJUSTMENT DAY
NGÀY ĐIỀU CHỈNH GIÁ THAM CHIẾU
CCC SIGNAL PAUSED
CCC TẠM NGƯNG TÍN HIỆU TRONG PHIÊN NÀY
```

## 23.4 Signal trong ngày adjustment

```text
signal_enabled = FALSE
signal_pause_reason = REFERENCE_ADJUSTMENT_DAY
```

Không gửi strong alert/Market Movers performance như một signal bình thường.

Metrics vẫn có thể tính/lưu phục vụ audit, nhưng classifier không phát state tín hiệu giao dịch bình thường trong ngày đó.

## 23.5 Phân loại adjustment

Logical classification:

```text
PRICE_ONLY   - Điều chỉnh chủ yếu mặt bằng giá, ví dụ cổ tức tiền nhỏ
STRUCTURAL   - Thay đổi cấu trúc như split/stock dividend lớn/right issue có thể đổi volume regime
UNKNOWN      - Chưa đủ evidence để phân loại chắc chắn
```

## 23.6 Sau ngày PRICE_ONLY

- pause đúng ngày event;
- phiên sau signal được chạy lại bình thường;
- không reset Day RVOL/RVOL15/RVOL30 baseline chỉ vì refPrice khác previous close.

## 23.7 Sau ngày STRUCTURAL

- pause ngày event;
- volume baseline chuyển sang warm-up/rebuild từ các post-event sessions sạch;
- strong historical-RVOL conclusions được hạn chế đến khi coverage đủ theo policy;
- không nhất thiết tắt toàn bộ metric/engine trong 8 phiên.

Gợi ý trust ladder:

```text
0-2 post-event sessions -> historical RVOL strong signal chưa dùng
3-4 sessions            -> WATCHING / low confidence
5-7 sessions            -> degraded/limited
8 sessions              -> ACCEPTABLE_MINIMUM
9 sessions              -> ACCEPTABLE
10 sessions             -> FULL
```

## 23.8 UNKNOWN không tự động reset 8 phiên

Nếu chưa chứng minh được structural change:

- ngày event vẫn pause;
- không tự động reset volume baseline chỉ vì `refPrice != previous_close`;
- giữ quality/reason context để audit;
- structural reset chỉ kích hoạt khi có evidence đáng tin cậy.

## 23.9 Intentional exclusion

Ngày adjustment bị loại khỏi baseline khi policy của metric yêu cầu loại, nhưng không tính là missing-data break block.

## 23.10 MA/technical price basis

Raw SSI history không sửa.

Khi reference adjustment làm đứt price basis, engine có thể dùng `technical adjustment factor (hệ số điều chỉnh kỹ thuật)` nội bộ cho MA10/MA200 và technical comparison.

Không UPDATE lại raw minute/daily OHLCV.

---

# 24. Missing Data - Dữ liệu thiếu

## 24.1 Trong phiên

Nếu SSI thiếu phút:

```text
10:20 present
10:21 missing
10:22 present
```

CCC không tạo fake 10:21.

## 24.2 Cuối ngày

EOD thử lấy lại từ SSI REST.

Nếu vẫn thiếu:

- lưu `data_gap`;
- metric phụ thuộc phải degraded/unavailable theo policy;
- không dùng legacy Supabase/KBS/VCI làm fallback.

## 24.3 Missing DailyOhlc

Không tự tạo canonical daily bar bằng cách cộng/aggregate minute history rồi giả là SSI DailyOhlc.

Nếu DailyOhlc chưa có:

```text
daily finalize = pending/unavailable
```

và retry theo policy.

---

# 25. Proposed Logical Database Model - Mô hình database logic đề xuất

Đây là logical design. Tên table/index có thể tinh chỉnh trong migration mà không thay đổi product/data contract.

## 25.1 MARKET - Dữ liệu thị trường

### `minute_bars_1m` - Nến 1 phút
Canonical IntradayOhlc history.

### `daily_bars` - Nến ngày
Canonical DailyOhlc history.

### `live_quotes` - Giá/trạng thái realtime
Current live observation, không thay canonical historical tables.

### `auction_sessions` - Dữ liệu ATO/ATC
Lưu evidence/metrics auction.

### `market_reference_prices` - Giá tham chiếu ngày
Lưu refPrice, ceiling/floor, previous close, adjustment flags/classification.

## 25.2 BASELINE - Dữ liệu nền

### `volume_baselines`
Có thể chứa theo symbol + minute:

```text
avg_cumulative_volume
avg_volume_15m
avg_volume_30m
sessions_used
target_sessions
coverage_pct
break_blocks
first_session_used
last_session_used
quality_status
```

### `ma_baselines`
MA10/MA200 + session coverage + technical adjustment context.

### `baseline_session_usage`
Audit danh sách session thực sự được dùng/bỏ cho từng metric.

## 25.3 STATE - Trạng thái hiện tại

### `stock_state_current`
Một row/current projection cho mỗi symbol, phục vụ scanner/API.

Không dùng nó thay cho immutable history.

## 25.4 SIGNAL - Tín hiệu

### `signal_configs`
Config có version, effective range, threshold/rule definitions.

### `signal_events`
Immutable history của state transitions.

### `market_movers_daily`
Daily performance/summary của signal events.

## 25.5 OPS - Vận hành

### `ingest_runs`
Nhật ký ingest.

### `finalize_runs`
Nhật ký EOD.

### `backfill_state`
Checkpoint/resume historical backfill.

### `data_gaps`
Khoảng thiếu dữ liệu được ghi minh bạch.

### `reconciliation_runs`
Audit IntradayOhlc vs DailyOhlc và các consistency checks.

---

# 26. Source / Calculation Ownership Matrix - Ma trận nguồn và tính toán

| Output / Metric | Nguồn chính | Calculation / Ghi chú |
|---|---|---|
| Current Price (Giá hiện tại) | SSI FastConnect | Live |
| Current Cumulative Volume (KL tích lũy hiện tại) | SSI FastConnect | Live |
| 1m OHLCV (OHLCV 1 phút lịch sử) | SSI IntradayOhlc | Canonical after EOD |
| Daily OHLCV (OHLCV ngày) | SSI DailyOhlc | Canonical daily |
| 5m/15m/30m/1h Chart | 1m canonical + current live | Aggregate on read/cache |
| 1D Chart | DailyOhlc | Direct daily |
| Day RVOL | Live cumulative + IntradayOhlc baseline | Same-time cumulative |
| RVOL15 | Live 15m + IntradayOhlc baseline | Rolling 15m, minute-by-minute |
| RVOL30 | Live 30m + IntradayOhlc baseline | Rolling 30m, minute-by-minute |
| Price5 | FastConnect/live price history | 5-minute price momentum |
| Price15 | FastConnect/live price history | 15-minute price momentum |
| MA10 | DailyOhlc | Completed sessions |
| MA200 | DailyOhlc | Completed sessions |
| ATO metrics | FastConnect provider-session evidence | Auction-specific |
| ATC metrics | FastConnect provider-session evidence | Auction-specific |
| ATC volume share | ATC volume + DailyOhlc volume | DailyOhlc denominator |
| Signal State | Calculated metrics + config | Backend only |
| Signal Events | Signal engine | Versioned immutable history |

---

# 27. Temporary Supabase -> VPS PostgreSQL - Lộ trình hạ tầng

## 27.1 Giai đoạn hiện tại

NEW Supabase project được dùng như:

```text
Temporary PostgreSQL workspace
Không gian PostgreSQL tạm để xây, query, audit và sửa schema
```

Mục đích:

- quan sát dữ liệu thuận tiện;
- audit calculation;
- đối chiếu SSI;
- thử migration/schema;
- dễ query cùng ChatGPT/DB tooling.

## 27.2 Không khóa kiến trúc vào Supabase

Schema ưu tiên PostgreSQL portable:

- không phụ thuộc Supabase-specific feature nếu không cần;
- browser không đọc trực tiếp NEW Supabase;
- Auth/User/Watchlist vẫn ở OLD Supabase;
- market schema có thể migrate sang VPS PostgreSQL.

## 27.3 Điều kiện bắt đầu migration về VPS

Sau khoảng:

```text
5 consecutive stable trading sessions
5 phiên giao dịch ổn định liên tục
```

thì bắt đầu kế hoạch chuyển market database về PostgreSQL trên VPS.

Không có nghĩa phải xóa Supabase ngay ở phiên thứ 5; đây là trigger để bắt đầu cutover plan và đối chiếu.

---

# 28. EOD & Historical Backfill Operational Rules - Quy tắc vận hành

Historical download/backfill phải:

- checkpoint/resume;
- bounded batching;
- rate-limit aware;
- safe retry/backoff;
- không restart toàn job nếu bị ngắt;
- không tạo uncontrolled 800-symbol request storm;
- có per-symbol/per-date status.

Lịch chạy thực tế phụ thuộc dữ liệu/session SSI available, không hard-code một giờ thị trường như source of truth.

---

# 29. Migration Policy - Chính sách chuyển đổi

## 29.1 Không import market-data cũ làm canonical SSI baseline

Legacy Supabase market tables chỉ dùng:

- audit;
- comparison;
- regression reference khi cần.

Không dùng làm SSI V3 canonical input.

## 29.2 Dữ liệu giữ nguyên ở OLD Supabase

Ưu tiên không đụng:

- Auth;
- Profiles;
- Plans/Subscriptions;
- VIP Day;
- Watchlist;
- Metadata;
- Financial/BCTC.

## 29.3 SQLite runtime hiện tại

Không xóa trước khi PostgreSQL path mới proven và production cutover hoàn tất.

Trong migration, hệ mới có thể chạy song song và đối chiếu trước khi retire SQLite.

---

# 30. Acceptance Criteria - Tiêu chí nghiệm thu data layer mới

Hệ mới được xem là đạt khi:

1. SSI là market-data provider duy nhất.
2. Realtime 1 phút hoạt động ổn định.
3. Chart 5m/15m/30m/1h/1D liền mạch theo contract.
4. Historical 1m + Daily OHLCV được backfill từ 2025 trong phạm vi SSI cung cấp.
5. Day RVOL chạy từng phút đúng same-time cumulative baseline.
6. RVOL15/RVOL30 chạy rolling từng phút, phase-aware theo SSI/sàn.
7. Price5/Price15 đúng window và không cross lunch/auction sai quy tắc.
8. ATO/ATC tách riêng và có quality evidence.
9. MA10/MA200 dùng SSI DailyOhlc và không bị raw reference adjustment làm sai technical basis.
10. Baseline 10/9/8 sessions + 2 break blocks hoạt động đúng.
11. Missing data không bị biến thành zero/fallback provider khác.
12. EOD không ép DailyOhlc volume bằng sum minute volume.
13. Reference adjustment day được đánh dấu và pause signal đúng policy.
14. Signal engine state-based, configurable, versioned.
15. Signal Events/Market Movers lưu được performance history.
16. Backfill/EOD có checkpoint, health log và audit.
17. NEW Supabase chạy ổn khoảng 5 phiên liên tục trước khi bắt đầu VPS PostgreSQL migration.

---

# 31. Retired Assumptions - Các giả định chính thức bị loại bỏ

Các assumption sau không còn được dùng:

```text
5-minute snapshot là canonical intraday storage.
Daily Volume % dùng một field có thể đổi nghĩa theo thời điểm.
4 hard-coded signals là signal contract chính.
4/4 = Golden Board là tiêu chuẩn duy nhất.
FastConnect stream được copy thẳng thành canonical historical minute data.
Daily volume phải bằng tổng minute volume.
Mọi GDKHQ đều phải tắt signal nhiều phiên.
Mọi reference adjustment đều phải reset volume baseline 8 phiên.
EOD phải chạy vào một giờ hard-code cố định.
Legacy market-data có thể fallback khi SSI thiếu.
```

---

# 32. Glossary EN-VI - Từ điển thuật ngữ Anh-Việt

| English | Tiếng Việt |
|---|---|
| Canonical Data | Dữ liệu chuẩn/nguồn sự thật của hệ thống |
| Realtime / Live | Thời gian thực / đang chạy |
| Historical Data | Dữ liệu lịch sử |
| Intraday | Trong phiên |
| Daily | Theo ngày |
| OHLCV | Mở cửa - Cao nhất - Thấp nhất - Đóng cửa - Khối lượng |
| Cumulative Volume | Khối lượng tích lũy |
| Baseline | Dữ liệu nền so sánh |
| Relative Volume / RVOL | Khối lượng tương đối |
| Rolling Window | Cửa sổ trượt theo thời gian |
| Price Momentum | Động lượng giá |
| Auction | Phiên khớp lệnh định kỳ |
| Opening Auction / ATO | Phiên định kỳ mở cửa |
| Closing Auction / ATC | Phiên định kỳ đóng cửa |
| Reference Price | Giá tham chiếu |
| Reference Adjustment | Điều chỉnh giá tham chiếu |
| Ex-right Date | Ngày giao dịch không hưởng quyền |
| Structural Adjustment | Điều chỉnh làm thay đổi cấu trúc/mặt bằng giao dịch |
| Price-only Adjustment | Điều chỉnh chủ yếu ở mặt bằng giá |
| Break Block | Cụm gián đoạn dữ liệu |
| Intentional Exclusion | Phiên bị loại có chủ đích |
| Quality Status | Trạng thái chất lượng dữ liệu |
| Trusted Metrics | Chỉ số đủ tin cậy |
| Reason Code | Mã lý do |
| Signal State | Trạng thái tín hiệu |
| Signal Event | Sự kiện thay đổi tín hiệu |
| Market Movers | Bảng mã nổi bật/biến động đáng chú ý |
| Reconciliation | Đối chiếu dữ liệu |
| Finalization / EOD | Chốt dữ liệu cuối ngày |
| Backfill | Bổ sung dữ liệu lịch sử |
| Checkpoint / Resume | Điểm lưu tiến độ / tiếp tục chạy |
| Provenance | Nguồn gốc dữ liệu |
| Configuration Version | Phiên bản cấu hình |
| Engine Version | Phiên bản bộ máy tính/tín hiệu |
| Warm-up | Giai đoạn tích lũy lại dữ liệu nền |
| Degraded | Suy giảm chất lượng/độ tin cậy |
| Full Coverage | Độ phủ đầy đủ |

---

# 33. Implementation Boundary - Ranh giới triển khai

Sau tài liệu này, phần còn lại chủ yếu là quyết định kỹ thuật:

- tên physical table/index cuối cùng;
- PostgreSQL types;
- partitioning;
- index strategy;
- caching/materialized aggregation;
- transaction boundaries;
- retry parameters;
- EOD worker implementation;
- exact API projection mapping.

Các quyết định kỹ thuật được phép tối ưu nhưng **không được thay đổi các business/data rules đã chốt trong tài liệu này**.

---

# 34. Final Source-of-Truth Statement - Tuyên bố nguồn quy chuẩn cuối

Từ 24/09/2026, hướng thiết kế market-data CCC được hiểu như sau:

```text
SSI FastConnect
= Realtime + Live State + ATO/ATC Evidence
= Realtime + Trạng thái live + Bằng chứng ATO/ATC

SSI IntradayOhlc
= Canonical 1-minute Historical Data
= Lịch sử 1 phút chuẩn

SSI DailyOhlc
= Canonical Daily OHLCV
= OHLCV ngày chuẩn

CCC Calculation Layer
= Day RVOL + RVOL15 + RVOL30 + Price5 + Price15 + MA10 + MA200 + Auction Metrics
= Lớp tính toán chỉ số CCC

CCC Signal Engine
= Configurable State Machine + Reason Codes + Versioning
= Bộ máy trạng thái tín hiệu có cấu hình + mã lý do + version

NEW Supabase PostgreSQL
= Temporary Build/Audit Database
= Database tạm để xây và audit

VPS PostgreSQL
= Planned Long-term Market Database after stable proof
= Database market dài hạn sau khi chạy ổn định được chứng minh
```

**END OF CANONICAL CONTRACT**
