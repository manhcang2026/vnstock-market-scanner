CCC v19.12.0 — ONE-SHOT FRONTEND RELEASE
=========================================

Mục tiêu của gói này:
1) Hiện Bảng vàng 4/4, có lịch sử cũ và Signal V1/V2-ready.
2) Public offer chỉ còn VIP DAY 100.000đ/24h và FULL 1.000.000đ/tháng.
3) Đổi cách gọi VOL10 trên UI thành KL/TB10 + chú thích đúng Same-Time trong giờ giao dịch.
4) Đồng bộ UI với backend VIP mới: VIP DAY có DS mã theo dõi không giới hạn; hết VIP danh sách vẫn giữ, mã vượt gói nền hiện trạng thái khóa kỹ thuật.

BASELINE AN TOÀN
----------------
Gói patch này được dựng trên website-next baseline:
  v19.11.5-mobile-auth-hotfix
(branch nguồn kiểm tra: hotfix/mobile-auth-2026-08-27)

TRƯỚC KHI CHÉP FILE:
Mở file local: website-next/VERSION.txt
- Nếu đang là: v19.11.5-mobile-auth-hotfix -> tiếp tục.
- Nếu KHÁC -> DỪNG, không ghi đè index.html. Gửi ảnh VERSION.txt cho ChatGPT để rebase patch lên bản mới hơn.

CÁC FILE SẼ THAY/THÊM
----------------------
REPLACE:
  website-next/index.html
  website-next/VERSION.txt

ADD:
  website-next/assets/ccc-v19.12.0-golden-membership-vol10.js
  website-next/assets/ccc-v19.12.0-golden-membership-vol10.css
  supabase/migrations/20260904213653_golden_board_signal_version_v1.sql
  supabase/migrations/20260904213703_golden_board_expose_signal_version.sql
  docs/release/CCC_v19.12.0_RELEASE_NOTES.md
  docs/release/BACKEND_PRODUCTION_STATUS.md

KHÔNG THAY:
- app-v19.7.0-phase5c-cross-route.js
- data-v19.7.0-phase5c-cross-route.js
- mobile-auth-hotfix-v19.11.5.js
- các file scanner/backend hiện tại

SUPABASE
--------
Backend production đã apply xong trước release này.
KHÔNG chạy lại SQL thủ công chỉ để deploy website.
Hai file migration Golden Board đi kèm để Git repo có record tương ứng với production.

SAU KHI COPY VÀO REPO
----------------------
GitHub Desktop nên hiện các thay đổi chính:
- 2 file modified: index.html, VERSION.txt
- 4+ file added

Commit đề xuất:
  Release v19.12.0 Golden Board membership TB10

Sau đó Push origin.

DEPLOY WEBSITE (HAWKHOST / cPanel)
---------------------------------
Production HawkHost/cPanel hiện dùng root: /home/visasgn1/chuyenchochung.com/
Upload theo thứ tự an toàn:
1) website-next/assets/ccc-v19.12.0-golden-membership-vol10.js -> /home/visasgn1/chuyenchochung.com/assets/
2) website-next/assets/ccc-v19.12.0-golden-membership-vol10.css -> /home/visasgn1/chuyenchochung.com/assets/
3) website-next/VERSION.txt -> /home/visasgn1/chuyenchochung.com/VERSION.txt (replace)
4) website-next/index.html -> /home/visasgn1/chuyenchochung.com/index.html (replace, UPLOAD CUỐI CÙNG)

Không cần upload supabase/ hoặc docs/ lên hosting. Không đụng thư mục stock-logos/.

SMOKE TEST SAU DEPLOY
---------------------
1) Ctrl+F5 chuyenchochung.com
2) Bấm Bảng vàng -> URL /bang-vang
3) Bảng vàng latest phải thấy dữ liệu 04/09 cũ; user VIP thấy đủ 6 mã.
4) Đổi ngày -> phải có 27/08, 28/08, 03/09, 04/09.
5) Kiểm tra badge V1 ở rows.
6) Tài khoản -> phần nâng cấp chỉ còn FULL; VIP DAY hiện riêng.
7) Trang Hướng dẫn -> chỉ còn 2 offer trả phí: VIP DAY + FULL.
8) Các chỗ khối lượng đổi sang KL/TB10 hoặc TB10 và có chú thích Same-Time.
9) Với user Launch VIP: DS mã theo dõi phải cho thêm vượt limit base (không bị frontend chặn).

ROLLBACK NHANH
-------------
Nếu UI có vấn đề, chỉ cần restore index.html cũ trên hosting.
Hai file CSS/JS mới có thể để nguyên vì index cũ không load chúng.
Backend không cần rollback.
