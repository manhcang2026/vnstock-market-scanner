from pathlib import Path

from app.collector import QuoteCollector
from app.storage import SQLiteStore


def test_minute_volume_uses_cumulative_delta(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = SQLiteStore(db, commit_every_events=1, commit_every_seconds=1)
    collector = QuoteCollector({"HPG"}, store)

    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:10", "LastPrice": 27000, "TotalVol": 1000}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:20", "LastPrice": 27100, "TotalVol": 1200}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:40", "LastPrice": 26900, "TotalVol": 1250}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:01:05", "LastPrice": 27200, "TotalVol": 1500}
    )
    store.commit()

    rows = store._conn.execute(
        "SELECT minute, open, high, low, close, volume, last_total_volume, is_partial FROM minute_bars ORDER BY minute"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["minute"] == "09:00"
    assert rows[0]["open"] == 27000
    assert rows[0]["high"] == 27100
    assert rows[0]["low"] == 26900
    assert rows[0]["close"] == 26900
    assert rows[0]["volume"] == 250
    assert rows[0]["last_total_volume"] == 1250
    assert rows[0]["is_partial"] == 1

    assert rows[1]["minute"] == "09:01"
    assert rows[1]["volume"] == 250
    assert rows[1]["is_partial"] == 0
    store.close()


def test_outside_universe_is_ignored(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store)
    collector.on_message(
        {"Symbol": "VN30F1M", "TradingDate": "11/09/2026", "Time": "09:00:10", "LastPrice": 1800, "TotalVol": 10}
    )
    store.commit()
    count = store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
    assert count == 0
    assert collector.stats.ignored_outside_universe == 1
    store.close()
