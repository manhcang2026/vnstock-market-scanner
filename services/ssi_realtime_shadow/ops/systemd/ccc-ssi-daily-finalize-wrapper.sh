#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${CCC_SSI_CONTAINER:-ccc-ssi-shadow}"
DAY="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

container_env() {
  local name="$1"
  local value
  value="$(docker exec "$CONTAINER" printenv "$name" 2>/dev/null || true)"
  if [[ -z "$value" ]]; then
    log "Missing required container environment: $name"
    exit 2
  fi
  printf '%s' "$value"
}

# The running service configuration is the only path source.  Clean-epoch
# suffixes are operational choices and must never be baked into this wrapper.
HOT_DB="$(container_env DATABASE_PATH)"
MARKET_DB="$(container_env MARKET_V2_DATABASE_PATH)"
HISTORY_DB="$(container_env SSI_HISTORY_PATH)"
BASELINE_DB="$(container_env VOLUME_BASELINE_PATH)"
REST_STAGE_DB="$(container_env SSI_EOD_STAGING_PATH)"
DAILY_JSON="$(container_env SSI_EOD_DAILY_JSON_PATH)"

EOD_PATH_NAMES=(
  DATABASE_PATH
  MARKET_V2_DATABASE_PATH
  SSI_HISTORY_PATH
  VOLUME_BASELINE_PATH
  SSI_EOD_STAGING_PATH
  SSI_EOD_DAILY_JSON_PATH
)
EOD_PATH_VALUES=(
  "$HOT_DB"
  "$MARKET_DB"
  "$HISTORY_DB"
  "$BASELINE_DB"
  "$REST_STAGE_DB"
  "$DAILY_JSON"
)
for ((i = 0; i < ${#EOD_PATH_VALUES[@]}; i++)); do
  path="${EOD_PATH_VALUES[$i]}"
  if [[ "$path" != /* ]]; then
    log "${EOD_PATH_NAMES[$i]} must be absolute inside the container: $path"
    exit 2
  fi
  for ((j = 0; j < i; j++)); do
    if [[ "$path" == "${EOD_PATH_VALUES[$j]}" ]]; then
      log "EOD paths must be distinct: ${EOD_PATH_NAMES[$j]} and ${EOD_PATH_NAMES[$i]} both resolve to $path"
      exit 2
    fi
  done
done

log "REST-canonical EOD start day=$DAY hot=$HOT_DB market=$MARKET_DB history=$HISTORY_DB baseline=$BASELINE_DB staging=$REST_STAGE_DB"

SYMBOLS="$(docker exec -i "$CONTAINER" python - <<'EOD_UNIVERSE_PY'
from app.settings import Settings
from app.universe import load_universe

settings = Settings.from_env()
symbols = sorted(load_universe(settings))
if not symbols:
    raise SystemExit(2)
print(",".join(symbols))
EOD_UNIVERSE_PY
)"

CLI_DATE="$(date -d "$DAY" '+%d/%m/%Y')"
log "Fetching paced/resumable SSI REST IntradayOhlc"
docker exec \
  -e DATABASE_PATH="$REST_STAGE_DB" \
  "$CONTAINER" \
  python -m app.historical_bootstrap \
    --from-date "$CLI_DATE" \
    --to-date "$CLI_DATE" \
    --symbols "$SYMBOLS" \
    --request-interval 1 \
    --max-retries 5 \
    --max-consecutive-rate-limits 8

log "Fetching paced/resumable SSI DailyOhlc"
docker exec -i "$CONTAINER" python - "$DAY" "$REST_STAGE_DB" "$DAILY_JSON" "$SYMBOLS" <<'EOD_DAILY_PY'
import json
import sqlite3
import sys
from datetime import date, timedelta

from app.daily_history import normalize_daily_ohlc_record
from app.settings import Settings
from app.ssi_historical import SSIHistoricalClient, SSINoDataFound


def ensure_daily_checkpoint_schema(con):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS eod_daily_checkpoints (
            symbol TEXT NOT NULL,
            trading_date TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT,
            error TEXT,
            PRIMARY KEY(symbol, trading_date)
        )
        """
    )
    con.commit()


def upsert_daily_checkpoint(con, symbol, day, status, payload=None, error=None):
    con.execute(
        """
        INSERT INTO eod_daily_checkpoints VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, trading_date) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            error=excluded.error
        """,
        (symbol, day, status, payload, error),
    )
    con.commit()


def fetch_daily_checkpoint(con, client, symbol, day, target):
    row = con.execute(
        "SELECT status FROM eod_daily_checkpoints WHERE symbol=? AND trading_date=?",
        (symbol, day),
    ).fetchone()
    if row and row[0] in {"COMPLETED", "NO_DATA"}:
        return row[0]
    try:
        matches = []
        for item in client.fetch_daily_ohlc(symbol, target, target):
            raw_day = str(
                item.get("TradingDate")
                or item.get("tradingDate")
                or item.get("trading_date")
                or ""
            )
            if raw_day in {day, target.strftime("%d/%m/%Y"), target.strftime("%Y%m%d")}:
                matches.append(item)
        if not matches:
            intraday = con.execute(
                """
                SELECT status, row_count
                FROM historical_bootstrap_checkpoints
                WHERE symbol=? AND from_date=? AND to_date=? AND resolution=1
                """,
                (symbol, day, day),
            ).fetchone()
            if intraday == ("NO_DATA", 0):
                diagnostic = "EMPTY_RESPONSE_CONFIRMED_BY_INTRADAY_NO_DATA"
                upsert_daily_checkpoint(
                    con, symbol, day, "NO_DATA", error=diagnostic
                )
                return "NO_DATA"
            raise RuntimeError(
                "EMPTY_OR_AMBIGUOUS_RESPONSE: expected one DailyOhlc row, "
                "received 0 without explicit NoDataFound or confirming "
                "Intraday NO_DATA"
            )
        if len(matches) != 1:
            raise RuntimeError(
                "EMPTY_OR_AMBIGUOUS_RESPONSE: expected one DailyOhlc row, "
                f"received {len(matches)} without explicit NoDataFound"
            )
        upsert_daily_checkpoint(
            con,
            symbol,
            day,
            "COMPLETED",
            json.dumps(matches[0], separators=(",", ":")),
        )
        return "COMPLETED"
    except SSINoDataFound as exc:
        upsert_daily_checkpoint(
            con, symbol, day, "NO_DATA", error=f"SSINoDataFound: {exc}"
        )
        return "NO_DATA"
    except Exception as exc:
        upsert_daily_checkpoint(
            con, symbol, day, "FAILED", error=f"{type(exc).__name__}: {exc}"
        )
        raise


def validated_daily_payloads(con, symbols, day, target):
    intraday = {
        row[0]: (row[1], int(row[2]))
        for row in con.execute(
            """
            SELECT symbol, status, row_count
            FROM historical_bootstrap_checkpoints
            WHERE from_date=? AND to_date=? AND resolution=1
            """,
            (day, day),
        )
    }
    daily = {
        row[0]: (row[1], row[2])
        for row in con.execute(
            """
            SELECT symbol, status, payload_json FROM eod_daily_checkpoints
            WHERE trading_date=?
            """,
            (day,),
        )
    }
    minute_counts = {
        row[0]: int(row[1])
        for row in con.execute(
            """
            SELECT symbol, COUNT(*)
            FROM minute_bars WHERE trading_date=? GROUP BY symbol
            """,
            (day,),
        )
    }
    payloads = []
    for symbol in symbols:
        intraday_state = intraday.get(symbol)
        daily_state = daily.get(symbol)
        if intraday_state is None or daily_state is None:
            raise RuntimeError(f"INCOMPLETE_CHECKPOINT_PAIR:{symbol}")
        intraday_status, checkpoint_rows = intraday_state
        daily_status, payload_json = daily_state
        if intraday_status not in {"COMPLETED", "NO_DATA"}:
            raise RuntimeError(f"INTRADAY_CHECKPOINT_{intraday_status}:{symbol}")
        if daily_status not in {"COMPLETED", "NO_DATA"}:
            raise RuntimeError(f"DAILY_CHECKPOINT_{daily_status}:{symbol}")
        minute_count = minute_counts.get(symbol, 0)
        if intraday_status == "COMPLETED":
            if checkpoint_rows <= 0 or minute_count <= 0:
                raise RuntimeError(f"INTRADAY_COMPLETED_WITHOUT_ROWS:{symbol}")
            if checkpoint_rows != minute_count:
                raise RuntimeError(
                    f"INTRADAY_ROW_COUNT_MISMATCH:{symbol}:"
                    f"checkpoint={checkpoint_rows}:staged={minute_count}"
                )
        elif checkpoint_rows != 0 or minute_count != 0:
            raise RuntimeError(f"INTRADAY_NO_DATA_WITH_ROWS:{symbol}")

        daily_bar = None
        if daily_status == "COMPLETED":
            if not payload_json:
                raise RuntimeError(f"DAILY_COMPLETED_WITHOUT_PAYLOAD:{symbol}")
            payload = json.loads(payload_json)
            daily_bar = normalize_daily_ohlc_record(
                payload, as_of_date=target + timedelta(days=1)
            )
            if (
                daily_bar is None
                or daily_bar.symbol != symbol
                or daily_bar.trading_date != day
            ):
                raise RuntimeError(f"INVALID_DAILY_PAYLOAD:{symbol}")
        elif payload_json is not None:
            raise RuntimeError(f"DAILY_NO_DATA_WITH_PAYLOAD:{symbol}")

        pair = (intraday_status, daily_status)
        if pair == ("COMPLETED", "COMPLETED"):
            payloads.append(payload)
        elif pair == ("NO_DATA", "COMPLETED"):
            if daily_bar.volume != 0:
                raise RuntimeError(f"NO_DATA_NONZERO_DAILY:{symbol}")
            payloads.append(payload)
        elif pair == ("NO_DATA", "NO_DATA"):
            continue
        else:
            raise RuntimeError(f"INCONSISTENT_CHECKPOINT_PAIR:{symbol}:{pair}")
    return payloads


def main():
    day, staging_path, output_path, raw_symbols = sys.argv[1:5]
    symbols = tuple(item for item in raw_symbols.split(",") if item)
    settings = Settings.from_env()
    client = SSIHistoricalClient(
        base_url=settings.ssi_url,
        consumer_id=settings.ssi_consumer_id,
        consumer_secret=settings.ssi_consumer_secret,
        auth_type=settings.ssi_auth_type,
        request_interval=1,
        max_attempts=6,
        initial_retry_delay=2,
        max_retry_delay=120,
        retry_jitter_ratio=0.25,
        max_consecutive_rate_limits=8,
    )
    con = sqlite3.connect(staging_path)
    try:
        ensure_daily_checkpoint_schema(con)
        target = date.fromisoformat(day)
        for symbol in symbols:
            fetch_daily_checkpoint(con, client, symbol, day, target)
        payloads = validated_daily_payloads(con, symbols, day, target)
    finally:
        con.close()
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump({"dataList": payloads}, handle)


if __name__ == "__main__":
    main()
EOD_DAILY_PY

log "Validating REST IntradayOhlc and SSI DailyOhlc independently"
docker exec "$CONTAINER" python -m app.daily_finalize \
  --source "$REST_STAGE_DB" \
  --auction-source "$HOT_DB" \
  --history "$HISTORY_DB" \
  --market "$MARKET_DB" \
  --daily-json "$DAILY_JSON" \
  --date "$DAY" \
  --write

log "EOD PASS; rebuilding baseline for the next proven trading session"
docker exec "$CONTAINER" python -m app.volume_baseline_build \
  --history-db "$HISTORY_DB" \
  --daily-db "$MARKET_DB" \
  --output-db "$BASELINE_DB" \
  --next-session-after "$DAY" \
  --lookback 10

log "REST-canonical EOD and next-session baseline completed"
