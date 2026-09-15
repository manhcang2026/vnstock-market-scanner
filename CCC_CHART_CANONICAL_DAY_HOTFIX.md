# CCC Chart canonical-day hotfix

Fixes Chart Data merge semantics:

- `PASS` / `REST_PASS`: history is canonical for the whole trading day.
- Realtime does not fill missing minutes on canonical days.
- Historical `SSI_REST` / `SSI_STREAM_FINAL` dates created before finalize metadata existed are also treated as canonical.
- Explicit `BLOCKED` / `REST_BLOCKED` days may still use realtime fill.
- Current/unfinalized days continue to use realtime normally.

Files:
- `services/ssi_realtime_shadow/app/chart_data.py`
- `services/ssi_realtime_shadow/tests/test_chart_data.py`
