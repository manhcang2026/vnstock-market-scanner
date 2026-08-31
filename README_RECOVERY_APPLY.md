# Stage 2B — Apply fake-session recovery

This stage is intentionally separate from the read-only dry run.

## Preconditions

The Stage 2 v1.1 dry run MUST print:

- 800 reconstructed rows
- 4/4 = 3
- >=3 = 21
- >=2 = 89
- RVOL30 >=200% = 137
- 4/4 = BVS, SSB, TLP
- Golden Board EOD 4/4 = BVS, SSB, TLP
- invalid intraday rows = 44,800
- fake stock_snapshot = 800
- EOD 31/08 vs 28/08 price+volume = 800/800
- `DRY RUN PASS — NOTHING WAS WRITTEN`

## Safety design

The apply script:

1. refuses to write unless `--apply` is supplied;
2. reruns the entire dry-run audit immediately before writes;
3. accepts only the known database states;
4. requires an interactive confirmation token;
5. makes a local gzip backup under:
   `~/ccc-recovery-backups/`
6. restores `stock_snapshot` to audited 28/08 15:00 values;
7. preserves Golden Board exactly:
   - `stock_snapshot` has a Golden Board trigger;
   - the script backs up 28/08 Golden Board rows first;
   - after stock restore, it writes the original Golden Board rows back;
   - it verifies the history rows match before deleting fake intraday data;
8. deletes ONLY:
   `intraday_snapshots.trading_date = 2026-08-31`;
9. leaves `scan_runs` untouched for audit history;
10. verifies final KPI and row counts.

## Important

Do not run the apply command until this code has been committed/pushed to the
recovery branch and reviewed.

The apply command is intentionally not included in this README's quick-start.
Follow the guided recovery steps in chat so each checkpoint can be verified.
