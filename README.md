# vnstock-market-scanner
Công cụ quét cổ phiếu Việt Nam bằng vnstock.
## Chức năng
- Cập nhật giá thị trường trong phiên.
- Tính các chỉ báo ngày như MA200 và khối lượng trung bình.
- Đẩy dữ liệu sang Google Sheets phục vụ dashboard.
- GitHub Actions được kích hoạt bởi Google Apps Script thông qua API.
## Workflow chính
- `update-market-snapshot.yml`: cập nhật dữ liệu trong phiên.
- `update-daily-indicators.yml`: cập nhật chỉ báo ngày.
- `build-watchlist.yml`: tạo lại danh sách cổ phiếu khi cần.
