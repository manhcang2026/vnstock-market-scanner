# Company Logo Toolkit

Mục tiêu: tạo `SYMBOL.webp` 256x256 cho toàn bộ watchlist và upload lên Supabase Storage bucket `stock-logos`.

## Nguồn logo
Tool chạy theo thứ tự:
1. URL override trong `tools/logos/config/logo_overrides.csv`.
2. Ảnh/logo ứng viên trên hồ sơ Vietstock.
3. Logo / JSON-LD / favicon từ website chính thức tìm được trên Vietstock.
4. Nếu vẫn không có: tạo fallback bằng chữ ticker và đánh dấu `FALLBACK`.

Mọi nguồn đều được ghi lại trong `tools/logos/work/logo_manifest.csv` để review. Không commit ảnh/logo output vào GitHub.

## Chạy lấy logo
`RUN_LOGOS_1_FETCH.bat`

Mặc định chạy toàn bộ `config/watchlist.csv`. Có thể chạy subset bằng lệnh Python với `--symbols <csv>`.

Sau khi chạy, xem số `FALLBACK`. Nếu logo nào sai/thiếu, thêm URL thật vào `logo_overrides.csv`, rồi chạy lại mã đó với `--force`.

## Supabase Storage
1. Chạy `tools/logos/setup_stock_logos_bucket.sql` một lần trong SQL Editor.
2. Copy `tools/logos/.env.example` thành `tools/logos/.env`.
3. Điền Project URL và **Secret key**. File `.env` đã bị gitignore; tuyệt đối không commit key.
4. Chạy `RUN_LOGOS_2_UPLOAD.bat`.

Mặc định uploader bỏ qua fallback; nếu muốn website có ảnh cho đủ tất cả mã, chạy Python với `--include-fallback`.

Website dùng URL cố định:
`{SUPABASE_URL}/storage/v1/object/public/stock-logos/{SYMBOL}.webp`
Không cần thêm cột `logo_url` vào database.
