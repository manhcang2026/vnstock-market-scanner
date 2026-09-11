# CCC — SSI Realtime Shadow Plan

## Mục tiêu

Chuyển nguồn intraday của CCC từ pipeline polling cũ sang SSI FCData streaming mà không làm gián đoạn website production.

## Kiến trúc giai đoạn shadow

```text
SSI FCData X:ALL
      |
      v
ssi_realtime_shadow
  - filter ~800 symbol
  - latest quote state
  - aggregate OHLCV 1 minute
      |
      v
SQLite local / server disk
```

Website production vẫn đọc Supabase như hiện tại. Shadow collector **không ghi đè production**.

## Vì sao SQLite ở giai đoạn đầu

- 1 process ghi duy nhất, phù hợp workload collector.
- nhẹ hơn PostgreSQL khi cần chạy tạm trên PC/E2 Micro.
- file đơn dễ backup/copy sang Oracle/VPS.
- đủ cho 10–20 phiên validation.
- sau cutover có thể migrate historical 1m sang PostgreSQL/Timescale hoặc storage khác mà không đổi SSI ingest logic.

## Dữ liệu 1 phút

Khóa chính:

```text
(trading_date, minute, symbol)
```

Trường chính:

```text
open high low close
volume
last_total_volume
event_count
is_partial
```

`volume` được tính bằng delta `TotalVol`; `last_total_volume` giữ cumulative volume của SSI để kiểm tra và phục hồi sau reconnect.

## RVOL30 sau khi đủ dữ liệu

Tại thời điểm T:

```text
volume_30m(T) = tổng volume của 30 bucket phút gần nhất
rvol30(T) = volume_30m(T) / avg(volume_30m cùng cửa sổ thời gian của N phiên trước)
```

Trong giai đoạn tích lũy, hiển thị coverage N/10. Chỉ khi đủ 10 phiên mới là baseline hoàn chỉnh.

## Validation tối thiểu mỗi phiên

1. Universe coverage gần 800 mã.
2. Không có gap phút diện rộng trong thời gian thị trường giao dịch.
3. `TotalVol` cuối phiên hợp lý khi so với nguồn/pipeline cũ.
4. Giá close/latest hợp lý khi so với nguồn/pipeline cũ.
5. Reconnect không tạo volume âm hoặc double count.
6. File DB tăng trưởng trong mức dự kiến.
7. Collector không ghi secret ra log.

## Lộ trình cutover

### Phiên 1–10

- Old pipeline: primary production, read/write như hiện tại.
- SSI collector: shadow only.
- Tích lũy minute bars + đối chiếu.

### Phiên 11–20

Nếu validation đạt:

- SSI trở thành primary data engine.
- Pipeline cũ giữ ở chế độ reference/manual fallback.
- Bắt đầu writer có kiểm soát sang Supabase và/hoặc API nội bộ.

### Sau ổn định

- thêm CCC WebSocket server;
- chart realtime đọc history ban đầu + live stream từ CCC server;
- archive/prune historical raw cũ theo retention policy;
- GitHub Intraday Scan giữ manual emergency fallback.

## Nguyên tắc deployment

- Không phụ thuộc Oracle-specific service.
- Code + config nằm trong repo.
- Secret chỉ ở `.env` trên host.
- Docker image portable.
- Data nằm trên volume/path host để backup và migrate độc lập.
