# CCC 4C-9 / Alpha.19 — Stabilization

- Restore Alpha.17 account/member visual layer.
- Overview KPI copy: `DS của bạn: X mã`.
- Default Overview: all tracked symbols; KPI click filters; reset returns all.
- Empty tracked list: fixed demo symbols `VCB, FPT, HPG, VIC, VNM, GAS` with full CCC presentation plus onboarding CTA.
- Sidebar hides `Bộ quét`; `DS mã theo dõi` opens `/danh-sach`.
- `/danh-sach`: tracked-list tab first, whole-market tab second.
- Whole-market tab uses authenticated safe RPC and returns only basic fields; no CCC/RVOL30 fields.
- Desktop: 50/page. Mobile: 20 + `Xem thêm`.
- FULL/VIP effective tracked list = current Scanner Universe dynamically.
- 7-day setup quota logic unchanged.

Supabase migration already applied: `add_safe_market_basic_and_overview_samples`.
