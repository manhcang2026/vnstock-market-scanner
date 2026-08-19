# Financial Toolkit - reusable

Mục tiêu: giữ thuật toán lâu dài, không giữ output của từng lần chạy trong Git.

## Khi thêm mã mới
1. Thêm mã vào scanner/watchlist theo quy trình của hệ thống.
2. Điền ticker vào `tools/financial/input/symbols_to_add.csv`.
3. Chạy `RUN_FINANCIAL_1_METADATA.bat`.
   - Tên pháp lý: lấy từ `config/watchlist.csv` (VNStock).
   - Vietstock: đối chiếu tên + phân ngành.
   - Nếu còn mã chưa chắc chắn, file `tools/financial/work/industry_unresolved.csv` sẽ được tạo. Review rồi thêm override vào `tools/financial/config/industry_overrides.csv` và chạy lại.
4. Chạy `RUN_FINANCIAL_2_BCTC.bat`.
   - tối đa 9 quý;
   - ưu tiên hợp nhất;
   - NORMAL / BANK / SECURITIES / INSURANCE;
   - exact metric trước;
   - contains chỉ nhận khi duy nhất một chỉ tiêu khớp;
   - ambiguous -> PARTIAL/REVIEW;
   - chặn kỳ tương lai;
   - lỗi không checkpoint, chạy lại sẽ retry;
   - mã không có BCTC vẫn có `NO_FINANCIAL_DATA` trong financial_latest.
5. Chạy `RUN_FINANCIAL_3_SQL.bat`.
   - SQL chỉ UPSERT;
   - chia 250 rows/file để chạy được bằng Supabase SQL Editor;
   - không DELETE/TRUNCATE.
6. Chạy SQL trong `tools/financial/work/sql/` theo thứ tự và cuối cùng chạy file verify.

## Link BCTC Vietstock
Không cần lưu URL trong database. Website sinh từ ticker:
`https://finance.vietstock.vn/{SYMBOL}/tai-chinh.htm?tab=BCTT`

## Output
`tools/financial/work/` là output tạm và đã được `.gitignore`; không commit lên GitHub.

## Refresh toàn bộ
Chỉ khi thật sự cần: `py tools\financial\00_prepare_targets.py --all`, sau đó chạy classifier/fetch như bình thường. Không dùng tùy tiện vì sẽ gọi Vietstock rất nhiều.
