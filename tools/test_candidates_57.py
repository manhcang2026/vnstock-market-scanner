from __future__ import annotations

import csv
import sys
from datetime import timedelta
from pathlib import Path
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import daily_baseline as daily
from common import now_vn

CANDIDATES = [
    "MVN",
    "DMX", "HTT", "HU3", "VE3", "FOC", "TNS", "CMN", "PXM",
    "AAM", "LBE", "TSB", "TXM", "JOS", "HEP", "MFS", "PSL",
    "PTV", "QNP", "SDK", "LM8", "EFI", "INN", "KTL", "CDR",
    "BTW", "LDP", "DTI", "HPP", "VTK", "ALV", "HAS", "TS3",
    "TGP", "YBM", "TA9", "PBP", "VIM", "SIV", "DC2", "VLS",
    "C32", "SLS", "DHA", "NSC", "DNM", "PGN", "TCW", "TCT",
    "SPD", "NSH", "SKH", "RCL", "LHC", "GIC", "TDB", "L35",
]

MAX_AGE_DAYS = 31
RETRY_DELAYS = (10, 30)
OUT = ROOT / "candidate_57_test_output"

def test_symbol(symbol: str, run_date):
    start = (run_date - timedelta(days=daily.LOOKBACK_DAYS)).isoformat()
    end = run_date.isoformat()
    last_error = ""

    for attempt in range(3):
        try:
            row = daily.calculate_symbol(
                symbol=symbol,
                exchange="UNKNOWN",
                start=start,
                end=end,
                run_date=run_date,
                updated_at=now_vn(),
            )
            tdate = daily.date.fromisoformat(row["trading_date"])
            age = (run_date - tdate).days
            vol = float(row.get("avg_volume_10") or 0)

            if age > MAX_AGE_DAYS:
                verdict = "FAIL_STALE"
            elif vol <= 0:
                verdict = "FAIL_ZERO_VOLUME"
            else:
                verdict = "PASS"

            return {
                "symbol": symbol,
                "verdict": verdict,
                "trading_date": row["trading_date"],
                "age_days": age,
                "previous_close": row.get("previous_close"),
                "avg_volume_10": row.get("avg_volume_10"),
                "ma10": row.get("ma10"),
                "ma200": row.get("ma200"),
                "source": row.get("source"),
                "error": "",
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                sleep(RETRY_DELAYS[attempt])

    return {
        "symbol": symbol,
        "verdict": "ERROR",
        "trading_date": "",
        "age_days": "",
        "previous_close": "",
        "avg_volume_10": "",
        "ma10": "",
        "ma200": "",
        "source": "",
        "error": last_error,
    }

def main():
    if len(CANDIDATES) != 57 or len(set(CANDIDATES)) != 57:
        raise RuntimeError("Danh sách phải đúng 57 mã duy nhất")

    daily.verify_vnstock_api_access()
    run_date = now_vn().date()
    OUT.mkdir(parents=True, exist_ok=True)

    results = []
    for i, symbol in enumerate(CANDIDATES, 1):
        print(f"[{i:02d}/57] {symbol}", flush=True)
        row = test_symbol(symbol, run_date)
        results.append(row)
        print(
            f"  {row['verdict']} | date={row['trading_date'] or '-'} "
            f"| age={row['age_days'] if row['age_days'] != '' else '-'} "
            f"| KLTB10={row['avg_volume_10'] if row['avg_volume_10'] != '' else '-'} "
            f"| source={row['source'] or '-'}",
            flush=True,
        )

    csv_path = OUT / "candidate_57_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    passed = [r for r in results if r["verdict"] == "PASS"]
    failed = [r for r in results if r["verdict"] != "PASS"]

    summary = [
        "# Kết quả test 57 mã",
        "",
        f"- Ngày test VN: {run_date.isoformat()}",
        f"- PASS: {len(passed)}/57",
        f"- Cần thay: {len(failed)}/57",
        "",
        "## Mã cần thay",
        "",
        ", ".join(r["symbol"] for r in failed) if failed else "Không có",
        "",
    ]
    (OUT / "candidate_57_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print("=" * 60)
    print(f"PASS: {len(passed)}/57")
    print(f"CẦN THAY: {len(failed)}/57")
    if failed:
        print("Danh sách:", ", ".join(f"{r['symbol']}[{r['verdict']}]" for r in failed))

if __name__ == "__main__":
    main()
