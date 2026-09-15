#!/usr/bin/env bash
set -uo pipefail

CONTAINER="ccc-ssi-shadow"
SOURCE_DB="/app/data/ssi_shadow.db"
HISTORY_DB="/app/data/ssi_history_2026.db"
DAY="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Idempotent day-level exit. Do not re-hit SSI REST after a successful finalize.
PREVIOUS_STATUS="$(docker exec -i "$CONTAINER" python - "$DAY" "$HISTORY_DB" <<'PY'
import sqlite3, sys

day, db = sys.argv[1], sys.argv[2]
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = con.execute(
        "SELECT status FROM daily_finalize_runs WHERE trading_date=?", (day,)
    ).fetchone()
    print(row[0] if row else "")
    con.close()
except Exception:
    print("")
PY
)"

if [[ "$PREVIOUS_STATUS" == "PASS" || "$PREVIOUS_STATUS" == "REST_PASS" ]]; then
  log "Already finalized: day=$DAY status=$PREVIOUS_STATUS"
  exit 0
fi

log "Strict realtime finalize: day=$DAY"
if docker exec "$CONTAINER" \
  python -m app.daily_finalize \
    --source "$SOURCE_DB" \
    --history "$HISTORY_DB" \
    --date "$DAY"; then
  log "Realtime finalize PASS"
  exit 0
fi

log "Realtime QA blocked. Falling back to SSI REST 1-minute rebuild."
CLI_DATE="$(date -d "$DAY" '+%d/%m/%Y')"

set +e
docker exec \
  -e DATABASE_PATH="$HISTORY_DB" \
  "$CONTAINER" \
  python -m app.historical_bootstrap \
    --from-date "$CLI_DATE" \
    --to-date "$CLI_DATE"
BOOTSTRAP_RC=$?
set -e

log "REST bootstrap returned rc=$BOOTSTRAP_RC; evaluating checkpoints + canonical history."

docker exec -i "$CONTAINER" python - "$DAY" "$SOURCE_DB" "$HISTORY_DB" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

DAY, SOURCE_DB, HISTORY_DB = sys.argv[1:4]
VN = ZoneInfo("Asia/Ho_Chi_Minh")

source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
hist = sqlite3.connect(HISTORY_DB)
hist.row_factory = sqlite3.Row

# NoDataFound is a legitimate symbol/day outcome, not a fatal provider error.
hist.execute(
    """
    UPDATE historical_bootstrap_checkpoints
    SET status='NO_DATA', row_count=0,
        completed_at=COALESCE(completed_at, last_attempt_at)
    WHERE from_date=? AND to_date=? AND resolution=1
      AND status='FAILED'
      AND error LIKE '%NoDataFound%'
    """,
    (DAY, DAY),
)
hist.commit()

status_counts = {
    str(r["status"]): int(r["n"])
    for r in hist.execute(
        """
        SELECT status, COUNT(*) n
        FROM historical_bootstrap_checkpoints
        WHERE from_date=? AND to_date=? AND resolution=1
        GROUP BY status
        """,
        (DAY, DAY),
    )
}
checkpoint_total = sum(status_counts.values())
bad_checkpoints = sum(
    n for status, n in status_counts.items()
    if status not in {"COMPLETED", "NO_DATA"}
)

expected_row = source.execute(
    "SELECT value FROM collector_meta WHERE key='universe_size'"
).fetchone()
expected_universe = int(expected_row[0]) if expected_row else None
stream_symbols = int(source.execute(
    "SELECT COUNT(DISTINCT symbol) FROM minute_bars WHERE trading_date=?", (DAY,)
).fetchone()[0])

r = hist.execute(
    """
    SELECT COUNT(*) rows,
           COUNT(DISTINCT symbol) symbols,
           COUNT(DISTINCT minute) minutes,
           MIN(minute) first_minute,
           MAX(minute) last_minute,
           COALESCE(SUM(is_partial),0) partial_rows,
           COALESCE(SUM(has_gap),0) gap_rows,
           COALESCE(SUM(CASE
             WHEN high < low
               OR open < low OR open > high
               OR close < low OR close > high
             THEN 1 ELSE 0 END),0) invalid_ohlc_rows,
           COALESCE(SUM(CASE WHEN volume < 0 THEN 1 ELSE 0 END),0)
             negative_volume_rows
    FROM minute_bars
    WHERE trading_date=?
    """,
    (DAY,),
).fetchone()

quality_counts = {
    str(x[0]): int(x[1])
    for x in hist.execute(
        "SELECT quality_status, COUNT(*) FROM minute_bars WHERE trading_date=? GROUP BY quality_status",
        (DAY,),
    )
}

reasons = []
if r["rows"] < 20000:
    reasons.append("rest_rows<20000")
if r["symbols"] < 500:
    reasons.append("rest_symbols<500")
if r["symbols"] < stream_symbols:
    reasons.append(f"rest_symbols={r['symbols']}<stream_symbols={stream_symbols}")
if r["minutes"] < 200:
    reasons.append("rest_minutes<200")
if r["last_minute"] is None or r["last_minute"] < "14:45":
    reasons.append("rest_last_minute<14:45")
if r["gap_rows"]:
    reasons.append(f"rest_gap_rows={r['gap_rows']}")
if r["negative_volume_rows"]:
    reasons.append(f"rest_negative_volume_rows={r['negative_volume_rows']}")
if bad_checkpoints:
    reasons.append(f"rest_bad_checkpoints={bad_checkpoints}")
if expected_universe is not None and checkpoint_total != expected_universe:
    reasons.append(
        f"rest_checkpoints={checkpoint_total}!=universe={expected_universe}"
    )

# Historical SSI occasionally emits internally inconsistent OHLC bars. Preserve the
# raw provider row; ChartDataStore filters those candles by default. Report, don't block.
status = "REST_PASS" if not reasons else "REST_BLOCKED"
now = datetime.now(VN).isoformat()

hist.execute(
    """
    UPDATE daily_finalize_runs
    SET status=?,
        inserted_rows=?,
        history_rows=?,
        symbols=?,
        minutes=?,
        partial_rows=?,
        gap_rows=?,
        invalid_ohlc_rows=?,
        quality_json=?,
        details_json=?,
        finalized_at=?
    WHERE trading_date=?
    """,
    (
        status,
        int(r["rows"]),
        int(r["rows"]),
        int(r["symbols"]),
        int(r["minutes"]),
        int(r["partial_rows"]),
        int(r["gap_rows"]),
        int(r["invalid_ohlc_rows"]),
        json.dumps(quality_counts, sort_keys=True),
        json.dumps(
            {
                "reasons": reasons,
                "fallback": "SSI_REST",
                "checkpoint_status": status_counts,
                "invalid_ohlc_policy": "preserve_raw_filter_in_chart_api",
            },
            sort_keys=True,
        ),
        now,
        DAY,
    ),
)
hist.commit()

print(json.dumps({
    "trading_date": DAY,
    "status": status,
    "rows": int(r["rows"]),
    "symbols": int(r["symbols"]),
    "stream_symbols": stream_symbols,
    "minutes": int(r["minutes"]),
    "first_minute": r["first_minute"],
    "last_minute": r["last_minute"],
    "invalid_ohlc_rows": int(r["invalid_ohlc_rows"]),
    "negative_volume_rows": int(r["negative_volume_rows"]),
    "checkpoint_status": status_counts,
    "checkpoint_total": checkpoint_total,
    "expected_universe": expected_universe,
    "reasons": reasons,
}, ensure_ascii=False))

source.close()
hist.close()
raise SystemExit(0 if status == "REST_PASS" else 2)
PY
