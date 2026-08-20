# CCC UI/UX QA CHECKLIST v1.0

**Parent standard:** `CCC_UIUX_MASTER.md`  
**Purpose:** Release gate for new screens and meaningful UI changes.

A UI task is not complete just because it looks correct in one screenshot.

---

# A. Product intent

- [ ] The primary job of the screen is written and clear.
- [ ] The most important information supports that job.
- [ ] Secondary information does not compete with primary information.
- [ ] The screen does not invent features or data that the backend does not provide.
- [ ] Future-only functionality is clearly separated from production functionality.

---

# B. Data correctness and trust

- [ ] Realistic production-like data was used for testing.
- [ ] Null/missing values are not displayed as zero unless zero is correct.
- [ ] “Chưa đủ dữ liệu” is distinct from “0”.
- [ ] Market/data update time is available when relevant.
- [ ] LIVE/DEMO/degraded/error status is correctly represented.
- [ ] Missing-data state is visible when relevant.
- [ ] Stale data has a distinct state when applicable.
- [ ] Data source/audit information is available where users need to verify trust.
- [ ] Refresh does not unnecessarily blank previously usable data.

---

# C. Scanner logic

- [ ] The four current signals are represented accurately.
- [ ] Signal count matches the underlying signal states.
- [ ] Signal UI does not imply buy/sell advice.
- [ ] CCC Signal Rail uses more than color to communicate state.
- [ ] Filter labels match actual filter logic.
- [ ] Sort labels match actual sort logic.
- [ ] Search behavior matches the real searchable fields.
- [ ] Watchlist/display actions do not modify the backend scanner universe.

---

# D. Readability

- [ ] Essential text is not dependent on 10–11px sizing.
- [ ] Mobile body text is comfortably readable.
- [ ] Stock symbol and primary metrics are visually prominent.
- [ ] Technical abbreviations are explained at an appropriate layer.
- [ ] Numeric values use tabular numerals where comparison matters.
- [ ] Numeric table columns are aligned consistently.
- [ ] Labels do not wrap or truncate in a way that changes meaning.
- [ ] Hierarchy remains understandable if semantic colors are removed.

---

# E. Color and tokens

- [ ] Semantic tokens are used instead of random raw colors.
- [ ] Market green/red only describes market state.
- [ ] Color is not the only cue for success/error/signal state.
- [ ] Contrast is sufficient in light mode.
- [ ] Contrast is sufficient in dark mode if the changed component supports it.
- [ ] No unnecessary gradient/glass effect reduces financial-data clarity.
- [ ] New tokens are added to the system rather than duplicated locally.

---

# F. Layout — mobile 375px

- [ ] No unintended horizontal page scroll.
- [ ] Search is easy to access.
- [ ] Filter/sort controls are touch-friendly.
- [ ] Important touch targets are approximately 44–48px where practical.
- [ ] Stock cards show decision information before secondary metrics.
- [ ] Dense desktop tables are not merely squeezed into mobile.
- [ ] Bottom sheet/dialog content remains usable with device/browser chrome.
- [ ] Long stock names/labels have a deliberate overflow strategy.

---

# G. Layout — tablet 768px

- [ ] Layout is deliberately designed, not an accidental desktop/mobile breakpoint.
- [ ] Cards/table choice is appropriate for available width.
- [ ] Filter controls remain understandable.
- [ ] Detail interaction fits the device.
- [ ] No awkward large empty zones or cramped columns.

---

# H. Layout — 1024px

- [ ] Main analysis layout is usable.
- [ ] Table columns remain readable.
- [ ] Command bar does not wrap unpredictably.
- [ ] Navigation remains clear.
- [ ] Side detail/drawer, if present, leaves enough usable scanner width.

---

# I. Layout — desktop 1440px

- [ ] Information density uses the available width effectively.
- [ ] Content is not artificially constrained to a narrow marketing column.
- [ ] Table header remains understandable.
- [ ] Primary scanner controls are immediately available.
- [ ] Long rows/lists have an appropriate scrolling strategy.

---

# J. Interaction

- [ ] Mouse interaction works.
- [ ] Touch interaction works where relevant.
- [ ] Keyboard focus is visible.
- [ ] Keyboard-focusable row/card actions can be activated with Enter/Space or semantic controls.
- [ ] Icon-only controls have accessible labels.
- [ ] No essential action is hover-only.
- [ ] Opening/closing stock detail preserves scanner state when practical.
- [ ] Filters do not unexpectedly reset sort/search.
- [ ] Sorting has a clear active state.

---

# K. Loading / empty / error

- [ ] Loading state is designed.
- [ ] Refresh state is designed.
- [ ] Empty search state is designed.
- [ ] Empty filter-result state is designed.
- [ ] Error state explains the problem in user language.
- [ ] Retry/recovery is offered when useful.
- [ ] Missing data is not confused with an application error.
- [ ] Layout remains stable while loading.

---

# L. Performance

- [ ] Search typing is responsive.
- [ ] Filter changes do not freeze the UI.
- [ ] Large lists have a documented rendering strategy.
- [ ] Expensive filtering/search is optimized/debounced where needed.
- [ ] Unrelated parts of the page do not re-render unnecessarily.
- [ ] Detail opens without waiting for unrelated work.
- [ ] Skeleton/loading UI does not cause major layout shift.
- [ ] Motion does not delay reading or interaction.

---

# M. Accessibility

- [ ] Semantic HTML is used where practical.
- [ ] Dialog/sheet focus behavior is correct.
- [ ] Escape/close behavior is predictable.
- [ ] Reading order is logical.
- [ ] Status is not color-only.
- [ ] Contrast is acceptable.
- [ ] Touch targets are usable.
- [ ] Reduced motion is respected where relevant.
- [ ] Table structure uses actual table semantics when data is tabular.

---

# N. Copy and product language

- [ ] Copy is understandable to non-specialists.
- [ ] Jargon is not used when a clearer Vietnamese label exists.
- [ ] Technical details remain available for advanced users.
- [ ] No copy promises investment outcomes.
- [ ] Scanner conditions are not worded as buy/sell recommendations.
- [ ] Disclaimer is shown where appropriate without dominating the product.

---

# O. Component consistency

- [ ] Existing shared component was reused when appropriate.
- [ ] No new one-off button/chip/card visual language was introduced.
- [ ] Spacing follows the system rhythm.
- [ ] Radius/shadow usage is consistent.
- [ ] New component states are documented if reusable.
- [ ] `CCC_COMPONENT_RULES.md` is updated if a new reusable pattern is introduced.

---

# P. Page pattern consistency

- [ ] The page follows the relevant pattern in `CCC_PAGE_PATTERNS.md`.
- [ ] Any intentional deviation has a product reason.
- [ ] A major pattern change is documented before implementation.
- [ ] Future pages do not copy a layout that was designed for a different primary job.

---

# Q. Lovable gate

Complete only if Lovable was involved.

- [ ] Lovable use was proposed before calling it.
- [ ] The product owner explicitly approved the use.
- [ ] The task was appropriate for Lovable's strengths.
- [ ] The generated design was reviewed against CCC MASTER.
- [ ] Lovable output did not override data logic or accessibility requirements.
- [ ] Any reusable design decision was absorbed into the CCC system rather than left as an isolated generated style.

---

# R. Final release gate

- [ ] `CCC_UIUX_MASTER.md` has been followed.
- [ ] `CCC_COMPONENT_RULES.md` has been followed.
- [ ] Relevant `CCC_PAGE_PATTERNS.md` section has been followed.
- [ ] Real data/state testing is complete.
- [ ] 375 / 768 / 1024 / 1440 checks are complete.
- [ ] Accessibility blockers are resolved.
- [ ] Performance blockers are resolved.
- [ ] No backend scanner-universe behavior was accidentally changed by UI work.
- [ ] Product owner review items are resolved or explicitly deferred.
