#!/usr/bin/env bash
set -uo pipefail

CONTAINER="ccc-ssi-shadow"
SOURCE_DB="/app/data/ssi_shadow.db"
HISTORY_DB="/app/data/ssi_history_2026.db"
MARKET_DB="/app/data/ccc_market_v2.db"
DAY="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Idempotent exit requires both a success status and complete canonical outputs.
if docker exec -i "$CONTAINER" python - \
  "$DAY" "$SOURCE_DB" "$HISTORY_DB" "$MARKET_DB" <<'PY'
import json
import sqlite3
import sys
from dataclasses import asdict

from app.daily_finalize import canonical_day_completeness

day, source_db, history_db, market_db = sys.argv[1:5]
try:
    con = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
    row = con.execute(
        "SELECT status FROM daily_finalize_runs WHERE trading_date=?", (day,)
    ).fetchone()
    con.close()
    status = str(row[0]) if row else ""
    if status not in {"PASS", "REST_PASS"}:
        raise SystemExit(2)
    proof = canonical_day_completeness(
        source_path=source_db,
        history_path=history_db,
        market_path=market_db,
        trading_date=day,
    )
    print(json.dumps({"status": status, **asdict(proof)}, sort_keys=True))
    raise SystemExit(0 if proof.complete else 2)
except (OSError, sqlite3.Error, ValueError):
    raise SystemExit(2)
PY
then
  log "Already finalized with complete canonical outputs: day=$DAY"
  exit 0
fi

log "Canonical stream-first finalize: day=$DAY"
if docker exec "$CONTAINER" \
  python -m app.daily_finalize \
    --source "$SOURCE_DB" \
    --history "$HISTORY_DB" \
    --market "$MARKET_DB" \
    --date "$DAY" \
    --stream-primary \
    --write; then
  log "Canonical stream finalize PASS"
  exit 0
fi

log "Stream finalize did not fully pass. Deriving bounded REST repair set."
set +e
REPAIR_SYMBOLS="$(docker exec -i "$CONTAINER" python - "$DAY" "$HISTORY_DB" <<'PY'
import json
import sqlite3
import sys

from app.daily_finalize import repair_plan_from_details

day, history_db = sys.argv[1:3]
con = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
row = con.execute(
    "SELECT status, details_json FROM daily_finalize_runs WHERE trading_date=?",
    (day,),
).fetchone()
con.close()
if row is None:
    print("MISSING_FINALIZE_JOURNAL", file=sys.stderr)
    raise SystemExit(2)
try:
    details = json.loads(str(row["details_json"] or ""))
except (TypeError, ValueError):
    details = None
plan = repair_plan_from_details(details, status=str(row["status"] or ""))
if not plan.bounded:
    print(plan.reason, file=sys.stderr)
    raise SystemExit(2)
print(",".join(plan.symbols))
PY
)"
REPAIR_PLAN_RC=$?
set -e
if [[ $REPAIR_PLAN_RC -ne 0 || -z "$REPAIR_SYMBOLS" ]]; then
  log "No bounded REST repair set; failing closed without bootstrap."
  exit 2
fi

log "Running targeted SSI REST repair/backfill: symbols=$REPAIR_SYMBOLS"
CLI_DATE="$(date -d "$DAY" '+%d/%m/%Y')"

set +e
docker exec \
  -e DATABASE_PATH="$HISTORY_DB" \
  "$CONTAINER" \
  python -m app.historical_bootstrap \
    --from-date "$CLI_DATE" \
    --to-date "$CLI_DATE" \
    --symbols "$REPAIR_SYMBOLS"
BOOTSTRAP_RC=$?
set -e

log "REST bootstrap returned rc=$BOOTSTRAP_RC; evaluating checkpoints + canonical history."

docker exec -i "$CONTAINER" python - \
  "$DAY" "$SOURCE_DB" "$HISTORY_DB" "$MARKET_DB" "$REPAIR_SYMBOLS" <<'PY'
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.daily_finalize import canonical_day_completeness, rest_repair_status

DAY, SOURCE_DB, HISTORY_DB, MARKET_DB, RAW_TARGETS = sys.argv[1:6]
TARGETS = tuple(sorted({item for item in RAW_TARGETS.split(",") if item}))
VN = ZoneInfo("Asia/Ho_Chi_Minh")

hist = sqlite3.connect(HISTORY_DB)
hist.row_factory = sqlite3.Row

placeholders = ",".join("?" for _ in TARGETS)

# NoDataFound remains explicit and is scoped to this bounded repair set.
hist.execute(
    f"""
    UPDATE historical_bootstrap_checkpoints
    SET status='NO_DATA', row_count=0,
        completed_at=COALESCE(completed_at, last_attempt_at)
    WHERE from_date=? AND to_date=? AND resolution=1
      AND status='FAILED'
      AND error LIKE '%NoDataFound%'
      AND symbol IN ({placeholders})
    """,
    (DAY, DAY, *TARGETS),
)
hist.commit()

status_counts = {
    str(r["status"]): int(r["n"])
    for r in hist.execute(
        f"""
        SELECT status, COUNT(*) n
        FROM historical_bootstrap_checkpoints
        WHERE from_date=? AND to_date=? AND resolution=1
          AND symbol IN ({placeholders})
        GROUP BY status
        """,
        (DAY, DAY, *TARGETS),
    )
}
checkpoint_total = sum(status_counts.values())
bad_checkpoints = sum(
    n for status, n in status_counts.items()
    if status not in {"COMPLETED", "NO_DATA"}
)
checkpoints_complete = bad_checkpoints == 0 and checkpoint_total == len(TARGETS)

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
if bad_checkpoints:
    reasons.append(f"repair_bad_checkpoints={bad_checkpoints}")
if checkpoint_total != len(TARGETS):
    reasons.append(f"repair_checkpoints={checkpoint_total}!=targets={len(TARGETS)}")

proof = canonical_day_completeness(
    source_path=SOURCE_DB,
    history_path=HISTORY_DB,
    market_path=MARKET_DB,
    trading_date=DAY,
)
for field in (
    "missing_daily_bars",
    "missing_history",
    "unsafe_daily_bars",
    "unsafe_history",
    "volume_mismatches",
    "unfinalized_stream",
    "unsafe_stream_source",
):
    values = getattr(proof, field)
    if values:
        reasons.append(f"{field}={','.join(values)}")
now = datetime.now(VN).isoformat()

existing = hist.execute(
    "SELECT status, details_json FROM daily_finalize_runs WHERE trading_date=?", (DAY,)
).fetchone()
try:
    details = json.loads(str(existing["details_json"])) if existing else []
except (TypeError, ValueError):
    details = []
if not isinstance(details, list):
    details = []
details = [
    item for item in details
    if not (isinstance(item, dict) and item.get("kind") == "REST_REPAIR")
]
prior_status = str(existing["status"] or "") if existing else ""
status = rest_repair_status(
    prior_status=prior_status,
    checkpoints_complete=checkpoints_complete,
    canonical_complete=proof.complete,
)
details.append({
    "kind": "REST_REPAIR",
    "status": status,
    "repair_symbols": TARGETS,
    "reasons": reasons,
    "checkpoint_status": status_counts,
    "checkpoint_total": checkpoint_total,
    "canonical_completeness": asdict(proof),
})

columns = {
    str(row["name"])
    for row in hist.execute("PRAGMA table_info(daily_finalize_runs)")
}
updates = {
    "status": status,
    "details_json": json.dumps(details, sort_keys=True),
    "finalized_at": now,
}
legacy_updates = {
    "inserted_rows": int(r["rows"]),
    "history_rows": int(r["rows"]),
    "symbols": int(r["symbols"]),
    "minutes": int(r["minutes"]),
    "partial_rows": int(r["partial_rows"]),
    "gap_rows": int(r["gap_rows"]),
    "invalid_ohlc_rows": int(r["invalid_ohlc_rows"]),
    "quality_json": json.dumps(quality_counts, sort_keys=True),
}
updates.update({key: value for key, value in legacy_updates.items() if key in columns})
assignments = ", ".join(f"{key}=?" for key in updates)
hist.execute(
    f"UPDATE daily_finalize_runs SET {assignments} WHERE trading_date=?",
    (*updates.values(), DAY),
)
hist.commit()

print(json.dumps({
    "trading_date": DAY,
    "status": status,
    "rows": int(r["rows"]),
    "symbols": int(r["symbols"]),
    "minutes": int(r["minutes"]),
    "first_minute": r["first_minute"],
    "last_minute": r["last_minute"],
    "invalid_ohlc_rows": int(r["invalid_ohlc_rows"]),
    "negative_volume_rows": int(r["negative_volume_rows"]),
    "checkpoint_status": status_counts,
    "checkpoint_total": checkpoint_total,
    "repair_symbols": TARGETS,
    "canonical_completeness": asdict(proof),
    "reasons": reasons,
}, ensure_ascii=False))

hist.close()
raise SystemExit(0 if status == "REST_PASS" else 2)
PY
