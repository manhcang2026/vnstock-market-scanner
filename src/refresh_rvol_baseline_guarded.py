from __future__ import annotations

import refresh_rvol_baseline as job
import market_session_guard


# refresh_rvol30_baseline RPC expects an exclusive date.
job.rvol_as_of_date = market_session_guard.history_exclusive_date


if __name__ == "__main__":
    job.main()
