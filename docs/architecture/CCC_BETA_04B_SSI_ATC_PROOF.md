# CCC BETA-04B — SSI Historical ATC Cross-Provider Proof

Audit date: 2026-09-18

Evaluation date: 2026-09-18

## Decision

**ALLOW_TEMP_INFERRED_BOOTSTRAP**

All 90 SSI canonical symbol-session rows pass the locked proof contract. The
approved provenance for a future implementation is:

- `source=SSI_REST`
- `quality=INFERRED_BOUNDARY`
- `proof=CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1`

This is eligibility proof only. No bootstrap row was written to a runtime table
and no Signal Engine behavior changed. Historical one-minute evidence is never
`PROVEN`.

ATO remains **DO_NOT_BOOTSTRAP** from BETA-04A and was not reconsidered.

## Input verification

The audit used only local files from
`services/ssi_realtime_shadow/audit/beta04b_input/`; it made no SSI, KBS, or VCI
network request.

| Input evidence | Verified result |
|---|---:|
| Existing SSI REST one-minute rows | 17,617 |
| Gap SSI REST rows for 16–17 September | 2,711 |
| Combined canonical SSI REST rows | 20,328 |
| Combined source | 20,328 `SSI_REST` |
| Combined quality | 20,328 `TRUSTED` |
| Duplicate symbol/date/minute keys | 0 |
| Required symbol-session combinations | 90/90 |
| Missing combinations | 0 |
| SSI DailyOhlc rows | 90 |
| Extraction reconciliation rows marked exact | 90/90 |

The named archive was not present in the local input directory, so its supplied
SHA256 could not be independently recomputed in this workspace. This did not
block the proof because every required extracted CSV was present and was
cross-checked internally by counts, keys, source/quality, and volume sums. Raw
input files remain ignored and uncommitted.

## Locked proof contract

Every accepted row satisfies all of these conditions:

1. SSI has a last continuous bar at or before 14:29.
2. SSI has exactly one post-continuous bar from 14:30 through 14:47.
3. That candidate is the final session bar.
4. Its OHLC values are one identical closing price.
5. Summed SSI one-minute volume exactly equals SSI DailyOhlc volume.
6. The committed KBS witness exists.
7. The committed VCI witness exists.
8. SSI's normalized boundary minute matches both witnesses.
9. SSI's closing price matches both witnesses exactly.
10. SSI's boundary volume matches both witnesses exactly.

No percentage tolerance is used. Original SSI provider timestamps are retained,
then normalized to the minute only for structural comparison.

SSI prices remain in official full-VND units with no scaling. BETA-04A vnstock
witness prices are stored in thousands of VND, so comparison uses the exact,
documented conversion `witness_price × 1,000`. Both raw and normalized witness
prices remain in the evidence output.

## Real proof result

- Rows attempted: 90.
- `CONFIRMED_INFERRED_BOUNDARY`: 90.
- `UNCONFIRMED_BOUNDARY`: 0.
- `UNAVAILABLE`: 0.
- SSI/KBS/VCI exact minute, price, and volume matches: 90/90.
- Three-provider mismatches: 0.
- SSI intraday sum versus SSI DailyOhlc exact: 90/90.
- SSI daily mismatches: 0.
- Historical rows labelled `PROVEN`: 0.

KBS and VCI are witnesses only. Neither becomes canonical data, and their daily
volumes are not used as the reconciliation denominator. The nine small VCI
daily-volume differences found in BETA-04A therefore do not reject these
SSI-canonical rows.

## Exact previous 10

The dates were derived by the existing BETA-02
`load_candidate_market_sessions()` semantics from the union of trusted SSI
DailyOhlc dates and canonical SSI minute dates strictly before 2026-09-18:

1. 2026-09-04
2. 2026-09-07
3. 2026-09-08
4. 2026-09-09
5. 2026-09-10
6. 2026-09-11
7. 2026-09-14
8. 2026-09-15
9. 2026-09-16
10. 2026-09-17

Every audited symbol—FPT, HPG, SSI, VIC, VCB, and VIX—has 10/10 confirmed
inferred boundaries in this fixed window. No failed date was skipped and no
older 11th date was substituted.

## FPT 2026-09-17

| Evidence | Value |
|---|---:|
| SSI last continuous raw time | 14:29:59 |
| SSI last continuous minute / price | 14:29 / 74,000 |
| SSI closing boundary raw time | 14:45:00 |
| SSI closing price | 74,300 |
| SSI closing volume | 1,887,000 |
| SSI intraday and DailyOhlc volume | 6,626,700 |
| KBS minute/price/volume match | Yes |
| VCI minute/price/volume match | Yes |
| Classification | `CONFIRMED_INFERRED_BOUNDARY` |

The row carries `SSI_REST + INFERRED_BOUNDARY +
CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1`.

## SSI REST versus SSI STREAM settlement

For the six symbols on 2026-09-16 and 2026-09-17, all 12 settled 14:45 SSI
STREAM close/volume pairs match SSI REST exactly. There are zero differences.

VIX on 2026-09-16 is the important quality observation:

- STREAM event-level row: `quality_status=VOLUME_REGRESSION`, `is_partial=1`.
- STREAM settled close/volume: 12,650 / 6,264,100.
- REST closing close/volume: 12,650 / 6,264,100.
- Settled price and volume match exactly.

This supports the existing distinction between event quality and settled data
quality. It does not create or modify a production quality rule.

## Future intended behavior

If runtime bootstrap is separately approved and implemented:

- Historical: `SSI_REST + INFERRED_BOUNDARY +
  CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1`.
- Future realtime: `SSI_STREAM + PROVEN`, based only on raw provider
  `TradingSession` evidence.
- Exact previous 10 evolves from 1 PROVEN + 9 INFERRED, through 5 + 5, to
  10 PROVEN.
- A failed exact candidate is never replaced by an older 11th session.
- After 10/10 PROVEN, historical inferred bootstrap is irrelevant.

BETA-04B does not implement this runtime behavior.

## Remaining blocker and next job

There is no remaining evidence blocker for temporary ATC inferred-bootstrap
eligibility. Product Owner approval is still required before runtime mutation.

**NEXT JOB ONLY:** BETA-04C — implement the approved SSI-only ATC bootstrap
writer and exact previous-10 replacement lifecycle, with dry-run/idempotency,
provenance preservation, and no ATO bootstrap. Do not deploy as part of that job
unless separately authorized.

## Artifacts

- `services/ssi_realtime_shadow/audit/ssi_atc_proof_summary.json`
- `services/ssi_realtime_shadow/audit/ssi_atc_proof_rows.csv`
- `services/ssi_realtime_shadow/audit/ssi_atc_exact10_coverage.csv`
