# SSI Realtime Shadow Collector

Service này thu dữ liệu SSI FCData `X:ALL` song song với pipeline hiện tại và **không ghi đè production `stock_snapshot`** trong giai đoạn shadow.

## Nguyên tắc

- SSI FCData là nguồn realtime mới.
- Chỉ giữ các mã thuộc scanner universe CCC (~800 mã).
- Lưu dữ liệu 1 phút vào SQLite local để nhẹ, portable và không làm đầy Supabase Free.
- Pipeline cũ vẫn chạy bình thường trong ít nhất 10 phiên đối chiếu.
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

## Shadow mode

Phiên bản này **chưa ghi production Supabase**. Mục tiêu đầu tiên là kiểm chứng:

- coverage universe;
- continuity theo phút;
- reconnect;
- giá/volume so với pipeline cũ;
- dữ liệu đủ để xây RVOL30 chuẩn 10 phiên.

Sau khi đạt tiêu chí cutover, service mới mở rộng API/WebSocket và writer sang bảng production/shadow phù hợp.
