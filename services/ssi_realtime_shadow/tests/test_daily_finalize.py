from __future__ import annotations

import inspect
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import app.daily_finalize as daily_finalize_module
from app.auction import CLOSE_AUCTION, OPEN_AUCTION
from app.auction_history import (
    CROSS_PROVIDER_PROOF,
    INFERRED_BOUNDARY,
    PROVEN,
    SSI_REST,
    SSI_STREAM,
    AuctionHistoryRow,
    read_atc_exact10,
    read_ato_exact10,
    store_auction_history_row,
)
from app.daily_finalize import finalize_day, finalize_stream_day, yearly_history_path
from app.daily_history import DailyBar
from app.market_storage_schema import ensure_market_storage_schema
from app.storage import SCHEMA
from app.volume_baseline import (
    load_candidate_market_sessions,
    prove_replay_volume_session,
    prove_volume_session,
)


DAY = "2026-09-17"
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
NOW_TEXT = "2026-09-17T16:00:00+07:00"
DATES = (
    "2026-09-04",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
    "2026-09-11",
    "2026-09-14",
    "2026-09-15",
    "2026-09-16",
    "2026-09-17",
)


@dataclass(frozen=True)
class DbPaths:
    source: Path
    history: Path
    market: Path


def _make_paths(tmp_path: Path) -> DbPaths:
    paths = DbPaths(
        source=tmp_path / "ssi_shadow.db",
        history=tmp_path / "ssi_history_2026.db",
        market=tmp_path / "market.db",
    )
    for path in (paths.source, paths.history):
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA)
        connection.commit()
        connection.close()
    market = sqlite3.connect(paths.market)
    ensure_market_storage_schema(market, applied_at=NOW_TEXT)
    market.close()
    return paths


def _daily(symbol: str = "FPT", *, volume: int = 100) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=DAY,
        exchange="HOSE",
        open=100,
        high=105,
        low=99,
        close=103,
        volume=volume,
        value=volume * 103,
    )


def _insert_minute(
    path: Path,
    *,
    symbol: str = "FPT",
    minute: str = "14:45",
    volume: int = 100,
    quality: str = "TRUSTED",
    partial: int = 0,
    gap: int = 0,
    source: str = SSI_STREAM,
    close: float = 103,
    trading_date: str = DAY,
    exchange: str = "HOSE",
) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        INSERT INTO minute_bars (
            trading_date, minute, symbol, open, high, low, close, volume,
            last_total_volume, event_count, is_partial, exchange,
            quality_status, has_gap, gap_from, gap_to, data_source,
            provider_time, updated_at
        ) VALUES (?, ?, ?, 100, 105, 99, ?, ?, ?, 2, ?, ?, ?, ?,
                  NULL, NULL, ?, ?, ?)
        """,
        (
            trading_date,
            minute,
            symbol,
            close,
            volume,
            volume,
            partial,
            exchange,
            quality,
            gap,
            source,
            minute + ":00",
            trading_date + "T15:30:00+07:00",
        ),
    )
    connection.commit()
    connection.close()


def _insert_auction(
    path: Path,
    *,
    symbol: str = "FPT",
    auction_type: str = CLOSE_AUCTION,
    provider_session: str = "ATC",
    price: float = 103,
    volume: int = 40,
    quality: str = "TRUSTED",
    source: str = SSI_STREAM,
) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        INSERT INTO auction_session_buckets (
            symbol, trading_date, exchange, auction_type, provider_session,
            auction_price, pre_auction_price, auction_volume, start_total_volume,
            end_total_volume, event_count, out_of_order_events, first_event_at,
            last_event_at, quality_status, finalized, data_source, updated_at
        ) VALUES (?, ?, 'HOSE', ?, ?, ?, 102, ?, 60, 100, 2, 0,
                  ?, ?, ?, 1, ?, ?)
        """,
        (
            symbol,
            DAY,
            auction_type,
            provider_session,
            price,
            volume,
            DAY + "T14:30:00+07:00",
            DAY + "T14:45:00+07:00",
            quality,
            source,
            NOW_TEXT,
        ),
    )
    connection.commit()
    connection.close()


def _run(
    paths: DbPaths,
    *,
    bars: tuple[DailyBar, ...] = (_daily(),),
    dry_run: bool = False,
):
    return finalize_day(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
        daily_bars=bars,
        dry_run=dry_run,
        now=NOW,
    )


def _count(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    value = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    connection.close()
    return value


def _history_row(paths: DbPaths):
    connection = sqlite3.connect(paths.history)
    row = connection.execute(
        """
        SELECT data_source, quality_status, is_partial, has_gap, volume
        FROM minute_bars WHERE trading_date=? AND symbol='FPT'
        """,
        (DAY,),
    ).fetchone()
    connection.close()
    return row


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
        "INSERT INTO minute_bars VALUES (?, 'SSI_STREAM', 'HOSE')",
        [(value,) for value in dates],
    )
    daily.executemany(
        "INSERT INTO daily_bars VALUES (?, 'SSI_DAILY_OHLC', 'TRUSTED')",
        [(value,) for value in dates],
    )
    return history, daily


def _auction_history_row(
    trading_date: str,
    *,
    auction_type: str,
    quality: str,
) -> AuctionHistoryRow:
    inferred = quality == INFERRED_BOUNDARY
    return AuctionHistoryRow(
        symbol="FPT",
        trading_date=trading_date,
        exchange="HOSE",
        auction_type=auction_type,
        auction_price=103,
        pre_auction_price=102,
        auction_volume=100,
        provider_session=None if inferred else ("ATO" if auction_type == OPEN_AUCTION else "ATC"),
        source=SSI_REST if inferred else SSI_STREAM,
        quality=quality,
        proof_code=CROSS_PROVIDER_PROOF if inferred else None,
        finalized=True,
    )


def test_dry_run_performs_zero_mutation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    result = _run(paths, dry_run=True)
    assert result.status == "DRY_RUN_PASS"
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0
    assert _count(paths.market, "auction_session_history") == 0
    connection = sqlite3.connect(paths.history)
    journal = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_finalize_runs'"
    ).fetchone()
    connection.close()
    assert journal is None


def test_completed_trusted_session_finalizes(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    result = _run(paths)
    assert result.status == "PASS"
    assert result.symbols_trusted == 1
    assert result.minute_rows_inserted == 1


def test_healthy_stream_replaces_rest_blocked_and_finalizes_canonically(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _run(paths, bars=())
    connection = sqlite3.connect(paths.history)
    connection.execute(
        "UPDATE daily_finalize_runs SET status='REST_BLOCKED' WHERE trading_date=?",
        (DAY,),
    )
    connection.commit()
    connection.close()

    _insert_minute(
        paths.source, minute="09:00", volume=40, close=101, exchange="UPCOM"
    )
    _insert_minute(
        paths.source, minute="14:59", volume=60, close=104, exchange="UPCOM"
    )
    result = finalize_stream_day(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
        dry_run=False,
        now=NOW,
        minimum_symbols=1,
        minimum_minutes=2,
    )

    assert result.status == "PASS"
    assert (result.minute_rows_inserted, result.daily_rows_inserted) == (2, 1)
    market = sqlite3.connect(paths.market)
    market.row_factory = sqlite3.Row
    daily = market.execute(
        """
        SELECT open, high, low, close, volume, value, source, quality_status
        FROM daily_bars WHERE symbol='FPT' AND trading_date=?
        """,
        (DAY,),
    ).fetchone()
    assert tuple(daily) == (
        100.0,
        105.0,
        99.0,
        104.0,
        100,
        None,
        SSI_STREAM,
        "TRUSTED",
    )
    history = sqlite3.connect(paths.history)
    history.row_factory = sqlite3.Row
    assert history.execute(
        "SELECT status FROM daily_finalize_runs WHERE trading_date=?", (DAY,)
    ).fetchone()[0] == "PASS"
    assert prove_volume_session(
        history, market, symbol="FPT", trading_date=DAY
    ).proven
    history.close()
    market.close()


def test_insufficient_stream_with_rest_blocked_still_fails(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _run(paths, bars=())
    connection = sqlite3.connect(paths.history)
    connection.execute(
        "UPDATE daily_finalize_runs SET status='REST_BLOCKED' WHERE trading_date=?",
        (DAY,),
    )
    connection.commit()
    connection.close()
    _insert_minute(paths.source, minute="14:59", exchange="UPCOM")

    result = finalize_stream_day(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
        dry_run=False,
        now=NOW,
    )

    assert result.status == "BLOCKED"
    assert "STREAM_SYMBOLS<500" in result.symbols[0].reasons
    assert "STREAM_MINUTES<200" in result.symbols[0].reasons
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_stream_coverage_accepts_production_shape_and_exact_boundaries() -> None:
    minutes = [f"{9 + offset // 60:02d}:{offset % 60:02d}" for offset in range(268)]
    minutes.append("14:59")
    production_rows = {
        f"S{index:03d}": [{"minute": minutes[index % len(minutes)]}]
        for index in range(635)
    }
    production_rows["S000"] = [{"minute": minute} for minute in minutes]
    assert daily_finalize_module._stream_coverage_reasons(production_rows) == ()

    boundary_rows = {"FPT": [{"minute": "09:15"}, {"minute": "14:45"}]}
    assert daily_finalize_module._stream_coverage_reasons(
        boundary_rows, minimum_symbols=1, minimum_minutes=2
    ) == ()


def test_wrapper_keeps_rest_pass_idempotency_and_rest_as_fallback() -> None:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "ccc-ssi-daily-finalize-wrapper.sh"
    ).read_text(encoding="utf-8")
    assert '"$PREVIOUS_STATUS" == "REST_PASS"' in wrapper
    assert wrapper.index("--stream-primary") < wrapper.index("app.historical_bootstrap")
    assert "--market \"$MARKET_DB\"" in wrapper
    assert "--write" in wrapper


def test_finalized_minute_source_remains_ssi_stream(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _run(paths)
    assert _history_row(paths) == (SSI_STREAM, "TRUSTED", 0, 0, 100)


def test_identical_rerun_is_noop(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _run(paths)
    again = _run(paths)
    assert again.minute_rows_inserted == 0
    assert again.minute_rows_identical == 1
    assert _count(paths.history, "minute_bars") == 1


def test_existing_identical_ssi_rest_row_is_safe(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_minute(paths.history, source=SSI_REST)
    result = _run(paths)
    assert result.status == "PASS"
    assert result.minute_rows_identical == 1
    assert _history_row(paths)[0] == SSI_REST


def test_conflicting_existing_history_blocks(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_minute(paths.history, source=SSI_REST, close=104)
    result = _run(paths)
    assert result.status == "BLOCKED"
    assert result.minute_conflicts == 1
    assert _count(paths.market, "daily_bars") == 0


def test_missing_daily_ohlc_blocks_trusted_settlement(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    result = _run(paths, bars=())
    assert result.status == "BLOCKED"
    assert result.missing_daily_ohlc == 1
    assert _count(paths.history, "minute_bars") == 0


def test_daily_volume_mismatch_blocks(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, volume=99)
    result = _run(paths)
    assert result.volume_mismatches == 1
    assert result.symbols_blocked == 1
    assert _count(paths.history, "minute_bars") == 0


def test_unresolved_gap_blocks(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, gap=1, quality="GAP")
    result = _run(paths)
    assert result.unresolved_gaps == 1
    assert "UNRESOLVED_GAP" in result.symbols[0].reasons
    assert _count(paths.history, "minute_bars") == 0


def test_raw_event_anomaly_can_settle_trusted(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, quality="VOLUME_REGRESSION", partial=1)
    result = _run(paths)
    assert result.status == "PASS"
    assert result.event_anomaly_rows == 1
    assert "VOLUME_REGRESSION=1" in result.symbols[0].event_anomalies
    assert "IS_PARTIAL=1" in result.symbols[0].event_anomalies
    assert _history_row(paths) == (SSI_STREAM, "TRUSTED", 0, 0, 100)


def test_unresolved_event_anomaly_does_not_settle(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, quality="UNKNOWN_MARKET")
    result = _run(paths)
    assert "UNRESOLVED_EVENT_ANOMALY" in result.symbols[0].reasons
    assert _count(paths.history, "minute_bars") == 0


def test_daily_ohlc_is_persisted_idempotently(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    first = _run(paths)
    second = _run(paths)
    assert (first.daily_rows_inserted, second.daily_rows_existing) == (1, 1)
    assert _count(paths.market, "daily_bars") == 1


def test_atc_stream_bucket_creates_proven_history(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source)
    result = _run(paths)
    assert result.atc_proven_inserted == 1
    connection = sqlite3.connect(paths.market)
    row = connection.execute(
        "SELECT quality, source, provider_session FROM auction_session_history"
    ).fetchone()
    connection.close()
    assert row == (PROVEN, SSI_STREAM, "ATC")


def test_proven_atc_supersedes_inferred(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source)
    connection = sqlite3.connect(paths.market)
    store_auction_history_row(
        connection,
        _auction_history_row(DAY, auction_type=CLOSE_AUCTION, quality=INFERRED_BOUNDARY),
        recorded_at=NOW_TEXT,
    )
    connection.commit()
    connection.close()
    result = _run(paths)
    assert result.atc_proven_superseded == 1


def test_historical_inferred_provenance_is_retained(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source)
    connection = sqlite3.connect(paths.market)
    store_auction_history_row(
        connection,
        _auction_history_row(DAY, auction_type=CLOSE_AUCTION, quality=INFERRED_BOUNDARY),
        recorded_at=NOW_TEXT,
    )
    connection.commit()
    connection.close()
    _run(paths)
    connection = sqlite3.connect(paths.market)
    row = connection.execute(
        "SELECT previous_source, previous_quality, previous_proof_code "
        "FROM auction_session_history"
    ).fetchone()
    connection.close()
    assert row == (SSI_REST, INFERRED_BOUNDARY, CROSS_PROVIDER_PROOF)


def test_ato_requires_explicit_provider_session_evidence(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(
        paths.source, auction_type=OPEN_AUCTION, provider_session="ATO", price=101
    )
    result = _run(paths)
    assert result.ato_proven_inserted == 1
    connection = sqlite3.connect(paths.market)
    row = connection.execute(
        "SELECT auction_type, provider_session, quality FROM auction_session_history"
    ).fetchone()
    connection.close()
    assert row == (OPEN_AUCTION, "ATO", PROVEN)


def test_time_only_ato_inference_is_rejected(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source, auction_type=OPEN_AUCTION, provider_session="LO")
    result = _run(paths)
    assert result.ato_conflicts == 1
    assert _count(paths.market, "auction_session_history") == 0


def test_auction_rerun_is_idempotent(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source)
    _run(paths)
    again = _run(paths)
    assert (again.atc_proven_inserted, again.atc_proven_existing) == (0, 1)
    assert _count(paths.market, "auction_session_history") == 1


def test_exact10_atc_lifecycle_remains_correct(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    connection = sqlite3.connect(paths.market)
    for trading_date in DATES:
        store_auction_history_row(
            connection,
            _auction_history_row(
                trading_date,
                auction_type=CLOSE_AUCTION,
                quality=INFERRED_BOUNDARY,
            ),
            recorded_at=NOW_TEXT,
        )
    history, daily = _evidence(DATES)
    initial = read_atc_exact10(
        connection, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert (initial.proven_sessions, initial.inferred_sessions) == (0, 10)
    for trading_date in DATES[-5:]:
        store_auction_history_row(
            connection,
            _auction_history_row(
                trading_date, auction_type=CLOSE_AUCTION, quality=PROVEN
            ),
            recorded_at=NOW_TEXT,
        )
    mixed = read_atc_exact10(
        connection, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert (mixed.proven_sessions, mixed.inferred_sessions) == (5, 5)


def test_ato_coverage_starts_partial_and_grows_from_proven_only(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    connection = sqlite3.connect(paths.market)
    history, daily = _evidence(DATES)
    store_auction_history_row(
        connection,
        _auction_history_row(DATES[0], auction_type=OPEN_AUCTION, quality=PROVEN),
        recorded_at=NOW_TEXT,
    )
    partial = read_ato_exact10(
        connection, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert partial.sessions_used == 1
    assert not partial.baseline_usable
    for trading_date in DATES[1:]:
        store_auction_history_row(
            connection,
            _auction_history_row(
                trading_date, auction_type=OPEN_AUCTION, quality=PROVEN
            ),
            recorded_at=NOW_TEXT,
        )
    complete = read_ato_exact10(
        connection, history, daily, symbol="FPT", as_of_date="2026-09-18"
    )
    assert complete.sessions_used == 10
    assert complete.baseline_quality == PROVEN


def test_finalized_day_is_accepted_by_candidate_and_replay_readers(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _run(paths)
    history = sqlite3.connect(paths.history)
    history.row_factory = sqlite3.Row
    market = sqlite3.connect(paths.market)
    market.row_factory = sqlite3.Row
    old_dates = [f"2026-09-{day:02d}" for day in range(1, 11)]
    for trading_date in old_dates:
        history.execute(
            """
            INSERT INTO minute_bars (
                trading_date, minute, symbol, open, high, low, close, volume,
                last_total_volume, event_count, is_partial, exchange,
                quality_status, has_gap, gap_from, gap_to, data_source,
                provider_time, updated_at
            ) VALUES (?, '14:45', 'FPT', 100, 105, 99, 103, 100,
                      100, 1, 0, 'HOSE', 'TRUSTED', 0, NULL, NULL,
                      'SSI_REST', '14:45:00', ?)
            """,
            (trading_date, trading_date + "T15:30:00+07:00"),
        )
        market.execute(
            """
            INSERT INTO daily_bars (
                symbol, trading_date, exchange, open, high, low, close,
                volume, value, source, quality_status, finalized_at
            ) VALUES ('FPT', ?, 'HOSE', 100, 105, 99, 103, 100, 10300,
                      'SSI_DAILY_OHLC', 'TRUSTED', ?)
            """,
            (trading_date, NOW_TEXT),
        )
    history.commit()
    market.commit()
    candidates = load_candidate_market_sessions(
        history, market, as_of_date="2026-09-18", lookback=10
    )
    assert len(candidates) == 10
    assert candidates[-1] == DAY
    assert old_dates[0] not in candidates
    replay = prove_replay_volume_session(
        history, market, symbol="FPT", trading_date=DAY
    )
    assert replay.proven
    assert prove_volume_session(
        history, market, symbol="FPT", trading_date=DAY
    ).proven


def test_no_stream_final_semantic_source_remains_in_write_path() -> None:
    assert "SSI_STREAM_FINAL" not in inspect.getsource(daily_finalize_module)
    assert yearly_history_path(Path("data"), DAY) == Path("data/ssi_history_2026.db")


def test_one_failed_symbol_does_not_corrupt_valid_symbol(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, symbol="FPT")
    _insert_minute(paths.source, symbol="HPG")
    _insert_minute(paths.history, symbol="HPG", source=SSI_REST, close=104)
    result = _run(paths, bars=(_daily("FPT"), _daily("HPG")))
    assert result.status == "BLOCKED"
    assert (result.symbols_trusted, result.symbols_blocked) == (1, 1)
    connection = sqlite3.connect(paths.history)
    rows = connection.execute(
        "SELECT symbol, close FROM minute_bars ORDER BY symbol"
    ).fetchall()
    connection.close()
    assert rows == [("FPT", 103.0), ("HPG", 104.0)]


def test_finalize_journal_reports_accurate_counts_and_status(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, symbol="FPT")
    _insert_minute(paths.source, symbol="HPG", volume=90)
    result = _run(paths, bars=(_daily("FPT"), _daily("HPG")))
    assert result.status == "PARTIAL"
    assert (result.source_symbols, result.symbols_trusted, result.symbols_blocked) == (
        2,
        1,
        1,
    )
    assert result.volume_mismatches == 1
    connection = sqlite3.connect(paths.history)
    row = connection.execute(
        """
        SELECT status, source_rows, source_symbols, symbols_attempted,
               symbols_trusted, symbols_blocked, minute_rows_inserted,
               volume_mismatches, event_anomaly_rows
        FROM daily_finalize_runs WHERE trading_date=?
        """,
        (DAY,),
    ).fetchone()
    connection.close()
    assert row == ("PARTIAL", 2, 2, 2, 1, 1, 1, 1, 0)


def test_legacy_finalize_journal_is_migrated_additively(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    connection = sqlite3.connect(paths.history)
    connection.execute(
        """
        CREATE TABLE daily_finalize_runs (
            trading_date TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            inserted_rows INTEGER NOT NULL,
            history_rows INTEGER NOT NULL,
            symbols INTEGER NOT NULL,
            minutes INTEGER NOT NULL,
            partial_rows INTEGER NOT NULL,
            gap_rows INTEGER NOT NULL,
            invalid_ohlc_rows INTEGER NOT NULL,
            quality_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            finalized_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()
    _insert_minute(paths.source)
    result = _run(paths)
    assert result.status == "PASS"
    connection = sqlite3.connect(paths.history)
    row = connection.execute(
        "SELECT status, mode, inserted_rows, history_rows FROM daily_finalize_runs"
    ).fetchone()
    connection.close()
    assert row == ("PASS", "WRITE", 1, 1)
