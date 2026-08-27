CCC GOLDEN BOARD v19.12.0 — LOCAL PREVIEW

STATUS
- Production HawkHost remains v19.11.4. DO NOT upload this preview to production yet.
- Supabase Golden Board backend migration 20260826174318 is ALREADY APPLIED.
- Do NOT run the migration SQL again manually. The SQL file is included only so Git matches the database migration history.
- The database trigger starts collecting automatically on future stock_snapshot writes.
- No historical fake/backfill rows were inserted.

APPLY TO LOCAL REPO
1. Confirm GitHub Desktop current branch: feature/golden-board
2. Copy the contents of this ZIP into the repository root.
3. Allow overwrite for:
   website-next/index.html
   website-next/VERSION.txt
4. New files/directories are added automatically.
5. Review Changes in GitHub Desktop before committing.

LOCAL TEST
From the repository's website-next folder, run a local static server, for example:
  py -m http.server 8080

Open:
  http://localhost:8080/
  http://localhost:8080/bang-vang/

EXPECTED TONIGHT
The real Golden Board may be empty because collection was enabled after the 26/08 trading session.
The first genuine records will be created by the next stock_snapshot updates when a symbol is recorded at 4/4.

WHAT THIS PREVIEW ADDS
- Desktop left-menu Bảng vàng
- Mobile bottom-menu Bảng vàng (Guide remains in header ?)
- Overview Bảng vàng teaser/widget
- /bang-vang/ page
- Guest: market count + max 2 real delayed symbols
- Member: full rows inside entitled/watchlist scope
- VIP/full market: all Golden Board rows
- Daily history selector
- Current/latest signal state saved after a symbol entered the board
- hit_count and retry-safe distinct time slots
- longest consecutive 5-minute 4/4 streak
- weekly ranking summary
- rvol30_sessions saved as metadata only; never blocks admission

DO NOT
- Do not upload website-next preview files to HawkHost production.
- Do not merge feature/golden-board to release until Product Owner explicitly approves.
- Do not re-run the included migration just because it appears in the patch.
