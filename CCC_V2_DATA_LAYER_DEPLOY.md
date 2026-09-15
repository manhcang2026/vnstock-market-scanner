# CCC V2 data layer overlay

Target branch: `feat/ssi-realtime-shadow`

This overlay adds:

- `app/daily_finalize.py`: hard QA gate + idempotent daily promotion from `ssi_shadow.db` to `ssi_history_2026.db`.
- `app/chart_data.py`: one seamless read model across history + current realtime.
- `app/chart_api.py`: local-only HTTP Chart Data API.
- `ops/systemd/ccc-ssi-daily-finalize.service` + `.timer`: automatic finalize at 15:35 VN, Mon-Fri.
- deterministic tests for finalization, history/realtime precedence, invalid OHLC filtering, and 5m aggregation.
- `docker-compose.yml`: adds local-only `ccc-chart-api` bound to `127.0.0.1:8787`.

## Safety decisions

- Collector ingest is not rewritten.
- Historical DB remains canonical after finalization.
- Current realtime fills dates/minutes not yet promoted.
- History wins if both DBs contain the same `(trading_date, minute, symbol)`.
- Invalid historical OHLC rows are kept raw in SQLite but dropped from chart responses by default.
- `include_invalid=1` exposes them with `quality_status=INVALID_OHLC`.
- Daily finalize is BLOCKED on hard QA problems: missing coverage, late session missing, gaps, invalid realtime OHLC, or negative volume.
- `PARTIAL` and `VOLUME_REGRESSION` are reported but do not automatically block promotion.
- No automatic deletion/pruning is included in this first deployment.

## Local test

From `services/ssi_realtime_shadow`:

```bash
pytest -q
```

The overlay's isolated tests passed: `6 passed`.

## VPS deployment

Deploy outside market hours.

```bash
cd /path/to/repo/services/ssi_realtime_shadow
git pull

docker compose build collector
docker compose up -d collector chart-api
docker ps --filter name=ccc-ssi-shadow --filter name=ccc-chart-api
```

Dry-run today's completed session first:

```bash
docker exec ccc-ssi-shadow \
  python -m app.daily_finalize \
  --source /app/data/ssi_shadow.db \
  --history /app/data/ssi_history_2026.db \
  --date 2026-09-15 \
  --dry-run
```

If status is `DRY_RUN_PASS`, promote it:

```bash
docker exec ccc-ssi-shadow \
  python -m app.daily_finalize \
  --source /app/data/ssi_shadow.db \
  --history /app/data/ssi_history_2026.db \
  --date 2026-09-15
```

Test API:

```bash
curl -s http://127.0.0.1:8787/health
curl -s "http://127.0.0.1:8787/v1/chart/HPG?from=2026-09-14&to=2026-09-15&resolution=5"
```

Install timer:

```bash
sudo cp ops/systemd/ccc-ssi-daily-finalize.service /etc/systemd/system/
sudo cp ops/systemd/ccc-ssi-daily-finalize.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ccc-ssi-daily-finalize.timer

systemctl status ccc-ssi-daily-finalize.timer --no-pager
systemctl list-timers --all | grep ccc-ssi
```

The timer runs at `15:35 Asia/Ho_Chi_Minh` Monday-Friday. On a QA failure, the service exits non-zero and the day is not promoted.

Inspect last result:

```bash
sudo journalctl -u ccc-ssi-daily-finalize.service -n 100 --no-pager
```

## API contract

Health:

```text
GET /health
```

Chart:

```text
GET /v1/chart/{symbol}?from=YYYY-MM-DD&to=YYYY-MM-DD&resolution=1
```

Allowed resolutions: `1, 5, 15, 30, 60`.

Optional:

```text
include_invalid=1
```

Default is to omit bars that violate OHLC invariants.

The API is intentionally bound to `127.0.0.1:8787` on the VPS. Do not expose it directly to the Internet; put it behind the CCC backend/reverse proxy and auth/entitlement layer later.
