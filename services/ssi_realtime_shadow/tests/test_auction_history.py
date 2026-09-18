from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from app.auction_history import (
    CLOSE_AUCTION,
    CROSS_PROVIDER_PROOF,
    INFERRED_BOUNDARY,
    MIXED,
    PROVEN,
    SSI_REST,
    SSI_STREAM,
    UNAVAILABLE,
    AuctionHistoryConflict,
    AuctionHistoryRow,
    approved_inferred_row,
    bootstrap_auction_history,
    read_atc_exact10,
    store_auction_history_row,
)
from app.market_storage_schema import ensure_market_storage_schema


NOW = "2026-09-18T19:00:00+07:00"
DATES = (
    "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
    "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
)


@pytest.fixture
def market_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(connection, applied_at=NOW)
    try:
        yield connection
    finally:
        connection.close()


def _row(
    trading_date: str = "2026-09-17",
    *,
    quality: str = INFERRED_BOUNDARY,
    volume: int = 1_887_000,
) -> AuctionHistoryRow:
    proven = quality == PROVEN
    return AuctionHistoryRow(
        symbol="FPT",
        trading_date=trading_date,
        exchange="HOSE",
        auction_type=CLOSE_AUCTION,
        auction_price=74_300,
        pre_auction_price=74_000,
        auction_volume=volume,
        provider_session="ATC" if proven else None,
        source=SSI_STREAM if proven else SSI_REST,
        quality=quality,
        proof_code=None if proven else CROSS_PROVIDER_PROOF,
        finalized=True,
    )


def _evidence(dates: tuple[str, ...] | list[str]):
    history = sqlite3.connect(":memory:")
    daily = sqlite3.connect(":memory:")
    history.execute(
        "CREATE TABLE minute_bars (trading_date TEXT, data_source TEXT, exchange TEXT)"
    )
    daily.execute(
        "CREATE TABLE daily_bars (trading_date TEXT, source TEXT, quality_status TEXT)"
    )
    history.executemany(
        "INSERT INTO minute_bars VALUES (?, 'SSI_REST', 'HOSE')",
        [(item,) for item in dates],
    )
    daily.executemany(
        "INSERT INTO daily_bars VALUES (?, 'SSI_DAILY_OHLC', 'TRUSTED')",
        [(item,) for item in dates],
    )
    return history, daily


def _insert_many(
    connection: sqlite3.Connection,
    dates: tuple[str, ...] | list[str],
    quality: str,
) -> None:
    for trading_date in dates:
        store_auction_history_row(
            connection,
            _row(trading_date, quality=quality, volume=1_000),
            recorded_at=NOW,
        )


def _proof_record(**overrides):
    record = {
        "symbol": "FPT",
        "trading_date": "2026-09-17",
        "classification": "CONFIRMED_INFERRED_BOUNDARY",
        "quality": INFERRED_BOUNDARY,
        "proof": CROSS_PROVIDER_PROOF,
        "source": SSI_REST,
        "failure_reasons": "[]",
        "ssi_boundary_price": "74300",
        "ssi_last_continuous_price": "74000",
        "ssi_boundary_volume": "1887000",
    }
    record.update(overrides)
    return record


def test_inferred_insert(market_db: sqlite3.Connection) -> None:
    assert store_auction_history_row(market_db, _row(), recorded_at=NOW) == "INSERTED"
    assert market_db.execute("SELECT COUNT(*) FROM auction_session_history").fetchone()[0] == 1


def test_identical_inferred_rerun_is_noop(market_db: sqlite3.Connection) -> None:
    store_auction_history_row(market_db, _row(), recorded_at=NOW)
    assert store_auction_history_row(market_db, _row(), recorded_at=NOW) == "ALREADY_IDENTICAL"


def test_conflicting_inferred_is_rejected(market_db: sqlite3.Connection) -> None:
    store_auction_history_row(market_db, _row(), recorded_at=NOW)
    with pytest.raises(AuctionHistoryConflict):
        store_auction_history_row(
            market_db, replace(_row(), auction_volume=1_887_001), recorded_at=NOW
        )


def test_inferred_cannot_overwrite_proven(market_db: sqlite3.Connection) -> None:
    store_auction_history_row(market_db, _row(quality=PROVEN), recorded_at=NOW)
    outcome = store_auction_history_row(market_db, _row(), recorded_at=NOW)
    assert outcome == "PROTECTED_PROVEN"
    assert market_db.execute("SELECT quality FROM auction_session_history").fetchone()[0] == PROVEN


def test_proven_precedence_over_inferred(market_db: sqlite3.Connection) -> None:
    store_auction_history_row(market_db, _row(), recorded_at=NOW)
    outcome = store_auction_history_row(
        market_db, _row(quality=PROVEN), recorded_at="2026-09-19T15:00:00+07:00"
    )
    assert outcome == "SUPERSEDED"
    assert market_db.execute("SELECT quality FROM auction_session_history").fetchone()[0] == PROVEN


def test_provenance_is_retained_on_supersession(market_db: sqlite3.Connection) -> None:
    store_auction_history_row(market_db, _row(), recorded_at=NOW)
    store_auction_history_row(
        market_db, _row(quality=PROVEN), recorded_at="2026-09-19T15:00:00+07:00"
    )
    stored = market_db.execute(
        "SELECT previous_source, previous_quality, previous_proof_code, superseded_at "
        "FROM auction_session_history"
    ).fetchone()
    assert stored[:3] == (SSI_REST, INFERRED_BOUNDARY, CROSS_PROVIDER_PROOF)
    assert stored[3] == "2026-09-19T15:00:00+07:00"


def test_only_confirmed_beta04b_rows_are_accepted() -> None:
    assert approved_inferred_row(_proof_record()) is not None
    assert approved_inferred_row(_proof_record(classification="UNCONFIRMED_BOUNDARY")) is None
    assert approved_inferred_row(_proof_record(proof="OTHER")) is None


def test_no_ato_bootstrap() -> None:
    assert approved_inferred_row(_proof_record(auction_type="OPEN_AUCTION")) is None


def test_exact_10_all_inferred(market_db: sqlite3.Connection) -> None:
    _insert_many(market_db, DATES, INFERRED_BOUNDARY)
    history, daily = _evidence(DATES)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert result.sessions_used == 10
    assert result.inferred_sessions == 10
    assert result.baseline_quality == INFERRED_BOUNDARY
    assert result.baseline_usable


def test_exact_10_mixed_proven_and_inferred(market_db: sqlite3.Connection) -> None:
    _insert_many(market_db, DATES, INFERRED_BOUNDARY)
    for trading_date in DATES[-5:]:
        store_auction_history_row(
            market_db, _row(trading_date, quality=PROVEN, volume=1_000), recorded_at=NOW
        )
    history, daily = _evidence(DATES)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert (result.proven_sessions, result.inferred_sessions) == (5, 5)
    assert result.baseline_quality == MIXED


def test_exact_10_all_proven(market_db: sqlite3.Connection) -> None:
    _insert_many(market_db, DATES, PROVEN)
    history, daily = _evidence(DATES)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert result.proven_sessions == 10
    assert result.baseline_quality == PROVEN
    assert result.baseline_usable


def test_exact_candidate_missing_is_unavailable(market_db: sqlite3.Connection) -> None:
    _insert_many(market_db, DATES[:-1], INFERRED_BOUNDARY)
    history, daily = _evidence(DATES)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert result.sessions_used == 9
    assert result.missing_sessions == (DATES[-1],)
    assert result.avg_closing_auction_volume is None
    assert result.baseline_quality == UNAVAILABLE


def test_no_11th_substitution(market_db: sqlite3.Connection) -> None:
    dates = ("2026-09-03", *DATES)
    _insert_many(market_db, dates, INFERRED_BOUNDARY)
    market_db.execute(
        "DELETE FROM auction_session_history WHERE trading_date=?", (DATES[4],)
    )
    history, daily = _evidence(dates)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert result.candidate_dates == DATES
    assert "2026-09-03" not in result.candidate_dates
    assert result.sessions_used == 9


def test_old_inferred_history_is_retained_outside_active_window(
    market_db: sqlite3.Connection,
) -> None:
    old_dates = [f"2026-08-{day:02d}" for day in range(10, 20)]
    new_dates = [f"2026-09-{day:02d}" for day in range(1, 11)]
    _insert_many(market_db, old_dates, INFERRED_BOUNDARY)
    _insert_many(market_db, new_dates, PROVEN)
    history, daily = _evidence(old_dates + new_dates)
    result = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-30"
    )
    assert result.proven_sessions == 10
    assert result.baseline_quality == PROVEN
    assert market_db.execute("SELECT COUNT(*) FROM auction_session_history").fetchone()[0] == 20
    assert market_db.execute(
        "SELECT COUNT(*) FROM auction_session_history WHERE quality=?",
        (INFERRED_BOUNDARY,),
    ).fetchone()[0] == 10


def test_fpt_20260917_fixture(market_db: sqlite3.Connection) -> None:
    row = approved_inferred_row(_proof_record())
    assert row is not None
    store_auction_history_row(market_db, row, recorded_at=NOW)
    stored = market_db.execute(
        "SELECT auction_price, pre_auction_price, auction_volume, quality, source, proof_code "
        "FROM auction_session_history"
    ).fetchone()
    assert tuple(stored) == (
        74_300,
        74_000,
        1_887_000,
        INFERRED_BOUNDARY,
        SSI_REST,
        CROSS_PROVIDER_PROOF,
    )


def test_dry_run_performs_zero_mutation(market_db: sqlite3.Connection) -> None:
    report = bootstrap_auction_history(
        market_db, [_row()], recorded_at=NOW, dry_run=True
    )
    assert report.would_insert == 1
    assert market_db.execute("SELECT COUNT(*) FROM auction_session_history").fetchone()[0] == 0


def test_exact10_lifecycle_evolves_without_deleting_inferred_history(
    market_db: sqlite3.Connection,
) -> None:
    old_dates = list(DATES)
    future_dates = [f"2026-09-{day:02d}" for day in range(21, 31)]
    _insert_many(market_db, old_dates, INFERRED_BOUNDARY)
    history, daily = _evidence(old_dates)

    initial = read_atc_exact10(
        market_db, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert (initial.proven_sessions, initial.inferred_sessions) == (0, 10)
    assert initial.baseline_quality == INFERRED_BOUNDARY

    checkpoints = {
        1: (1, 9, MIXED),
        5: (5, 5, MIXED),
        10: (10, 0, PROVEN),
    }
    for index, trading_date in enumerate(future_dates, start=1):
        store_auction_history_row(
            market_db,
            _row(trading_date, quality=PROVEN, volume=1_000),
            recorded_at=NOW,
        )
        if index in checkpoints:
            history.close()
            daily.close()
            history, daily = _evidence(old_dates + future_dates[:index])
            result = read_atc_exact10(
                market_db,
                history,
                daily,
                symbol="FPT",
                as_of_date="2026-10-01",
            )
            expected_proven, expected_inferred, expected_quality = checkpoints[index]
            assert (result.proven_sessions, result.inferred_sessions) == (
                expected_proven,
                expected_inferred,
            )
            assert result.baseline_quality == expected_quality

    history.close()
    daily.close()

    assert market_db.execute(
        "SELECT COUNT(*) FROM auction_session_history WHERE quality=?",
        (INFERRED_BOUNDARY,),
    ).fetchone()[0] == 10
