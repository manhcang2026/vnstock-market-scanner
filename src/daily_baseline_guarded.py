from __future__ import annotations

import daily_baseline_after_close as job
import market_session_guard


# Reuse the existing Daily Baseline engine but replace its weekday-only cutoff.
job.history_exclusive_date = market_session_guard.history_exclusive_date


if __name__ == "__main__":
    job.main()
