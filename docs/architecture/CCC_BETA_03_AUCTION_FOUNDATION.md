# CCC BETA-03 — Auction data foundation

## Why boundary minute bars are insufficient

The existing one-minute table is a canonical minute projection, not a raw
provider-event archive. A minute label at an auction boundary does not prove
that all volume in that minute belongs to the auction.

The FPT observations from 18 September 2026 demonstrate the ambiguity. The
09:15 bar opened at 74,500, traded between 74,400 and 74,600, closed at 74,600,
and carried 1,376,000 shares. The official daily open was 74,500. That bar can
therefore include both the opening-auction result and early continuous trades;
its full volume is not canonical ATO volume.

At the close, FPT was about 73,900 with cumulative volume 6,980,600 at 14:29.
The 14:45 boundary bar closed at 71,700 and final cumulative volume was
15,500,700. The observed 14:45 boundary/cumulative delta of 8,520,100 is used
as a golden semantic fixture, with a price response of about -2.977%. Exact
historical ATC attribution remains pending raw SSI `TradingSession` event
evidence; that historical event corpus is not available. The deterministic
fixture labels a synthetic event `ATC` only to exercise the engine. Large
volume therefore does not imply positive flow.

## Provider-session authority

Auction classification follows SSI `TradingSession`, preserved on the
internal realtime event:

- `ATO` → `OPEN_AUCTION`
- `ATC` → `CLOSE_AUCTION`
- `LO`, `PT`, `C`, `BREAK`, and `HALT` are not auction volume

Neither `09:15` nor `14:45` is sufficient to classify an event as auction.
Auction state is stored separately in `auction_session_buckets`; the
`minute_bars` primary key and continuous Price/RVOL domains are unchanged.

## Cumulative high-watermark accounting

For each symbol and trading date, the projection keeps a monotonic SSI
`TotalVol` high-watermark:

- a higher total contributes only the positive difference to the event's
  provider session and advances the watermark;
- an equal total contributes zero;
- a lower total records `OUT_OF_ORDER_REGRESSION`, contributes zero, and never
  lowers the watermark;
- a missing total is a real quality failure and contributes no invented
  volume.

Gaps, partial events, unsupported sources, unsupported sessions, and missing
totals degrade settled quality. A regression is retained as an event anomaly
and increments `out_of_order_events`, but does not by itself invalidate a
reconstructable finalized auction.

The accumulator hydrates its high-watermark, last useful LO price, structural
event chronology, and existing auction buckets from local SQLite state on the
first event after restart. Restarting immediately before or during ATC thus
appends only volume above the persisted cumulative total. A regression or an
event older than the last accepted structural event cannot replace canonical
auction/pre-close prices, move accepted event time backward, or finalize a
bucket. A chronologically valid duplicate-total transition such as `ATC → C`
may finalize the bucket but contributes zero volume.

## Auction features

The pure feature contract exposes:

- opening auction price, volume, RVOL, and gap percentage;
- pre-close price;
- closing auction price, volume, RVOL, day-volume share, and price impact.

Definitions:

```text
opening_gap_pct = (opening_auction_price / ref_price - 1) × 100
closing_price_impact_pct =
  (closing_auction_price / last_continuous_price - 1) × 100
closing_volume_share_pct = closing_auction_volume / total_day_volume × 100
```

ATO-RVOL uses only opening-auction volumes; ATC-RVOL uses only closing-auction
volumes. Each uses the exact previous ten candidate sessions. A bad or missing
session is not replaced by an older eleventh session. A partial history may
produce a diagnostic ratio, but the corresponding auction domain stays
untrusted. A zero denominator returns `NULL`.

The foundation records whether negative closing price response is eligible as
input to a future `SELLING_PRESSURE` evaluation. It does not define signal
thresholds, levels, or state transitions, and never infers positive flow from
volume alone.

## Deployment boundary

BETA-03 is local code and deterministic fixtures only. It does not access or
mutate production, Supabase, or a VPS, and it performs no deployment.
