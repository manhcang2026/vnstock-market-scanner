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

## Bootstrap lịch sử 1 phút

Có thể nạp OHLC 1 phút từ SSI FastConnect Data vào cùng SQLite local. Lệnh có
checkpoint theo symbol và chỉ thêm phút chưa tồn tại; không sửa hoặc cộng dồn lại
bar realtime đã có.

```bat
python -m app.historical_bootstrap --from-date 01/09/2026 --to-date 11/09/2026 --symbols HPG,SSI,VIX
```

Bỏ `--symbols` để dùng scanner universe hiện tại; có thể thêm
`--limit-symbols 10` khi kiểm thử phạm vi nhỏ. Credential tiếp tục lấy từ `.env`.

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

- `ssi_shadow.db`: hot SSI quote/minute transport;
- `ccc_market_YYYY.db`: canonical market history and current market facts;
- `ccc_engine.db`: canonical baselines, current state, and signals;
- `ccc-canonical-eod` and `ccc-canonical-premarket`: canonical maintenance.

Retired production paths:

- CCC V2 volume shadow and `LiveStateRuntime`;
- the `ccc_market_v2.db.stock_state_current` writer;
- the `ccc_v2_baseline.db` runtime dependency;
- `ccc-ssi-daily-finalize`, whose retained wrapper is a safe no-op.

The legacy modules remain in the repository only for offline/history tests until
`LEGACY-CLEANUP-01`. Setting `VOLUME_ENGINE_ENABLED=true` or
`LIVE_STATE_ENABLED=true` now makes collector startup fail closed with
`LEGACY_V2_RUNTIME_RETIRED`.

`ssi_history_2026.db` remains temporarily used only by `/v1/chart`. The chart,
quote, and live WebSocket transports are intentionally unchanged in this case.
