# CCC Golden Board — locked product rules (local preview)

## Purpose
Golden Board is a historical log of symbols that the CCC backend has actually recorded at **4/4** during a trading session.

It is not the same thing as the current `4/4` KPI:
- `Đang đạt 4/4` = current/latest scanner state.
- `Bảng vàng` = symbols that reached 4/4 at least once during that session.

## Admission rule
A symbol is admitted only when all current CCC technical signals are true:
1. Price change >= 3%
2. Daily volume >= 200% of AvgVol10
3. Price above MA200
4. RVOL30 >= 200%

`rvol30_sessions` is saved as historical metadata only. It never blocks admission.

## History
- One row per `(trading_date, symbol)`.
- The row is never removed when the symbol later falls to 3/4 or lower.
- Store first 4/4 time, latest 4/4 time, distinct 4/4 scan slots, hit count, best consecutive 5-minute streak, first/last hit metrics and latest observed state.
- Same `time_slot` retry never increments the hit count.
- A new trading day creates a new daily board. Old daily boards remain available.
- Do not hard-reset/delete at 09:00.

## Capture architecture
Golden Board capture is attached to `public.stock_snapshot` by a database trigger. The production scanner code is unchanged. This isolates the feature and starts collecting history without publishing the new UI.

## Access / teaser
- Guest: total daily count + maximum 2 real symbols; active-day teaser is delayed by 20 minutes.
- Non-full member: complete Golden Board only inside their personal watchlist/entitled technical scope.
- VIP/full-market: complete Golden Board across the market.
- Direct table access is blocked for `anon` and `authenticated`; access is through security-definer RPCs.

## Weekly ranking
Authenticated weekly summary ranks by:
1. number of sessions appearing on Golden Board;
2. best consecutive 4/4 scan streak;
3. total distinct 4/4 scan slots;
4. average RVOL30 across 4/4 hits.

UI calls it `Mã Vàng Tuần` only after at least two sessions have accumulated; otherwise it shows that weekly data is still accumulating.

## Frontend preview
This branch adds:
- a Golden Board entry to desktop left navigation;
- a Golden Board entry to mobile bottom navigation, replacing `Hướng dẫn` there (Guide remains reachable from the header `?`);
- `/bang-vang/`;
- a small Golden Board card on Overview;
- guest teaser and member/full-market views;
- Dark/Light and responsive styles.

Production HawkHost must remain on v19.11.4 until Product Owner explicitly approves deployment.
