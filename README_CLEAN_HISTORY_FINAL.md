# CCC Clean Daily History – Final Cutover Test

Branch đang dùng: `feature/daily-history-canonical-store`

Mục tiêu của patch này là chấm dứt chuỗi Phase B.x và quay về đúng một roadmap:

1. Làm sạch `daily_history` cho 800 mã bằng lịch sử provider đã được kiểm chứng với Daily Baseline production hiện tại.
2. Mỗi mã giữ tối đa 250 daily bars sạch làm seed.
3. Các row cũ không nằm trong seed đã kiểm chứng sẽ bị loại khỏi `daily_history` **sau khi seed mới đã upsert + verify đầy đủ**.
4. Append phiên 26/08/2026:
   - ưu tiên final intraday snapshot >=15:00 khi `price > 0` và `volume > 0`;
   - snapshot zero/missing thì gọi provider để xác nhận có daily bar 26/08 hay không;
   - chỉ append provider bar khi provider thực sự trả đúng ngày 26/08;
   - nếu provider trả lời thành công nhưng không có bar 26/08 thì `NO_BAR`, không bịa một phiên giao dịch.
5. Tính shadow baseline cho 27/08/2026.
6. Sau Daily Baseline cũ lúc 01:00 ngày 27/08, chạy mode `compare` để đối chiếu từng mã.

## Vì sao có 2 shadow baseline?

### `shadow_baseline_legacy`

Dùng đúng cửa sổ **500 calendar days** như Daily Baseline hiện tại.

Đây là bộ dùng để đối chiếu sáng 27/08. Nếu ingestion/history mới đúng, các trường sau phải khớp production cũ:

- trading_date
- previous_close
- MA10 + sessions
- MA200 + sessions
- KLTB10 + sessions

### `shadow_baseline_full`

Dùng toàn bộ clean store (tối đa 250 seed + EOD).

Bộ này để nhìn trước kiến trúc tương lai. Với các mã thanh khoản thưa, nó có thể có đủ 200 phiên trong khi Daily Baseline cũ 500-day chỉ nhìn thấy ít hơn 200. Khác biệt kiểu này là **expected improvement**, không phải lỗi ingestion.

Lần cutover đầu tiên nên dùng **legacy-compatible calculation** để tránh thay đổi tín hiệu ngoài ý muốn. Sau khi ổn định mới quyết định bật full-history MA cho mã thưa.

## Safety

- Trong 08:20–15:10 ngày giao dịch: không finalize.
- `write=true` bắt buộc confirm `FINALIZE`.
- Provider seed phải tái tạo EXACT Daily Baseline production hiện tại.
- Dùng chính source production trước (KBS hoặc VCI), fallback chỉ được dùng nếu cũng tái tạo EXACT.
- Không DELETE extra trước khi target seed đã upsert và verify đủ.
- Nếu DELETE fail, target sạch vẫn còn; chỉ có extra chưa xóa.
- EOD invalid không tự suy diễn thành bar.
- Nếu cả hai provider EOD đều lỗi kỹ thuật, symbol bị ERROR; không tự coi là `NO_BAR`.
- `latest_daily_baseline` production không bị sửa.

## Workflow inputs

### Tối 26/08 – dry-run

- operation: `finalize`
- symbols: để trống
- write: `false`
- confirm: để trống
- eod_date: `2026-08-26`
- max_symbols: `0`
- resume_after: để trống

### Sau khi dry-run sạch – write

- operation: `finalize`
- symbols: để trống
- write: `true`
- confirm: `FINALIZE`
- eod_date: `2026-08-26`
- max_symbols: `0`
- resume_after: để trống

### Sau Daily Baseline cũ 01:00 ngày 27/08

- operation: `compare`
- symbols: để trống
- write: `false`
- compare_run_date: `2026-08-27`

Mode compare hoàn toàn read-only và tính local baseline trực tiếp từ `daily_history`.

## Tiêu chí cutover

Chỉ chuyển scanner sang baseline local nếu mode `compare` đạt:

- exact = 800
- mismatch = 0
- missing_production = 0
- local_error = 0
- production_not_ok = 0

Nếu production cũ tự có mã `STALE`, không kết luận history mới sai; phải audit mã đó trước khi cutover.
