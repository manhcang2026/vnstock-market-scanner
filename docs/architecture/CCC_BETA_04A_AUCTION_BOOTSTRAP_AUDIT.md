# CCC BETA-04A — KBS/VCI Auction Bootstrap Audit

Audit date: 2026-09-18

Evaluation date: 2026-09-18

Scope: read-only historical audit; no canonical runtime writes and no Signal Engine changes.

## Decision

| Domain | Recommendation | Evidence |
|---|---|---|
| ATO | **DO_NOT_BOOTSTRAP** | 178/180 provider-session rows have a 09:15 bar whose OHLC is not a single official daily-open price. The bar therefore mixes the auction boundary with continuous trading and cannot isolate exact ATO volume. |
| ATC | **DIAGNOSTIC_ONLY** | All 180 provider-session rows expose one isolated 14:45 closing bar and all 90 KBS/VCI comparisons match exactly. However, VCI intraday volume does not reconcile exactly with VCI daily volume in 9/90 rows. No tolerance has been approved, so this is not promoted to temporary bootstrap. |

No KBS/VCI result is `PROVEN`. A usable historical boundary is labelled only
`INFERRED_BOUNDARY`; insufficient evidence is `UNAVAILABLE`.

## Data and provider availability

- Symbols: FPT, HPG, SSI, VIC, VCB, VIX (all HOSE).
- Completed sessions: 15, strictly before 2026-09-18, from 2026-08-25 through 2026-09-17.
- KBS: minute and daily history succeeded for 6/6 symbols.
- VCI: minute and daily history succeeded for 6/6 symbols.
- Provider-session rows: 180 (90 KBS + 90 VCI).
- Cross-provider comparisons: 180 (90 ATO + 90 ATC).
- The runner is paced at 3.2 seconds between vnstock requests to remain below the observed Guest limit of 20 requests/minute. A faster exploratory run hit that documented local quota; the final run completed without provider failures.

The provider adapters returned normalized `time`, OHLC, and `volume`. The audit
retains these fields for the opening/closing inspection windows, boundary bars,
last continuous bar, and final bar. Extra provider fields are retained when the
adapter exposes them. It does not retain or commit every raw intraday bar.

## ATO findings

- Both providers returned a 09:15 boundary bar in all 90 symbol-sessions.
- KBS and VCI match exactly on timestamp, daily-open price, and 09:15 bar volume
  in all 90 comparisons (`STRONG_AGREEMENT` under the audit's exact-equality
  classification).
- Exact cross-provider agreement does **not** make the bar exact ATO evidence.
- Only FPT on 2026-08-26 has a 09:15 OHLC bar equal to the daily open on all four
  prices: 1/90 rows for each provider, or 1.11% usable coverage.
- The remaining 89/90 rows per provider have OHLC movement away from the daily
  open inside the 09:15 bar. Their ATO inference quality is `UNAVAILABLE`.

Conclusion: historical one-minute data cannot generally isolate exact ATO
volume. ATO bootstrap is rejected even though KBS and VCI share the same bar
shape.

## ATC findings

- Every provider-session has a last continuous bar at or before 14:29 and one
  isolated final 14:45 bar.
- ATC usable coverage is 90/90 for KBS and 90/90 for VCI.
- All 90 KBS/VCI ATC comparisons agree exactly on final timestamp, final price,
  and candidate closing-boundary volume.
- Candidate closing volume share ranges from 1.6833% to 46.6567% of summed
  intraday volume (median 7.1748%).
- Inferred closing price impact ranges from -3.0075% to +2.2222% (median
  -0.2286%).

The cross-provider result is structurally strong, but the daily reconciliation
exception below prevents an approval without an explicit provider-semantics
decision. ATC therefore remains diagnostic only.

## Daily-volume reconciliation

| Provider | Exact | Mismatch | Missing daily | Total |
|---|---:|---:|---:|---:|
| KBS | 90 | 0 | 0 | 90 |
| VCI | 81 | 9 | 0 | 90 |

The nine VCI mismatches are:

- SSI: 2026-08-25, 2026-08-26, 2026-08-27.
- VIX: 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28,
  2026-09-03, 2026-09-04.

In each mismatch, the summed VCI minute volume is below VCI daily volume. The
absolute percentage difference is 0.06497%–0.12025% (median 0.10250%). The audit
records the raw differences and does not call them reconciled or introduce a
rounding tolerance. KBS reconciles exactly for the same audited set.

## FPT sample — 2026-09-17

KBS and VCI return the same values:

- 226 minute bars; daily open 73.3.
- 09:15 boundary volume 85,500, but the bar is mixed; ATO is `UNAVAILABLE`.
- Last continuous bar: 14:29 at 74.0.
- Final isolated bar: 14:45 at 74.3, volume 1,887,000.
- Candidate closing share: 28.4757%.
- Inferred closing price impact: +0.4054%.
- Intraday and daily volume: 6,626,700, reconciled exactly.
- ATC quality remains `INFERRED_BOUNDARY`, never `PROVEN`.

## Classification method and ambiguity

The audit deliberately uses no materiality tolerance:

- `STRONG_AGREEMENT`: exact boundary timestamp, price, and volume equality.
- `WEAK_AGREEMENT`: equal timestamp and price but a measurable volume difference.
- `DISAGREEMENT`: timestamp or price differs.
- `SINGLE_SOURCE`: only one provider has the boundary.
- `UNAVAILABLE`: neither provider has a boundary.

This exact-equality method makes the raw evidence visible without silently
choosing a product threshold. The observed VCI daily-volume differences may be
provider semantics (for example, trades represented in daily totals but absent
from one-minute OHLC), but the available fields do not prove the cause.

## Locked future policy

If a later job explicitly approves temporary ATC bootstrap:

- inferred history must remain `INFERRED_BOUNDARY`;
- new SSI realtime TradingSession evidence remains `PROVEN`;
- the exact previous-10 candidate dates remain fixed, with no older 11th-date
  replacement;
- PROVEN SSI sessions progressively replace inferred sessions;
- after 10/10 PROVEN SSI sessions, inferred bootstrap is irrelevant; and
- provenance and quality metadata remain preserved.

None of this replacement logic is implemented by BETA-04A.

## Remaining blocker and next job

Remaining blocker: explain or formally contract the nine VCI daily-versus-minute
volume differences and obtain Product Owner approval for any tolerance or
single-provider reconciliation rule.

**NEXT JOB ONLY:** BETA-04B — validate VCI volume semantics for the nine named
rows against provider documentation/raw contract, then decide whether ATC may
move from `DIAGNOSTIC_ONLY` to `ALLOW_TEMP_INFERRED_BOOTSTRAP`. Do not implement
runtime bootstrap until that decision is approved.

## Artifacts

- `services/ssi_realtime_shadow/audit/auction_bootstrap_audit_summary.json`
- `services/ssi_realtime_shadow/audit/auction_bootstrap_audit_rows.csv`
- `services/ssi_realtime_shadow/audit/auction_bootstrap_provider_comparison.csv`
