# Canonical Daily History – Phase B patch

Branch dự kiến: `feature/daily-history-canonical-store`

## Mục tiêu

Phase B cho phép **dry-run hoặc reconcile thật** `daily_history` về một chuỗi canonical KBS,
nhưng chỉ cho các mã mà Daily Baseline hiện có `ma200_sessions >= 200`.

Phase B **không xử lý nhóm <200 phiên**.

## An toàn

- Mặc định `write=false`.
- Nếu `write=true`, bắt buộc ô `confirm` phải nhập chính xác `WRITE`.
- Không chạy trong khung 08:20–15:10 ngày giao dịch.
- Chỉ dùng **KBS**, không fallback VCI.
- KBS phải tái tạo **EXACT** Daily Baseline production trước khi được xem là candidate.
- Khi ghi:
  1. Upsert toàn bộ canonical target trước.
  2. Verify target đã đủ và đúng source KBS.
  3. Chỉ xóa các **extra trading_date nằm bên trong canonical window**.
  4. Row cũ hơn hoặc mới hơn canonical window được giữ nguyên.
  5. Final verify lại toàn bộ target window.
- Không sửa `daily_history_sync_state`.
- Không sửa Daily Baseline / Intraday / production signal logic.

## File trong patch

- `.github/workflows/daily-history-repair.yml`
  - Temporary branch harness để chạy Phase B từ Actions mà chưa merge workflow mới vào main.
- `src/canonical_history_sync.py`
  - Logic dry-run/write Phase B.
- `README_CANONICAL_PHASE_B.md`

File `src/canonical_history_audit.py` của Phase A giữ nguyên trong branch.

## Dry-run khuyến nghị đầu tiên

Branch:
`feature/daily-history-canonical-store`

Symbols:
`TLP,VIT,CLC,VNC,MAC,PDN`

Write:
`false`

Confirm:
để trống.

Chỉ sau khi dry-run được kiểm tra log mới cân nhắc write=true.

## Write thử nghiệm sau khi được duyệt

Symbols:
nên vẫn chỉ dùng 6 mã mẫu trước.

Write:
`true`

Confirm:
`WRITE`

Không chạy toàn bộ 800 mã trong lượt đầu.

## Lưu ý trước khi merge main

Workflow `daily-history-repair.yml` trong patch này chỉ là **temporary feature-branch harness**.
Không merge nguyên trạng harness này vào main.

Trước merge production phải:
1. Khôi phục workflow Daily History Repair gốc.
2. Tạo workflow canonical sync riêng nếu quyết định đưa tính năng này vào production.
3. Audit lại diff branch -> main.
