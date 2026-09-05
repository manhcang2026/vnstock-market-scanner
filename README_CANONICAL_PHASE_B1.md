# Canonical Daily History – Phase B.1 Bulk-Safe

Branch dự kiến: `feature/daily-history-canonical-store`

Patch này **không thay đổi main** và tiếp tục dùng `Daily History Repair` làm
temporary harness trên feature branch.

## Mục tiêu

Sau khi Phase B đã write + verify thành công 6 mã mẫu, B.1 thêm lớp bulk-safe:

- chạy danh sách lớn theo chunk;
- checkpoint/report sau **mỗi symbol**;
- resume bằng `resume_after`;
- skip provider cho mã đã canonical local rõ ràng;
- vẫn chỉ canonicalize nhóm `ma200_sessions >= 200`;
- vẫn chỉ dùng KBS trên provider path;
- vẫn yêu cầu KBS tái tạo EXACT Daily Baseline;
- write giữ đúng thứ tự an toàn đã test ở Phase B.

## Inputs

### `symbols`

- Để trống: bulk mode trên toàn bộ watchlist đủ >=200 phiên.
- Có giá trị: chỉ chạy danh sách cụ thể.

### `write`

- `false`: dry-run, mặc định.
- `true`: cho phép reconcile thật.

### `confirm`

- Nếu `symbols` có danh sách cụ thể và `write=true`: nhập `WRITE`.
- Nếu `symbols` để trống (bulk) và `write=true`: nhập `WRITE-BULK`.

### `resume_after`

Bulk mode chạy theo alphabet.

Ví dụ report trước ghi:

`last_processed_symbol = HPG`

thì lượt sau nhập:

`resume_after = HPG`

Script sẽ bắt đầu từ mã kế tiếp.

### `max_symbols`

- Khuyến nghị: `100`.
- `0`: không giới hạn.
- Dùng chunk 100 để giảm rủi ro timeout/provider interruption.

### `force_provider_check`

- `false` (mặc định): mã nào 250 row local KBS + MA10/MA200/KLTB10/close đều
  EXACT Daily Baseline sẽ được skip, không gọi KBS lại.
- `true`: bắt buộc gọi KBS lại kể cả mã local đã canonical.

## Checkpoint / report

Sau mỗi symbol script ghi lại:

- `canonical_bulk_report.json`
- `canonical_bulk_report.csv`

Workflow upload hai file này thành artifact kể cả khi step chính lỗi.

Các field quan trọng:

- `last_processed_symbol`
- `local_canonical_skip`
- `provider_checked`
- `candidate_ready`
- `written`
- `errors`
- danh sách error symbol

Nếu workflow bị ngắt sau một chunk, lấy `last_processed_symbol` để resume.

## Safety rules

1. Không chạy trong 08:20–15:10 ngày giao dịch.
2. Không canonicalize nhóm `<200 phiên`.
3. Provider path chỉ dùng KBS, không fallback VCI.
4. KBS phải EXACT Daily Baseline production.
5. Write explicit cần `WRITE`; write bulk cần `WRITE-BULK`.
6. Upsert canonical trước.
7. Verify target đủ + đúng trước khi DELETE.
8. Chỉ DELETE extra date nằm **bên trong canonical window**.
9. Row cũ hơn/mới hơn canonical window giữ nguyên.
10. Final verify sau mỗi symbol.
11. Một symbol lỗi không làm mất kết quả của symbol đã verify trước đó; lỗi được ghi report.

## Lượt chạy nên làm sau khi push patch

**Chỉ dry-run trước.**

- Branch: `feature/daily-history-canonical-store`
- symbols: để trống
- write: false
- confirm: để trống
- resume_after: để trống
- max_symbols: `100`
- force_provider_check: false

Sau khi run xong, kiểm tra log + artifact/report rồi mới chạy chunk tiếp theo.

## Trước khi merge main

Không merge nguyên `daily-history-repair.yml` temporary harness này vào main.

Khi canonical store được chốt production:
- khôi phục `Daily History Repair` gốc;
- tạo workflow canonical riêng;
- tích hợp daily-history append/reconcile vào luồng Daily Baseline/EOD theo kiến trúc cuối.
