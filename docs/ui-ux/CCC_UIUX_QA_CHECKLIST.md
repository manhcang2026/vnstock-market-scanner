# CCC UI/UX QA CHECKLIST v1.1

**Baseline:** production website v18.5  
**Purpose:** release gate

---

# A. Source correctness

- [ ] UI work modifies the current `website/` frontend, not an obsolete frontend.
- [ ] `VERSION.txt` is reviewed.
- [ ] HTML references the intended versioned JS/CSS assets.
- [ ] No production-only HawkHost edit exists without Git counterpart.
- [ ] No secret/service-role key was introduced into frontend.
- [ ] Publishable frontend credentials remain within intended security model.

---

# B. Routes

- [ ] `/` works.
- [ ] `/danh-sach` works.
- [ ] `/so-sanh-theo-nganh` works.
- [ ] `/sang-loc-co-ban` works.
- [ ] `.htaccess` SPA fallback still works.
- [ ] Direct URL refresh works on every route.

---

# C. Data sources

- [ ] `stock_snapshot` loads.
- [ ] `financial_latest` loads.
- [ ] `stock_metadata` loads.
- [ ] `financial_quarterly` loads when detail requests it.
- [ ] BCTC Vietstock link remains correct.
- [ ] Network error does not destroy valid cached market data.

---

# D. Scanner universe

- [ ] Full production universe is validated.
- [ ] UI does not delete/stop scanning symbols.
- [ ] Filters are display-only.
- [ ] Future watchlist actions are display-only.
- [ ] Missing rows are not silently interpreted as user removal.

---

# E. Technical signals

- [ ] Price ≥3% signal correct.
- [ ] Daily volume ≥200% signal correct.
- [ ] Above MA200 signal correct.
- [ ] RVOL30 ≥200% signal correct.
- [ ] MA10 remains reference, not counted as core signal.
- [ ] `0/4` renders neutral.
- [ ] `1/4…4/4` count matches conditions.
- [ ] Signal UI does not imply recommendation.

---

# F. Fundamental score

- [ ] Score numerator is correct.
- [ ] Available denominator/coverage is visible.
- [ ] Missing criteria are not silently scored as zero unless business rule says so.
- [ ] Financial-model special cases remain honest.
- [ ] Profit YoY is correct.
- [ ] ROE is correct.
- [ ] P/E and P/B are correct.
- [ ] Industry median comparison behavior remains correct.
- [ ] Freshness state is shown.
- [ ] `NO_FINANCIAL_DATA` has a clear state.

---

# G. Data trust

- [ ] Updated time visible.
- [ ] Total symbols visible or accessible.
- [ ] Healthy/degraded/error state accurate.
- [ ] Countdown accurate.
- [ ] Outside-hours copy accurate.
- [ ] Error + cache behavior explicit.
- [ ] Manual refresh works.
- [ ] User is not shown false LIVE/healthy state.

---

# H. Dark mode

- [ ] Dark loads as intended for a user without saved preference.
- [ ] Saved Dark preference persists.
- [ ] Text contrast acceptable.
- [ ] Tables readable.
- [ ] Signal states distinguishable.
- [ ] Score states distinguishable.
- [ ] Focus visible.
- [ ] No neon overload.

---

# I. Light mode

- [ ] Toggle works.
- [ ] Saved Light preference persists.
- [ ] Text contrast acceptable.
- [ ] Borders/surfaces distinguish sections.
- [ ] Semantic colors remain readable.
- [ ] Focus visible.
- [ ] No washed-out status.

---

# J. Typography

- [ ] Essential text is not 9–11px.
- [ ] Mobile body is readable without zoom.
- [ ] Symbol prominent.
- [ ] Company name readable.
- [ ] Technical abbreviations have context.
- [ ] Numeric columns use tabular figures.
- [ ] Table header subtitles remain readable.
- [ ] Long Vietnamese labels do not break layout.

---

# K. Overview

- [ ] KPI count correct.
- [ ] RVOL30 early list correct.
- [ ] 4/4 list correct.
- [ ] 3/4 list correct.
- [ ] 2/4 list correct.
- [ ] 1/4 preview limited.
- [ ] KPI links open correct filtered scanner.
- [ ] Duplicate content is not excessive.
- [ ] Mobile page length remains practical.

---

# L. Scanner

- [ ] Search works.
- [ ] Enter submits search.
- [ ] Clear search works.
- [ ] Exchange filter works.
- [ ] Signal filters work.
- [ ] All sort modes work.
- [ ] Nearest MA10 works.
- [ ] Nearest MA200 works.
- [ ] Result count correct.
- [ ] Pagination correct.
- [ ] Opening detail preserves meaningful list context.
- [ ] Search/filter UI does not freeze.

---

# M. Industry comparison

- [ ] Industry list complete.
- [ ] Industry names not unintentionally clipped.
- [ ] Counts correct.
- [ ] Selected state clear.
- [ ] Table sorting basis clear.
- [ ] Score coverage visible.
- [ ] Numeric values aligned consistently.
- [ ] Freshness visible.
- [ ] Mobile selection usable.

---

# N. Fundamental screener

- [ ] Score filter works.
- [ ] Profit-growth filters work.
- [ ] ROE filters work.
- [ ] Result count correct.
- [ ] Missing-data symbols are treated according to rule.
- [ ] Methodology explanation available.
- [ ] Methodology does not block primary workflow.
- [ ] Cards/table show score coverage.

---

# O. Stock detail

- [ ] Logo fallback works.
- [ ] Company name works.
- [ ] Symbol/exchange correct.
- [ ] Technical signal summary correct.
- [ ] Why-notable explanation uses real values only.
- [ ] Fundamental summary correct.
- [ ] Score breakdown correct.
- [ ] Quarterly loading works.
- [ ] Quarterly empty works.
- [ ] Quarterly error works.
- [ ] BCTC link works.
- [ ] Dialog closes by button.
- [ ] Escape closes dialog.
- [ ] Mobile detail is scrollable.

---

# P. Responsive 375px

- [ ] No page horizontal overflow.
- [ ] Mobile nav does not overlap content.
- [ ] Search is comfortable.
- [ ] Filters are tappable.
- [ ] Card data is readable.
- [ ] No essential 7–9px labels.
- [ ] Detail fits viewport.
- [ ] Safe area respected.

---

# Q. Responsive 768px

- [ ] Layout intentionally chosen.
- [ ] No awkward desktop table squeeze.
- [ ] Industry selector usable.
- [ ] Fundamental filters readable.
- [ ] Header/trust area proportionate.

---

# R. Responsive 1024px

- [ ] Sidebar and content widths fit.
- [ ] Scanner table remains readable.
- [ ] No unexpected overlap.
- [ ] Long table headers remain clear.
- [ ] Detail dialog does not exceed usable viewport.

---

# S. Responsive 1440px

- [ ] Data workspace uses width efficiently.
- [ ] Columns not needlessly spread.
- [ ] Overview hierarchy remains clear.
- [ ] No giant empty gutters.
- [ ] Header aligns with main content.

---

# T. Accessibility

- [ ] `<html lang="vi">`.
- [ ] Keyboard focus visible.
- [ ] Buttons semantic.
- [ ] Links semantic.
- [ ] Icon-only controls labeled.
- [ ] Clickable table/card has keyboard path.
- [ ] No essential hover-only info.
- [ ] State not color-only.
- [ ] Dialog semantics/focus acceptable.
- [ ] Heading hierarchy logical.

---

# U. Performance

- [ ] Initial load acceptable.
- [ ] Search/filter responsive.
- [ ] 800-row source does not lock UI.
- [ ] Pagination still effective.
- [ ] Images/logo failures do not create repeated heavy work.
- [ ] No unnecessary repeated full financial fetch.
- [ ] Refresh retains previous data.
- [ ] CSS effects do not cause scroll jank.
- [ ] Version polling does not overload backend.

---

# V. Copy

- [ ] Primary labels are Vietnamese and understandable.
- [ ] ROE/ROA/P-E/P-B have plain-language helper.
- [ ] `Điểm cơ bản` meaning clear.
- [ ] Score denominator meaning clear.
- [ ] Scanner copy avoids investment recommendation.
- [ ] Disclaimer remains concise.
- [ ] External BCTC source clear.

---

# W. Lovable gate

If Lovable was used:

- [ ] Task was proposed first.
- [ ] Product Owner approved.
- [ ] Credit estimate was supplied.
- [ ] Output reviewed against CCC standard.
- [ ] No Lovable-generated fake data reached production.

---

# X. Release

- [ ] Mockups approved.
- [ ] Dark approved.
- [ ] Light approved.
- [ ] PC approved.
- [ ] Mobile approved.
- [ ] Production data tested.
- [ ] `VERSION.txt` updated.
- [ ] JS/CSS asset version updated.
- [ ] Git commit exists.
- [ ] HawkHost package matches Git version.
- [ ] Previous release can be restored.
