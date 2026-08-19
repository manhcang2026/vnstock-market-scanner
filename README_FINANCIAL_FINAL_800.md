# Financial pipeline FINAL 800

Mục tiêu hiện tại:
- Universe scanner: 800 mã final.
- Metadata/BCTC đang có và còn thuộc universe: 257 mã.
- Cần bổ sung: 543 mã.
- Không tự ghi Supabase; chỉ tạo SQL để chạy có kiểm soát.

## STEP 1
Chạy `RUN_STEP1_METADATA.bat`.

Nó:
1. xác minh 800 / 257 / 543;
2. lấy tên pháp lý từ `config/watchlist.csv` (VNStock);
3. gọi hồ sơ Vietstock để đối chiếu tên và lấy phân ngành;
4. Vietstock là nguồn chính cho ngành, watchlist chỉ fallback;
5. BANK / SECURITIES / INSURANCE được bảo vệ;
6. sinh link BCTC động theo mã;
7. tất cả mismatch/fallback/không rõ phải review.

Dừng sau STEP 1 và gửi:
- `tools/financial/output/industry_new_current_raw.csv`
- `tools/financial/output/industry_review_current.csv`

Sau khi duyệt tạo `industry_new_current_final.csv`.

## STEP 2
Chạy `RUN_STEP2_BCTC.bat`.

Giữ logic Vietstock BCTT cũ:
- tối đa 9 quý;
- ưu tiên hợp nhất;
- 4 financial model;
- exact metric trước;
- contains chỉ dùng khi duy nhất 1 chỉ tiêu khớp;
- nhiều chỉ tiêu cùng khớp => không lấy bừa, đánh dấu ambiguous;
- chặn kỳ báo cáo tương lai so với kỳ hợp lý hiện tại;
- checkpoint chỉ mã thành công, lỗi chạy lại sẽ retry;
- QoQ/YoY.

## STEP 3
Chạy `RUN_STEP3_BUILD_SQL.bat`.

Production validation:
- essential metrics theo từng financial model;
- future period bị loại;
- ambiguous metric => PARTIAL/REVIEW;
- SQL chỉ UPSERT, không DELETE/TRUNCATE.

## Link Vietstock
Không lưu URL trong Supabase. Website sinh:
`https://finance.vietstock.vn/{SYMBOL}/tai-chinh.htm?tab=BCTT`

## Dọn file cũ
Sau khi đã copy pipeline mới, chạy `CLEAN_OLD_542_PIPELINE.bat` nếu muốn dọn các file 542 cũ.
