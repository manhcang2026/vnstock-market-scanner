# Phase A - Canonical Daily History Audit

Mục tiêu của patch này là **audit read-only** trước khi thay đổi production.

## Phạm vi

- Không sửa `main` nếu bạn làm đúng trên branch `feature/daily-history-canonical-store`.
- Không INSERT / UPDATE / DELETE Supabase.
- Không thay đổi Daily Baseline production.
- Không xử lý các mã có `ma200_sessions < 200` trong Phase A.
- Tận dụng chính logic provider của `backfill_daily_history.py` để tìm lịch sử KBS/VCI có thể tái tạo **EXACT** Daily Baseline hiện tại.
- So sánh 250 phiên candidate với `daily_history` đang có và chỉ in kết quả.

## Vì sao tạm sửa workflow Daily History Repair?

GitHub chỉ cho workflow_dispatch hoạt động ổn định khi workflow đã tồn tại trên default branch. `Daily History Repair` đã tồn tại trên `main`, nên ở feature branch ta tạm dùng chính workflow này làm "harness" để chạy audit branch mà không cần merge workflow mới vào main.

Trên **main**, workflow Repair vẫn không thay đổi.

## Cách áp dụng bằng GitHub Desktop

1. Từ `main`, tạo branch mới: `feature/daily-history-canonical-store`.
2. Giải nén ZIP này thẳng vào thư mục repo, cho phép ghi đè `.github/workflows/daily-history-repair.yml` **trên branch mới**.
3. GitHub Desktop phải hiện đúng 3 file thay đổi/thêm:
   - `.github/workflows/daily-history-repair.yml`
   - `src/canonical_history_audit.py`
   - `README_CANONICAL_AUDIT.md`
4. Commit gợi ý: `Add read-only canonical history audit`
5. Push branch lên GitHub.

## Chạy test đầu tiên

Vào GitHub Actions > **Daily History Repair** > Run workflow.

- Branch: `feature/daily-history-canonical-store`
- symbols: `TLP,VIT,CLC,VNC,MAC,PDN`
- write: **false**

Lưu ý: trên feature branch, patch hard-code `CANONICAL_WRITE=false`, nên audit không ghi Supabase kể cả khi chọn nhầm write=true. Tuy vậy vẫn nên để false.

Sau khi run xong, gửi link run cho ChatGPT để đọc log và chốt Phase B.

## Chưa merge branch này vào main

Đây là harness kiểm chứng. Sau khi log dry-run đạt yêu cầu, Phase B sẽ:

- khôi phục `Daily History Repair` về workflow repair chuẩn;
- thêm cơ chế canonical sync vào luồng phù hợp;
- vẫn tách riêng bài toán 40 mã `<200 phiên`.
