# CCC UI/UX DESIGN SYSTEM v1.1

**Product:** Chuyện Chợ Chứng — Hệ thống quét & phân tích cổ phiếu  
**Version:** 1.1  
**Effective date:** 2026-08-20  
**Production frontend baseline:** `website/` — HawkHost static frontend v18.5-final800-near-ma  
**Status:** ACTIVE STANDARD

Bộ tài liệu này là chuẩn UI/UX chính thức của Chuyện Chợ Chứng.

## Thứ tự đọc bắt buộc

1. `CCC_UIUX_MASTER.md`
2. `CCC_COMPONENT_RULES.md`
3. `CCC_PAGE_PATTERNS.md`
4. `CCC_UIUX_QA_CHECKLIST.md`

Agent/coder làm việc trong repo phải đọc thêm `AGENTS.md` ở root.

## Source of truth

Frontend production hiện tại nằm tại:

```text
website/
├── index.html
├── .htaccess
├── VERSION.txt
└── assets/
    ├── app-v18.5.js
    └── styles-v18.5.css
```

Không còn sử dụng frontend React/Lovable cũ trong `dashboard/`.

## Bốn trang production hiện tại

- `/` — Tổng quan
- `/danh-sach` — Danh sách cổ phiếu / scanner
- `/so-sanh-theo-nganh` — So sánh theo ngành
- `/sang-loc-co-ban` — Sàng lọc cơ bản

## Nguyên tắc quan trọng

UI/UX Pro Max là nguồn tham khảo thiết kế.  
CCC UI/UX Design System mới là chuẩn trực tiếp của sản phẩm.

Lovable là công cụ tùy chọn. Không được tự ý sử dụng credit; mọi lần dùng phải được Product Owner duyệt trước.
