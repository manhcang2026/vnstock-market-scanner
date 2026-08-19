# Repo cleanup + reusable financial/logo toolkit

## Làm một lần ngay bây giờ
1. Giải nén chồng package này vào repo local.
2. Chạy `CLEAN_FINANCIAL_LEGACY.bat`.
3. Mở GitHub Desktop: kiểm tra deletions + các file toolkit mới.
4. Commit/Push với message: `Clean financial pipeline and add reusable logo toolkit`.

Sau cleanup, repo chỉ giữ thuật toán và config nhỏ; output từng lần chạy bị `.gitignore`.

## Financial về sau
- Điền ticker vào `tools/financial/input/symbols_to_add.csv`.
- `RUN_FINANCIAL_1_METADATA.bat`
- `RUN_FINANCIAL_2_BCTC.bat`
- `RUN_FINANCIAL_3_SQL.bat`

## Logo
- `RUN_LOGOS_1_FETCH.bat` để lấy/chuẩn hóa logo.
- Review manifest/fallback.
- Tạo bucket bằng `tools/logos/setup_stock_logos_bucket.sql`.
- Tạo `tools/logos/.env` từ `.env.example` và điền Supabase Secret key.
- `RUN_LOGOS_2_UPLOAD.bat`.
