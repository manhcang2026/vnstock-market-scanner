# Vietstock Financial Pipeline — mở rộng 258 → 800 mã

Bộ này **không ghi trực tiếp Supabase** và **không sửa scanner Daily/Intraday**.

## Trạng thái đầu vào
- Scanner universe: 800 mã.
- Đã có stock_metadata + BCTC: 258 mã thuộc universe hiện tại.
- Còn thiếu: 542 mã.
- TCQ cũ không thuộc universe 800 và không được xử lý lại.

## STEP 1 — phân ngành 542 mã mới
Chạy:
`RUN_STEP1_CLASSIFY_542.bat`

Script:
- chỉ gọi Vietstock cho 542 mã thiếu;
- có resume;
- ERROR sẽ retry khi chạy lại;
- Vietstock là nguồn chính;
- watchlist chỉ là fallback/đối chiếu;
- 3 mô hình đặc thù BANK/SECURITIES/INSURANCE được bảo vệ;
- không đụng 258 metadata cũ.

Kết quả:
- `tools/financial/output/industry_new_542_raw.csv`
- `tools/financial/output/industry_review_542.csv`

**Dừng ở đây và gửi 2 file cho ChatGPT duyệt.**
Sau khi duyệt sẽ có:
`tools/financial/output/industry_new_542_final.csv`

## STEP 2 — lấy BCTC 542 mã
Chạy:
`RUN_STEP2_FETCH_BCTC_542.bat`

Giữ nguyên logic pipeline v4.3 cũ:
- Vietstock BCTT;
- tối đa 9 quý;
- ưu tiên BCTC hợp nhất trong từng quý;
- nếu không có hợp nhất thì dùng riêng lẻ/đơn lẻ;
- 4 model: NORMAL / BANK / SECURITIES / INSURANCE;
- QoQ / YoY;
- exact metric match trước, contains sau;
- checkpoint chỉ mã thành công;
- mã lỗi không checkpoint, chạy lại sẽ retry.

## STEP 3 — tạo dữ liệu production + SQL
Chạy:
`RUN_STEP3_BUILD_SQL.bat`

Output:
- `01_stock_metadata_542.sql`
- `02_financial_quarterly_partXX.sql`
- `03_financial_latest_542.sql`
- `99_verify_coverage.sql`

Các SQL:
- chỉ UPSERT;
- không DELETE;
- không TRUNCATE;
- không xóa 258 mã cũ;
- bạn chạy thủ công trong Supabase SQL Editor.

## Link Vietstock dùng trên website sau này
Không cần lưu URL trong Supabase.
Từ symbol có thể sinh:
`https://finance.vietstock.vn/{SYMBOL}/tai-chinh.htm?tab=BCTT`

## Lưu ý
- Không chạy STEP 2 trước khi `industry_review_542.csv` được duyệt.
- Nếu STEP 2 bị dừng giữa chừng, chạy lại; script resume.
- Nếu còn `errors_542.csv`, chạy lại STEP 2 để retry.
