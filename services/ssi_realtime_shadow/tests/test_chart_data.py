from __future__ import annotations

from pathlib import Path

import pytest

from app.canonical_market_store import CanonicalMarketStore, MinuteBar
from app.chart_data import ChartDataStore


def _bar(
    *,
    day: str,
    minute: str,
    source: str = "SSI_REST",
    quality: str = "TRUSTED",
    finalized: int = 1,
    open_price: float | None = 10.0,
    high: float | None = 11.0,
    low: float | None = 9.0,
    close: float | None = 10.5,
    volume: int | None = 100,
) -> MinuteBar:
    return MinuteBar(
        symbol="HPG",
        trading_date=day,
        minute=minute,
        exchange="HOSE",
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source=source,
        quality_status=quality,
        is_finalized=finalized,
    )


def _seed(market_dir: Path, *rows: MinuteBar) -> None:
    with CanonicalMarketStore(market_dir) as store:
        store.upsert_minute_bars(rows)


def test_single_year_canonical_query_and_source_counts(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        _bar(day="2026-09-18", minute="09:00", source="SSI_REST"),
        _bar(
            day="2026-09-18", minute="09:01", source="SSI_STREAM",
            finalized=0, close=10.8,
        ),
    )
    result = ChartDataStore(tmp_path).query(
        symbol="hpg", date_from="2026-09-18", date_to="2026-09-18"
    )
    assert [(bar.minute, bar.close) for bar in result.bars] == [
        ("09:00", 10.5), ("09:01", 10.8)
    ]
    assert result.source_counts == {"SSI_REST": 1, "SSI_STREAM": 1}
    assert result.invalid_ohlc_dropped == 0


def test_cross_year_query_opens_required_shards_and_orders_rows(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        _bar(day="2025-12-31", minute="14:30", close=9.5),
        _bar(day="2026-01-02", minute="09:00", close=10.5),
    )
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2025-12-20", date_to="2026-01-10"
    )
    assert [(bar.trading_date, bar.minute) for bar in result.bars] == [
        ("2025-12-31", "14:30"), ("2026-01-02", "09:00")
    ]
    assert {path.name for path in tmp_path.glob("*.db")} == {
        "ccc_market_2025.db", "ccc_market_2026.db"
    }


def test_missing_year_shard_contributes_no_rows_and_is_not_created(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, _bar(day="2026-01-02", minute="09:00"))
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2025-12-20", date_to="2026-01-10"
    )
    assert len(result.bars) == 1
    assert not (tmp_path / "ccc_market_2025.db").exists()


def test_usable_unfinalized_current_minute_is_public_evidence(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        _bar(
            day="2026-10-02", minute="10:17", source="SSI_STREAM",
            quality="PARTIAL", finalized=0,
        ),
    )
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02"
    )
    assert len(result.bars) == 1
    assert result.bars[0].quality_status == "PARTIAL"


@pytest.mark.parametrize(
    "changes",
    [
        {"open_price": None}, {"high": None}, {"low": None},
        {"close": None}, {"volume": None},
    ],
)
def test_structurally_incomplete_rows_are_omitted_without_fabrication(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    _seed(tmp_path, _bar(day="2026-10-02", minute="10:17", **changes))
    store = ChartDataStore(tmp_path)
    default = store.query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02"
    )
    included = store.query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02",
        include_invalid=True,
    )
    assert default.bars == included.bars == ()
    assert default.invalid_ohlc_dropped == included.invalid_ohlc_dropped == 1


def test_complete_invalid_ohlc_is_filtered_or_explicitly_exposed(
    tmp_path: Path,
) -> None:
    _seed(
        tmp_path,
        _bar(
            day="2026-10-02", minute="10:17", open_price=12, high=11,
            low=9, close=10, quality="PARTIAL",
        ),
    )
    store = ChartDataStore(tmp_path)
    filtered = store.query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02"
    )
    included = store.query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02",
        include_invalid=True,
    )
    assert filtered.bars == ()
    assert filtered.invalid_ohlc_dropped == 1
    assert len(included.bars) == 1
    assert included.bars[0].quality_status == "INVALID_OHLC"


@pytest.mark.parametrize(
    ("resolution", "expected_minute"),
    [(5, "10:15"), (15, "10:15"), (30, "10:00"), (60, "10:00")],
)
def test_intraday_aggregation_resolutions(
    tmp_path: Path, resolution: int, expected_minute: str
) -> None:
    _seed(
        tmp_path,
        _bar(
            day="2026-10-02", minute="10:16", open_price=10, high=11,
            low=9, close=10.5, volume=100,
        ),
        _bar(
            day="2026-10-02", minute="10:17", open_price=10.5, high=12,
            low=10, close=11.5, volume=200, quality="LATE_CORRECTION",
        ),
    )
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02",
        resolution=resolution,
    )
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert (bar.minute, bar.open, bar.high, bar.low, bar.close, bar.volume) == (
        expected_minute, 10, 12, 9, 11.5, 300
    )
    assert bar.quality_status == "LATE_CORRECTION"


def test_daily_resolution_aggregates_canonical_minutes(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        _bar(day="2026-10-01", minute="09:00", close=10, volume=100),
        _bar(
            day="2026-10-01", minute="14:45", open_price=10, high=13,
            low=8, close=12, volume=250,
        ),
        _bar(day="2026-10-02", minute="09:00", close=11, volume=120),
    )
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2026-10-01", date_to="2026-10-02",
        resolution=1440,
    )
    assert len(result.bars) == 2
    assert result.bars[0].minute == "09:00"
    assert result.bars[0].close == 12
    assert result.bars[0].volume == 350


@pytest.mark.parametrize(
    "quality",
    [
        "TRUSTED", "PARTIAL", "MISSING_PRICE", "MISSING_VOLUME",
        "VOLUME_REGRESSION", "LATE_CORRECTION", "FUTURE_UNKNOWN",
    ],
)
def test_canonical_quality_statuses_aggregate_without_error(
    tmp_path: Path, quality: str
) -> None:
    _seed(tmp_path, _bar(day="2026-10-02", minute="10:17", quality=quality))
    result = ChartDataStore(tmp_path).query(
        symbol="HPG", date_from="2026-10-02", date_to="2026-10-02",
        resolution=5,
    )
    assert result.bars[0].quality_status == quality
