from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import market_session_guard as guard

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

cases = [
    ("2026-08-28T10:00:00", True, "normal Friday"),
    ("2026-08-29T10:00:00", False, "Saturday"),
    ("2026-08-31T10:00:00", False, "National Day holiday"),
    ("2026-09-01T10:00:00", False, "National Day holiday"),
    ("2026-09-02T10:00:00", False, "National Day holiday"),
    ("2026-09-03T10:00:00", True, "market reopens"),
]

failed = 0
for raw, expected, label in cases:
    dt = datetime.fromisoformat(raw).replace(tzinfo=TZ)
    actual = guard.is_market_slot(dt)
    print(f"{raw} | {label:24s} | expected={expected} actual={actual}")
    if actual != expected:
        failed += 1

cutoff_cases = [
    ("2026-08-28T20:00:00", "2026-08-29"),
    ("2026-08-31T20:00:00", "2026-08-29"),
    ("2026-09-01T01:00:00", "2026-08-29"),
    ("2026-09-02T20:00:00", "2026-08-29"),
    ("2026-09-03T10:00:00", "2026-08-29"),
    ("2026-09-03T16:00:00", "2026-09-04"),
]
for raw, expected in cutoff_cases:
    dt = datetime.fromisoformat(raw).replace(tzinfo=TZ)
    actual = guard.history_exclusive_date(dt).isoformat()
    print(f"cutoff {raw} | expected={expected} actual={actual}")
    if actual != expected:
        failed += 1


rollover_cases = [
    ("2026-01-01T10:00:00", False, "New Year holiday"),
    ("2026-01-02T10:00:00", False, "Jan-2 added holiday"),
    ("2026-01-05T10:00:00", True, "first 2026 trading Monday"),
]
for raw, expected, label in rollover_cases:
    dt = datetime.fromisoformat(raw).replace(tzinfo=TZ)
    actual = guard.is_market_slot(dt)
    print(f"{raw} | {label:24s} | expected={expected} actual={actual}")
    if actual != expected:
        failed += 1

jan_cutoff = datetime.fromisoformat("2026-01-05T10:00:00").replace(tzinfo=TZ)
jan_actual = guard.last_completed_trading_date(jan_cutoff).isoformat()
print(f"last completed 2026-01-05T10:00:00 | expected=2025-12-31 actual={jan_actual}")
if jan_actual != "2025-12-31":
    failed += 1

# Future-year fail closed.
future = datetime(2027, 1, 4, 10, 0, tzinfo=TZ)
if guard.is_market_slot(future):
    print("ERROR: uncovered 2027 calendar unexpectedly allowed trading.")
    failed += 1
else:
    print("2027 uncovered calendar: correctly FAIL-CLOSED.")

if failed:
    raise SystemExit(f"FAILED: {failed} checks")
print("PASS: Market Session Guard deterministic checks.")
