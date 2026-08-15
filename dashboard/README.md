# vnstock-dashboard-ui

Hãy thiết kế và dựng một giao diện hoàn chỉnh cho dự án VNStock Market Scanner.

Mục tiêu của Dashboard là giúp người dùng nhanh chóng phát hiện những cổ phiếu cần chú ý dựa trên 4 tín hiệu:
1. Giá hiện tại tăng ít nhất 3% so với giá đóng cửa của phiên hoàn tất gần nhất.
2. Khối lượng tích lũy hiện tại đạt ít nhất 200% khối lượng trung bình 10 phiên hoàn tất gần nhất.
3. Giá hiện tại nằm trên MA200.
4. RVOL30 đạt ít nhất 200%.

RVOL30 là chỉ báo cảnh báo sớm. Nó so sánh khối lượng giao dịch trong 30 phút gần nhất với khối lượng trung bình của đúng cùng khung 30 phút đó trong các phiên trước.

PHẠM VI BẮT BUỘC
Chỉ thiết kế giao diện và trải nghiệm người dùng.
Không được tạo Supabase, Firebase, database, authentication, backend mới, kết nối API bên ngoài, sửa logic Python, sửa GitHub Actions, thay đổi kiến trúc dữ liệu, tạo dữ liệu đầu tư thật, hoặc đưa ra khuyến nghị mua/bán.
Dữ liệu thật sau này sẽ được cung cấp từ Google Apps Script và sheet Dashboard_Current.
Hiện tại chỉ dùng dữ liệu demo cục bộ để xem giao diện.
Tách rõ lớp dữ liệu demo, hàm tải dữ liệu, và hàm render giao diện để sau này thay bằng Google Apps Script mà không phải thiết kế lại UI.

NGÔN NGỮ VÀ ĐỊNH DẠNG
- Toàn bộ giao diện dùng tiếng Việt, chuẩn UTF-8.
- Không dùng font ngoài; ưu tiên Arial, Helvetica hoặc system sans-serif.
- Responsive tốt trên desktop và mobile, mobile-first.
- Không dùng bảng rộng kéo ngang trong màn hình Tổng quan.
- Có thể dùng bảng trên desktop trong trang Danh sách; mobile phải chuyển thành thẻ dọc.

PHONG CÁCH
Dashboard tài chính hiện đại, chuyên nghiệp, sạch, dễ đọc, cao cấp nhưng không màu mè; nền trắng/xám rất nhạt, khoảng cách thoáng, bóng nhẹ, bo góc vừa phải, màu cảnh báo rõ nhưng không chói, không hiệu ứng rườm rà.

BỐ CỤC
Hai tab: Tổng quan và Danh sách cổ phiếu.

HEADER
- Tên VNStock Market Scanner
- Trạng thái hệ thống
- Thời điểm dữ liệu thị trường cập nhật
- Thời điểm Dashboard kiểm tra gần nhất
- Tổng số mã theo dõi
- Nhãn DEMO hoặc LIVE
- Nút Làm mới
Khi dùng demo phải có nhãn rõ: DEMO DATA – Không phải dữ liệu thị trường thật.

THẺ TỔNG HỢP
- Cảnh báo sớm RVOL30
- Đủ 4/4 tín hiệu
- Từ 3 tín hiệu trở lên
- Mã thiếu/lỗi dữ liệu
Bấm vào mở trang Danh sách với bộ lọc tương ứng.

CẢNH BÁO SỚM
Tên khu vực: Cảnh báo dòng tiền sớm.
Hiển thị mã có RVOL30 >= 200%, dùng tông tím/tím xanh.
Mỗi thẻ hiển thị: mã, sàn, giá hiện tại, % thay đổi, RVOL30, số phiên RVOL30 (0/10, 1/10, 5/10, 10/10), tỷ lệ KL ngày, khoảng cách MA200, điểm tín hiệu.
Một mã có thể xuất hiện cả ở cảnh báo sớm và nhóm tín hiệu tương ứng.

PHÂN NHÓM
4/4 — Tín hiệu rất mạnh: đỏ rượu/đỏ đậm vừa phải.
3/4 — Tín hiệu mạnh: cam.
2/4 — Đang hình thành: vàng/vàng nâu.
1/4 — Tín hiệu ban đầu: xanh lam/xanh xám.
Không hiển thị 0/4 ở Tổng quan.
Nhóm 1/4 chỉ hiển thị một số mã ưu tiên và có nút Xem tất cả.

THẺ CỔ PHIẾU
Hiển thị: mã, sàn, giá hiện tại, % thay đổi, tỷ lệ KL ngày, khoảng cách MA200, RVOL30, số phiên RVOL30, điểm tín hiệu.
Có 4 chỉ báo nhỏ cho: giá >=3%, KL ngày >=200%, trên MA200, RVOL30 >=200%.
Không dùng icon gợi ý mua/bán.

TRANG DANH SÁCH
Tìm theo mã.
Lọc: tất cả sàn, HOSE, HNX, UPCOM, 4/4, từ 3/4 trở lên, đúng 2/4, đúng 1/4, RVOL30 >=200%, Giá >=3%, KL ngày >=200%, Trên MA200, Thiếu dữ liệu.
Sắp xếp: ưu tiên tín hiệu, RVOL30 cao nhất, % tăng cao nhất, KL ngày cao nhất, mã A–Z.
Ưu tiên mặc định: có RVOL30 >=200%, signal_count cao hơn, RVOL30 cao hơn, % giá cao hơn, KL ngày cao hơn.
Desktop dùng bảng với các cột: Mã, Sàn, Giá, % thay đổi, KL ngày, MA200, RVOL30, Số phiên RVOL30, Tín hiệu, Trạng thái dữ liệu.
Mobile dùng thẻ dọc, không kéo ngang.

POPUP CHI TIẾT
Hiển thị: mã, sàn, giá hiện tại, giá đóng cửa, % thay đổi, MA200, khoảng cách MA200, số phiên MA200, KL tích lũy, KLTB10, số phiên KLTB10, tỷ lệ KL ngày, KL 30 phút, KL30 trung bình cùng khung, RVOL30, số phiên RVOL30, ngày giao dịch, khung thời gian, thời điểm cập nhật, trạng thái dữ liệu, nguồn dữ liệu, nhãn DEMO/LIVE.
Định dạng dễ hiểu: Ngày giao dịch 03/08/2026; Khung thời gian 09:20–09:50; Cập nhật lúc 09:52:14. Không hiển thị ISO dài hoặc ngày năm 1899.

LOGIC RVOL30
- 0/10: chưa có phiên tham chiếu
- 1/10: mới có 1 phiên
- 5/10: có 5 phiên
- 10/10: đủ 10 phiên
Khi rvol30_sessions = 0: không hiển thị RVOL30 giả, hiển thị “Chưa đủ dữ liệu”, signal_rvol30_200pct chưa đạt.
Khi chưa tính được: hiển thị “—” hoặc “Chưa có dữ liệu”, không hiển thị 0% như số thật.

DỮ LIỆU DEMO
Tạo khoảng 20 mã demo với đủ trường hợp 4/4, 3/4, 2/4, 1/4, 0/4; RVOL30 session từ 0/10 đến 10/10; một số mã thiếu dữ liệu; một số mã cảnh báo sớm nhưng chỉ 1/4; một số mã 3/4 chưa đạt RVOL30.
Dữ liệu hợp lý, % giá khoảng -3% đến +8%, không tạo +100%.
Không ám chỉ cổ phiếu thật đang có tín hiệu.
Tất cả demo có data_status = DEMO.

CẤU TRÚC CODE
Tách rõ: dữ liệu demo; loadDashboardData(); normalizeRows(); renderSummary(); renderOverview(); renderStockList(); renderStockCard(); renderStockDetail(); applyFilters(); applySorting().
Không hard-code từng thẻ trong HTML; render từ mảng dữ liệu.
Không kết nối backend thật, không database, không sửa kiến trúc.

KẾT QUẢ
Dựng giao diện hoàn chỉnh, preview được ngay.
Sau khi hoàn thành, nêu rõ:
1. File/component chứa mock data.
2. Hàm trả mock data.
3. Hàm cần thay để nối Google Apps Script.
4. Các thành phần UI chính.
5. Cách chuyển DEMO sang LIVE mà không sửa giao diện.

Ưu tiên thiết kế đẹp, rõ ràng, chuyên nghiệp, dễ bảo trì.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/2a153185-d9cd-4807-ba8c-9bb37eeee4fd).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
