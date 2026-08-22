# CCC v19 Phase 1 Report

**Release:** `v19.1.0-shell`  
**Repository:** `manhcang2026/vnstock-market-scanner`  
**Branch:** `feature/user-auth-foundation`  
**Date:** 2026-08-23  
**Target:** `website-next/` staging only  
**Review state:** Phase 1 corrections complete; awaiting Product Owner approval  
**Stop gate:** Phase 2 not started

## 1. Corrected Phase 1 outcome

Phase 1 now uses the approved three-asset consolidation without redesigning the CCC shell:

- `website-next/assets/data-v19.1.0.js` — one Supabase client and DOM-free data/auth adapter;
- `website-next/assets/app-v19.1.0.js` — one route, History API, shell and page-render owner;
- `website-next/assets/styles-v19.1.0.css` — one consolidated token/component/layout stylesheet.

The corrected desktop structure is:

```text
APPROVED TOP BAR
+ LEFT SIDEBAR
+ WORKING AREA
  + FULL-WIDTH PAGE HEADER
  + MAIN CONTENT + RIGHT RAIL
```

The desktop sidebar is retained and renders this final primary IA on the first application render:

1. Tổng quan
2. Nghiên cứu
3. DS mã theo dõi
4. Cảnh báo — visible, disabled and explicitly not ready
5. Tài khoản

`DS mã theo dõi` is the real link to `/danh-sach`. `Theo ngành` and `Sàng lọc cơ bản` remain inside the Nghiên cứu area and are not separate primary sidebar destinations. The obsolete user-facing label is absent from the active HTML, JavaScript, stylesheet and rendered initial DOM.

There is no horizontal desktop primary navigation.

## 2. Top bar preservation

The approved top-bar structure and visual direction are preserved with stable slots for:

- CCC brand and staging identity;
- stock-search area;
- market/session status context;
- refresh and next-check context;
- notification affordance;
- Light/Dark toggle;
- account/user affordance.

Phase 1 cannot safely load technical-market search, refresh or countdown data before the later backend STOP gates are resolved. Those slots therefore render an explicit neutral/disabled state. They are not removed, fabricated or repaired later by polling. Session and Account slots update only from the application state when authentication or membership resolves.

## 3. Runtime ownership and consolidation

### Data adapter

`data-v19.1.0.js` owns exactly one pinned Supabase browser client and the existing frontend contracts for:

- session restoration and auth-state subscription;
- Email/password login and Google OAuth;
- logout;
- profile, current subscription, plan and plan-catalog reads;
- `save_my_profile`;
- `get_my_watchlist_state`;
- `replace_my_watchlist`;
- stock-metadata search;
- public `financial_latest` and `stock_metadata` research reads.

It contains no DOM, History API, UI-label or theme ownership.

### App/router/render owner

`app-v19.1.0.js` owns the stable top bar, sidebar, mobile navigation, routing, History API, Page Header, main/right-rail layout, Account, Watchlist and route-specific presentation. The shell mounts once. Route changes replace only the route host; Watchlist operations update only the Watchlist region; theme changes update tokens and the toggle icon without reconstructing the shell.

### Stylesheet owner

`styles-v19.1.0.css` remains a real consolidation, not a concatenation of the five Alpha stylesheets. It has one cascade owner organized as reset → semantic Light/Dark tokens → shell → shared components → pages → responsive/reduced motion. It contains zero `!important` declarations.

## 4. GRACE membership correction

The current-subscription read now resolves all locked current states through the existing frontend table contract:

```text
ACTIVE
GRACE
SUSPENDED
```

The query includes `GRACE` and reads the existing `grace_started_at` / `grace_end_at` fields. No schema, RLS, RPC or backend change was made.

A GRACE subscription retains its current plan in Account instead of falling into the false “no active plan” state. Account and the top-bar account context render `Chờ gia hạn`, and the membership card shows the grace end time. SUSPENDED remains a current readable state and renders `Tạm ngưng` rather than an invented replacement plan.

## 5. Authentication, Account and Watchlist preservation

The correction preserves:

- Email login;
- Google login;
- session restore;
- logout;
- profile load/save;
- current plan;
- Account route and `#ds-ma-theo-doi` / `#goi-thanh-vien` anchors;
- Watchlist load, metadata search, add, remove, reset and atomic save;
- backend-authoritative capacity/quota/error behavior;
- the 7-day initial setup rule and its explanatory banner.

Temporary local-only fixtures were used for QA and removed before packaging. No real credentials were entered and no backend mutation was performed.

Authenticated fixture results:

- session restored as `Thành viên QA`;
- GRACE `BASIC` plan rendered as `CCC Basic` with `Chờ gia hạn` in Account and top bar;
- both Account anchors existed;
- Watchlist loaded `FPT` and `VNM` exactly once;
- metadata search found `MWG`;
- add, remove and reset updated only the editor region;
- save submitted the complete sorted array `FPT, MWG, VNM` and rendered success feedback;
- profile save rendered success feedback;
- logout cleared membership/Watchlist state and returned Account to the guest state;
- a separate ACTIVE setup fixture rendered `7 ngày khởi tạo miễn phí`, `Đang khởi tạo`, and the locked remove/change-quota rule.

Guest fixture results:

- Google, Email and password controls were present;
- the Email adapter entry point was invoked once;
- the Google adapter entry point was invoked once;
- no technical row, signal value, mock plan or obsolete label was present.

## 6. Phase boundary and backend STOP gates

Overview and Scanner remain entitlement-safe Phase 1 structural states. The following were not implemented and remain STOP gates:

1. guest-safe six-symbol Overview demo contract;
2. guest-safe whole-market basic contract;
3. server-paged absolute nearest-MA10/MA200 sort contract;
4. legacy anonymous technical-access closure.

No Supabase schema, RLS, RPC, table, Auth configuration, migration or backend file was changed. Phase 2 was not started.

## 7. Verification results

### Static and architecture

- `node --check website-next/assets/data-v19.1.0.js` — PASS
- `node --check website-next/assets/app-v19.1.0.js` — PASS
- local active asset references exist and are versioned — PASS
- `createClient(` count — 1
- `MutationObserver` count — 0
- `setInterval` count — 0
- `!important` count — 0
- active obsolete-label count — 0
- active Alpha runtime references — 0
- temporary QA fixture files — 0
- ZIP files inside repository — 0
- `git diff --check` — PASS
- production `website/` diff — empty

The only application timers are the 220ms Watchlist search debounce and a zero-delay Supabase auth-callback deferral. Neither performs routing, DOM repair or polling.

### Direct routes, click routing and history

Direct fallback loads and the single router were verified for:

- `/`
- `/danh-sach`
- `/danh-sach?tab=market`
- `/so-sanh-theo-nganh`
- `/sang-loc-co-ban`
- `/tai-khoan`
- `/tai-khoan#ds-ma-theo-doi`
- `/tai-khoan#goi-thanh-vien`

Sidebar and Nghiên cứu-tab click routing produced the expected URL, heading, focus and `aria-current`. Back moved from `/sang-loc-co-ban` to `/so-sanh-theo-nganh` with heading `So sánh theo ngành`; Forward restored `/sang-loc-co-ban` with heading `Sàng lọc cơ bản`. Both history renders retained `Nghiên cứu` as the active primary item and focused the main region.

### Responsive and theme matrix

All eight URLs were tested at 375, 768, 1024 and 1440 pixels. Light and Dark were exercised on every route/width combination.

- 32 route/width cases and 64 theme states — PASS
- horizontal overflow — 0 cases
- obsolete rendered label — 0 cases
- top-bar slots present — 32/32 cases
- Page Header immediately before content grid — 32/32 cases
- right rail exists — 32/32 cases
- theme changed without shell reload — 32/32 cases

Measured layout:

| Viewport | Sidebar | Main | Right rail | Result |
|---:|---:|---:|---:|---|
| 1024 | 184px | 521px | 240px | labeled sidebar + main + sticky rail |
| 1440 | 224px | 829px | 300px | labeled sidebar + main + sticky rail |
| 768 | hidden | 705px | 705px stacked | responsive single flow |
| 375 | hidden | 336px | 336px stacked | mobile single flow + bottom nav |

Desktop Dark and mobile 375px Dark/Light screenshots were visually inspected. The sidebar, top bar, Page Header, content hierarchy, right rail, disabled Cảnh báo treatment and mobile navigation remained readable. Reduced-motion rules remain present.

## 8. Active file hashes

| File | Bytes | SHA-256 |
|---|---:|---|
| `website-next/index.html` | 1,258 | `3D1E7486759DE1F70091D44C58AD02238DC8F0C1E956851F8DB8AA48A11F699D` |
| `website-next/VERSION.txt` | 14 | `FC802674C3D3C7711F1193920453F07A597608AC3A75D5523F18E57EE06D4F62` |
| `website-next/assets/data-v19.1.0.js` | 6,318 | `68F22B3AB39667F8D891B04E83A1C03DFE6D694D299F30CA36E3E5A1414F7CAF` |
| `website-next/assets/app-v19.1.0.js` | 61,581 | `507B29B475361240632EDA60DA06844471E9869722FE3A2648FFA93053A20226` |
| `website-next/assets/styles-v19.1.0.css` | 30,038 | `9E23B8AAEDCC4B7617417F0DD3FAD0F08027B5DD7E2CB5E785FB00925FD31D9E` |

## 9. Rollback

The Alpha assets remain physically unchanged for rollback. A staging rollback is:

1. restore the pre-Phase-1 `website-next/index.html` and `website-next/VERSION.txt` from Git or the previous package;
2. confirm they reference the unchanged Alpha.6/15/16/17/19 assets;
3. retain the v19.1.0 assets for diagnosis;
4. perform no backend rollback because Phase 1 made no backend change.

No deployment was performed.

## 10. Handoff packages

Both handoff ZIPs live outside the repository at:

```text
D:\github\CCC_HANDOFF\
```

The repository working tree contains no ZIP file.

### `CCC_CODEX_P1_REPO_UPLOAD.zip`

- `README_UPLOAD.txt`
- `website-next/index.html`
- `website-next/VERSION.txt`
- `website-next/assets/data-v19.1.0.js`
- `website-next/assets/app-v19.1.0.js`
- `website-next/assets/styles-v19.1.0.css`
- `docs/refactor/CCC_V19_PHASE1_REPORT.md`

### `CCC_CODEX_P1_CPANEL.zip`

- `README_DEPLOY.txt`
- `index.html`
- `VERSION.txt`
- `assets/data-v19.1.0.js`
- `assets/app-v19.1.0.js`
- `assets/styles-v19.1.0.css`

The cPanel archive does not contain `.htaccess`, because Phase 1 did not modify it.

## 11. Stop gate

Phase 1 corrections are complete and stopped for Product Owner review. Do not commit, push, merge, deploy or begin Phase 2 from this handoff.
