# SSI Realtime Canonical Collector

Thư mục có tên lịch sử `ssi_realtime_shadow`, nhưng đây là collector production
canonical của CCC V3. Runtime lưu hot transport vào `ssi_shadow.db`, canonical
market truth vào `ccc_market_YYYY.db`, và derived intelligence vào
`ccc_engine.db`.

## Nguyên tắc

- SSI FCData là nguồn realtime mới.
- Chỉ giữ các mã thuộc scanner universe CCC (~800 mã).
- Lưu dữ liệu 1 phút vào SQLite local để nhẹ, portable và không làm đầy Supabase Free.
- Canonical market persistence luôn xảy ra trước derived calculation.
- Không commit `consumerID`, `consumerSecret`, Supabase service-role key hoặc SSI SDK archive vào Git.

## Chạy trực tiếp trên Windows khi chờ Oracle

Yêu cầu: Python 3.11 và gói SSI FCData chính thức đã tải từ SSI.

```bat
cd services\ssi_realtime_shadow
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install C:\DUONG_DAN\ssi_fc_data-2.2.2.tar.gz
copy .env.example .env
```

Mở `.env` và điền credential **trên máy của bạn**, sau đó:

```bat
python -m app.main
```

Xem nhanh dữ liệu đã thu:

```bat
python -m app.status
```

## Historical recovery

`app.clean_rest_bootstrap` is the canonical bounded historical/backfill tool.
It fetches arbitrary minute or daily date ranges from SSI REST and writes them
directly into the matching `ccc_market_YYYY.db` shard. For example, in
PowerShell:

```powershell
python -m app.clean_rest_bootstrap --mode minute `
  --from-date 2026-09-01 --to-date 2026-09-11 `
  --symbols HPG,SSI,VIX --db-dir /app/data --retry-failed --verbose

python -m app.clean_rest_bootstrap --mode daily `
  --from-date 2026-09-01 --to-date 2026-09-11 `
  --symbols HPG,SSI,VIX --db-dir /app/data --retry-failed --verbose
```

When running directly on Windows outside the container, replace `/app/data`
with the local canonical data directory. The date range is inclusive and may
span years; the tool routes each result to its year shard.

`app.canonical_eod` has a different purpose. It performs post-close
reconciliation/finalization for one specific trading day. It is not the general
replacement for missing historical days, especially when the selected day has
no canonical live evidence.

The removed `app.historical_bootstrap` wrote to the old hot-history storage and
must not be reintroduced. Any retained `historical_bootstrap_checkpoints` schema
or import references are legacy compatibility metadata, not an active bootstrap
runtime.

## Chạy bằng Docker sau khi có Oracle/VPS

SSI phát hành Python client dạng `.tar.gz`/`.whl`. Repository CCC là public nên archive SDK không được commit.

1. Copy file SSI SDK vào `vendor/`, ví dụ `vendor/ssi_fc_data-2.2.2.tar.gz`.
2. Copy `.env.example` thành `.env` và điền credential.
3. Chạy:

```bash
docker compose up -d --build
docker compose logs -f collector
```

Dữ liệu nằm tại `./data/ssi_shadow.db` và mount ra host, nên có thể copy sang A1/VPS khác mà không phụ thuộc Oracle.

## Universe

Collector ưu tiên `UNIVERSE_FILE` nếu file tồn tại và có dữ liệu. Nếu không, collector đọc danh sách symbol từ `stock_snapshot` qua Supabase REST bằng `SUPABASE_URL` + `SUPABASE_KEY`.

Collector dừng nếu universe nhỏ hơn `MIN_UNIVERSE_SIZE` (mặc định 700) để tránh vô tình thu sai phạm vi.

## Dữ liệu lưu

- `latest_quotes`: trạng thái gần nhất theo symbol.
- `minute_bars`: OHLC 1 phút + volume delta + cumulative volume.
- Không lưu toàn bộ raw message lâu dài.

Volume 1 phút được tính từ chênh lệch `TotalVol` giữa các event. Khi collector restart giữa phiên, nó dùng cumulative volume đã persist để tiếp tục, hạn chế mất volume do reconnect.

Dòng phút đầu tiên của mỗi symbol sau khi process khởi động được đánh dấu `is_partial=1`; dữ liệu này không nên dùng làm baseline tin cậy nếu collector khởi động giữa phút.

## Production runtime ownership

Active production paths:

- `ssi_shadow.db`: collector-owned hot/raw operational transport;
- `ccc_market_YYYY.db`: canonical market history and current market facts;
- `/v1/chart`, `/v1/quote`, and live WebSocket chart snapshots: read-only
  consumers of canonical `ccc_market_YYYY.db` shards;
- `ccc_engine.db`: canonical baselines, current state, and signals;
- `CanonicalStateReader` and state serializers: canonical frontend API contracts;
- `app.volume_event.VolumeEvent`: normalized collector event contract;
- shared `volume_baseline.py` grid and session-policy helpers;
- `ccc-canonical-eod` and `ccc-canonical-premarket`: canonical maintenance.

Retired production paths:

- CCC V2 volume shadow and `LiveStateRuntime`;
- the `ccc_market_v2.db.stock_state_current` writer;
- the `ccc_v2_baseline.db` runtime dependency;
- `ccc-ssi-daily-finalize`: service, timer, and wrapper removed from the repository;
  retired service names must not be installed.

LEGACY-CODE-CLEANUP-01A removes the V2 runtime, harness, stock-state builder,
readiness checker, daily finalizer, volume-baseline CLI, and hot-history bootstrap
CLI. Shared types/helpers and migration compatibility remain where still consumed.
No production collector path reads or writes V2 state/baseline databases.

LEGACY-CODE-CLEANUP-01B removes `RealtimeVolumeEngine`, its V2 `VolumeSnapshot`
and baseline loader, the `stock_state_current` projector/writer, and direct
legacy SQL readers from `state_contract.py`. The active `VolumeEvent` and its
validators moved unchanged to `app.volume_event`; canonical serializers and
their key ordering remain unchanged. Its historical `BaselineValidationError`
exception name is retained only to preserve date/minute validation semantics.

Old `stock_state_current` and `signal_events` schema/migration definitions in
`market_storage_schema.py` remain migration compatibility for existing offline
initializer/import consumers. They do not enable a V2 production runtime. This
cleanup does not remove or migrate any physical table or database.

`VOLUME_ENGINE_ENABLED` and `LIVE_STATE_ENABLED` are obsolete configuration.
Remove them from deployment environments. The small explicit startup guard is
retained to diagnose stale settings: true values fail closed with
`LEGACY_V2_RUNTIME_RETIRED`, invalid booleans are rejected, and false/absent values
are accepted. This guard cannot create a V2 runtime. Production startup requires
both `CANONICAL_ENGINE_ENABLED=true` and `CANONICAL_SIGNAL_ENABLED=true`.

CHART-API-CANONICAL-01B moves `/v1/chart`, `/v1/quote`, and live WebSocket chart
snapshots to read-only canonical year shards. Chart ranges open only the required
`ccc_market_YYYY.db` files; quote continuity checks only the current and previous
year. `CHART_HISTORY_PATH`, `CHART_REALTIME_PATH`, legacy `daily_finalize_runs`
chart authority, and request-time reads from `ssi_shadow.db` are removed.
`ssi_history_2026.db` remains a physical cleanup candidate after deployment
verification and must not be deleted by the code cutover. `ssi_shadow.db` remains
active collector operational storage through `DATABASE_PATH`.

The collector and canonical maintenance do not use `MARKET_V2_DATABASE_PATH`,
`VOLUME_BASELINE_PATH`, or `SSI_HISTORY_PATH`. `ccc_market_v2.db` and
`ccc_v2_baseline.db` are retired / do not use. Their physical files, and
`ssi_history_2026.db`, have NOT been deleted. Installed legacy systemd units
will be cleaned separately after patch audit/deployment; this patch performs
no production action. Keep the active `ccc-canonical-eod.*` and
`ccc-canonical-premarket.*` units.
