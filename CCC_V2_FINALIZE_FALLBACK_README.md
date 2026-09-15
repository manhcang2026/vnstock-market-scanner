# CCC V2 finalize fallback hotfix

This hotfix keeps strict realtime QA, then automatically rebuilds the day from SSI REST 1-minute data when realtime QA is blocked.

Observed validation case (2026-09-15):
- realtime: 642 symbols, 66,141 bars, 544 GAP rows clustered 13:00-13:03 after restart;
- REST: 642 matching symbols, 37,408 bars, 158 NoDataFound symbol/day outcomes;
- REST OHLC inconsistencies are preserved raw and reported, not treated as fatal; ChartDataStore already filters invalid OHLC by default.

Timer is moved to 16:05 VN to give SSI REST time to settle after market close.
