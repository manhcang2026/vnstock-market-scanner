# VNStock Market Scanner — Backend v2

Backend mới phục vụ Dashboard quét 258 mã cổ phiếu Việt Nam.

## Luồng chạy

1. GAS trigger gọi GitHub Actions.
2. Python lấy dữ liệu và tính toàn bộ chỉ báo.
3. Python gửi bảng hoàn chỉnh tới GAS ingestion API để ghi Google Sheet.
4. GAS `doGet()` chỉ đọc `Dashboard_Current` và trả JSON.
5. Dashboard đọc JSON từ GAS.

## Lịch

- `daily-baseline.yml`: 01:00 hằng ngày, do GAS gọi.
- `intraday-scan.yml`: mỗi 10 phút trong giờ giao dịch, do GAS gọi.

## Bốn tín hiệu

1. Giá hiện tại tăng từ 3% so với giá đóng cửa phiên gần nhất.
2. Khối lượng lũy kế đạt từ 200% KLTB10.
3. Giá hiện tại lớn hơn MA200.
4. RVOL30 đạt từ 200%, so khối lượng 30 phút gần nhất với đúng khung giờ của tối đa 10 phiên trước.

RVOL30 tự tích lũy từ ngày triển khai và không tính xuyên giờ nghỉ trưa.

## Google Sheet

Chạy `setupNewBackend()` một lần để tạo:

- `Daily_Baseline`
- `Intraday_Snapshots`
- `Dashboard_Current`
- `Run_Log`

## Cấu hình GAS Script Properties

- `GITHUB_TOKEN`
- `GAS_API_SECRET`

Điền `SPREADSHEET_ID` trong `gas/00_Config.gs`, sau đó deploy Web App.

## GitHub Secrets

- `GAS_WEB_APP_URL`
- `GAS_API_SECRET`

## Cài trigger

Chạy `installBackendTriggers()` một lần trong GAS.
