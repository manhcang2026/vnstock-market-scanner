from __future__ import annotations

import inspect
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

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


def _daily(
    symbol: str = "FPT", *, volume: int = 100, exchange: str = "HOSE"
) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=DAY,
        exchange=exchange,
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
    source: str = SSI_REST,
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


def _count_symbol(path: Path, table: str, symbol: str) -> int:
    connection = sqlite3.connect(path)
    value = int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE symbol=?", (symbol,)
        ).fetchone()[0]
    )
    connection.close()
    return value


def _insert_daily_bar(path: Path, bar: DailyBar) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        INSERT INTO daily_bars (
            symbol, trading_date, exchange, open, high, low, close,
            volume, value, source, quality_status, finalized_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bar.symbol,
            bar.trading_date,
            bar.exchange,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.value,
            bar.source,
            bar.quality_status,
            NOW_TEXT,
        ),
    )
    connection.commit()
    connection.close()


def _insert_checkpoint_pair(
    paths: DbPaths,
    *,
    symbol: str,
    intraday_status: str,
    daily_status: str,
) -> None:
    connection = sqlite3.connect(paths.source)
    row_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM minute_bars WHERE symbol=? AND trading_date=?",
            (symbol, DAY),
        ).fetchone()[0]
    )
    connection.execute(
        """
        INSERT INTO historical_bootstrap_checkpoints (
            symbol, from_date, to_date, resolution, status, row_count,
            attempt_count, last_attempt_at, completed_at, error
        ) VALUES (?, ?, ?, 1, ?, ?, 1, ?, ?, ?)
        """,
        (
            symbol,
            DAY,
            DAY,
            intraday_status,
            row_count if intraday_status == "COMPLETED" else 0,
            NOW_TEXT,
            NOW_TEXT,
            "NoDataFound" if intraday_status == "NO_DATA" else None,
        ),
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS eod_daily_checkpoints (
            symbol TEXT NOT NULL,
            trading_date TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT,
            error TEXT,
            PRIMARY KEY(symbol, trading_date)
        )
        """
    )
    connection.execute(
        "INSERT INTO eod_daily_checkpoints VALUES (?, ?, ?, NULL, ?)",
        (
            symbol,
            DAY,
            daily_status,
            "SSINoDataFound" if daily_status == "NO_DATA" else None,
        ),
    )
    connection.commit()
    connection.close()


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


def test_stream_primary_cannot_replace_rest_blocked(
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
    with pytest.raises(RuntimeError, match="stream-primary EOD is disabled"):
        finalize_stream_day(
            source_path=paths.source,
            history_path=paths.history,
            market_path=paths.market,
            trading_date=DAY,
            dry_run=False,
            now=NOW,
            minimum_symbols=1,
            minimum_minutes=2,
        )
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_insufficient_stream_path_is_disabled(tmp_path: Path) -> None:
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

    with pytest.raises(RuntimeError, match="stream-primary EOD is disabled"):
        finalize_stream_day(
            source_path=paths.source,
            history_path=paths.history,
            market_path=paths.market,
            trading_date=DAY,
            dry_run=False,
            now=NOW,
        )
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


def test_wrapper_is_rest_canonical_and_rebuilds_only_after_pass() -> None:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "ccc-ssi-daily-finalize-wrapper.sh"
    ).read_text(encoding="utf-8")
    bootstrap_position = wrapper.index("app.historical_bootstrap")
    finalize_position = wrapper.index("app.daily_finalize")
    baseline_position = wrapper.index("app.volume_baseline_build")
    assert "--stream-primary" not in wrapper
    assert bootstrap_position < finalize_position < baseline_position
    assert 'REST_STAGE_DB="$(container_env SSI_EOD_STAGING_PATH)"' in wrapper
    assert 'HOT_DB="$(container_env DATABASE_PATH)"' in wrapper
    assert 'DAILY_JSON="$(container_env SSI_EOD_DAILY_JSON_PATH)"' in wrapper
    assert "from app.settings import Settings" in wrapper
    assert "from app.universe import load_universe" in wrapper
    assert "settings = Settings.from_env()" in wrapper
    assert "symbols = sorted(load_universe(settings))" in wrapper
    assert "latest_quotes" not in wrapper
    assert "ssi_history_2026.db" not in wrapper
    assert "ccc_market_v2.db" not in wrapper
    assert "--auction-source \"$HOT_DB\"" in wrapper
    assert "--market \"$MARKET_DB\"" in wrapper
    assert "--write" in wrapper


def test_wrapper_eod_universe_does_not_shrink_to_hot_quote_coverage(
    tmp_path: Path,
) -> None:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "ccc-ssi-daily-finalize-wrapper.sh"
    ).read_text(encoding="utf-8")
    program = wrapper.split("<<'EOD_UNIVERSE_PY'\n", 1)[1].split(
        "\nEOD_UNIVERSE_PY", 1
    )[0]
    universe_file = tmp_path / "universe.txt"
    universe_file.write_text("AAA\nBBB\nCCC\n", encoding="utf-8")
    hot_db = tmp_path / "hot.db"
    connection = sqlite3.connect(hot_db)
    connection.execute(
        "CREATE TABLE latest_quotes (symbol TEXT, trading_date TEXT)"
    )
    connection.execute("INSERT INTO latest_quotes VALUES ('AAA', ?)", (DAY,))
    connection.commit()
    connection.close()
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_PATH": str(hot_db),
            "MARKET_V2_DATABASE_PATH": str(tmp_path / "market.db"),
            "SSI_HISTORY_PATH": str(tmp_path / "history.db"),
            "VOLUME_BASELINE_PATH": str(tmp_path / "baseline.db"),
            "UNIVERSE_FILE": str(universe_file),
            "MIN_UNIVERSE_SIZE": "3",
            "SSI_CONSUMER_ID": "test-id",
            "SSI_CONSUMER_SECRET": "test-secret",
            "VOLUME_ENGINE_ENABLED": "false",
            "LIVE_STATE_ENABLED": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "AAA,BBB,CCC"


def test_wrapper_requires_six_absolute_pairwise_distinct_eod_paths() -> None:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "ccc-ssi-daily-finalize-wrapper.sh"
    ).read_text(encoding="utf-8")
    required = (
        "DATABASE_PATH",
        "MARKET_V2_DATABASE_PATH",
        "SSI_HISTORY_PATH",
        "VOLUME_BASELINE_PATH",
        "SSI_EOD_STAGING_PATH",
        "SSI_EOD_DAILY_JSON_PATH",
    )
    for name in required:
        assert f"container_env {name}" in wrapper
        assert name in wrapper.split("EOD_PATH_NAMES=(", 1)[1].split(")", 1)[0]
    validation_position = wrapper.index("EOD_PATH_VALUES=(")
    universe_position = wrapper.index("EOD_UNIVERSE_PY")
    assert validation_position < universe_position < wrapper.index(
        "app.historical_bootstrap"
    )
    assert 'if [[ "$path" != /* ]]' in wrapper
    assert "for ((j = 0; j < i; j++)); do" in wrapper
    assert '[[ "$path" == "${EOD_PATH_VALUES[$j]}" ]]' in wrapper


def _wrapper_daily_namespace() -> dict[str, object]:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "ccc-ssi-daily-finalize-wrapper.sh"
    ).read_text(encoding="utf-8")
    program = wrapper.split("<<'EOD_DAILY_PY'\n", 1)[1].split(
        "\nEOD_DAILY_PY", 1
    )[0]
    namespace: dict[str, object] = {"__name__": "wrapper_daily_test"}
    exec(compile(program, "<wrapper-daily-fetch>", "exec"), namespace)
    return namespace


def _wrapper_validation_connection(
    namespace: dict[str, object],
    *,
    intraday_status: str,
    checkpoint_rows: int,
    staged_rows: int,
    daily_status: str,
) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE historical_bootstrap_checkpoints (
            symbol TEXT NOT NULL,
            from_date TEXT NOT NULL,
            to_date TEXT NOT NULL,
            resolution INTEGER NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL
        );
        CREATE TABLE minute_bars (
            symbol TEXT NOT NULL,
            trading_date TEXT NOT NULL,
            volume INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO historical_bootstrap_checkpoints VALUES (?, ?, ?, 1, ?, ?)",
        ("AAA", DAY, DAY, intraday_status, checkpoint_rows),
    )
    connection.executemany(
        "INSERT INTO minute_bars VALUES ('AAA', ?, 1)",
        [(DAY,)] * staged_rows,
    )
    namespace["ensure_daily_checkpoint_schema"](connection)
    payload = None
    if daily_status == "COMPLETED":
        payload = json.dumps(
            {
                "Symbol": "AAA",
                "TradingDate": DAY,
                "Market": "HOSE",
                "Open": 100,
                "High": 105,
                "Low": 99,
                "Close": 103,
                "Volume": staged_rows,
            }
        )
    namespace["upsert_daily_checkpoint"](
        connection,
        "AAA",
        DAY,
        daily_status,
        payload=payload,
    )
    return connection


def test_wrapper_accepts_exact_completed_checkpoint_row_count() -> None:
    namespace = _wrapper_daily_namespace()
    connection = _wrapper_validation_connection(
        namespace,
        intraday_status="COMPLETED",
        checkpoint_rows=3,
        staged_rows=3,
        daily_status="COMPLETED",
    )

    payloads = namespace["validated_daily_payloads"](
        connection, ("AAA",), DAY, date.fromisoformat(DAY)
    )

    connection.close()
    assert len(payloads) == 1


def test_wrapper_rejects_checkpoint_count_above_staged_rows() -> None:
    namespace = _wrapper_daily_namespace()
    connection = _wrapper_validation_connection(
        namespace,
        intraday_status="COMPLETED",
        checkpoint_rows=100,
        staged_rows=99,
        daily_status="COMPLETED",
    )

    with pytest.raises(
        RuntimeError,
        match="INTRADAY_ROW_COUNT_MISMATCH:AAA:checkpoint=100:staged=99",
    ):
        namespace["validated_daily_payloads"](
            connection, ("AAA",), DAY, date.fromisoformat(DAY)
        )
    connection.close()


def test_wrapper_rejects_checkpoint_count_below_staged_rows() -> None:
    namespace = _wrapper_daily_namespace()
    connection = _wrapper_validation_connection(
        namespace,
        intraday_status="COMPLETED",
        checkpoint_rows=99,
        staged_rows=100,
        daily_status="COMPLETED",
    )

    with pytest.raises(
        RuntimeError,
        match="INTRADAY_ROW_COUNT_MISMATCH:AAA:checkpoint=99:staged=100",
    ):
        namespace["validated_daily_payloads"](
            connection, ("AAA",), DAY, date.fromisoformat(DAY)
        )
    connection.close()


def test_wrapper_rejects_no_data_checkpoint_with_staged_rows() -> None:
    namespace = _wrapper_daily_namespace()
    connection = _wrapper_validation_connection(
        namespace,
        intraday_status="NO_DATA",
        checkpoint_rows=0,
        staged_rows=1,
        daily_status="NO_DATA",
    )

    with pytest.raises(RuntimeError, match="INTRADAY_NO_DATA_WITH_ROWS:AAA"):
        namespace["validated_daily_payloads"](
            connection, ("AAA",), DAY, date.fromisoformat(DAY)
        )
    connection.close()


def test_successful_empty_daily_response_is_failed_not_no_data() -> None:
    namespace = _wrapper_daily_namespace()
    connection = sqlite3.connect(":memory:")
    namespace["ensure_daily_checkpoint_schema"](connection)

    class EmptyClient:
        @staticmethod
        def fetch_daily_ohlc(_symbol, _start, _end):
            return []

    with pytest.raises(RuntimeError, match="without explicit NoDataFound"):
        namespace["fetch_daily_checkpoint"](
            connection, EmptyClient(), "AAA", DAY, date.fromisoformat(DAY)
        )
    row = connection.execute(
        "SELECT status, error FROM eod_daily_checkpoints"
    ).fetchone()
    connection.close()
    assert row[0] == "FAILED"
    assert "EMPTY_OR_AMBIGUOUS_RESPONSE" in row[1]


def test_daily_no_data_checkpoint_is_persisted_and_skipped_on_rerun() -> None:
    namespace = _wrapper_daily_namespace()
    connection = sqlite3.connect(":memory:")
    namespace["ensure_daily_checkpoint_schema"](connection)

    class NoDataClient:
        calls = 0

        def fetch_daily_ohlc(self, _symbol, _start, _end):
            self.calls += 1
            raise namespace["SSINoDataFound"]("NoDataFound")

    client = NoDataClient()
    first = namespace["fetch_daily_checkpoint"](
        connection, client, "AAA", DAY, date.fromisoformat(DAY)
    )
    second = namespace["fetch_daily_checkpoint"](
        connection, client, "AAA", DAY, date.fromisoformat(DAY)
    )
    row = connection.execute(
        "SELECT status, payload_json, error FROM eod_daily_checkpoints"
    ).fetchone()
    connection.close()
    assert (first, second, client.calls) == ("NO_DATA", "NO_DATA", 1)
    assert row[0] == "NO_DATA"
    assert row[1] is None
    assert "SSINoDataFound" in row[2]


def test_partial_stream_derives_only_non_trusted_repair_symbols(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, symbol="FPT")
    _insert_minute(paths.source, symbol="HPG", quality="VOLUME_REGRESSION")
    result = _run(paths, bars=(_daily("FPT"), _daily("HPG")))
    assert result.status == "PARTIAL"
    connection = sqlite3.connect(paths.history)
    status, details_json = connection.execute(
        "SELECT status, details_json FROM daily_finalize_runs WHERE trading_date=?",
        (DAY,),
    ).fetchone()
    connection.close()
    plan = daily_finalize_module.repair_plan_from_details(
        json.loads(details_json), status=status
    )
    assert plan.bounded
    assert plan.symbols == ("HPG",)


def test_large_partial_repair_set_fails_closed() -> None:
    details = [
        {"symbol": f"S{index:03d}", "status": "BLOCKED", "reasons": ["GAP"]}
        for index in range(daily_finalize_module.MAX_TARGETED_REPAIR_SYMBOLS + 1)
    ]
    plan = daily_finalize_module.repair_plan_from_details(details, status="PARTIAL")
    assert not plan.bounded
    assert plan.symbols == ()
    assert plan.reason.startswith("REPAIR_SET_TOO_LARGE:")


def test_rest_minute_repair_without_daily_bar_is_not_canonically_complete(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, exchange="UPCOM", minute="14:59")
    _insert_minute(
        paths.history, source=SSI_REST, exchange="UPCOM", minute="14:59"
    )
    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )
    assert not proof.complete
    assert proof.missing_daily_bars == ("FPT",)
    assert daily_finalize_module.rest_repair_status(
        prior_status="PARTIAL",
        checkpoints_complete=True,
        canonical_complete=proof.complete,
    ) == "PARTIAL"


def test_rest_pass_completeness_requires_and_accepts_canonical_outputs(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, exchange="UPCOM", minute="14:59")
    _insert_minute(
        paths.history, source=SSI_REST, exchange="UPCOM", minute="14:59"
    )
    incomplete = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )
    assert not incomplete.complete
    assert daily_finalize_module.rest_repair_status(
        prior_status="REST_BLOCKED",
        checkpoints_complete=True,
        canonical_complete=incomplete.complete,
    ) == "REST_BLOCKED"

    _insert_daily_bar(paths.market, _daily(exchange="UPCOM"))
    complete = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )
    assert complete.complete
    assert complete.complete_symbols == ("FPT",)
    assert daily_finalize_module.rest_repair_status(
        prior_status="REST_BLOCKED",
        checkpoints_complete=True,
        canonical_complete=complete.complete,
    ) == "REST_PASS"


def test_finalized_minute_source_is_ssi_rest(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _run(paths)
    assert _history_row(paths) == (SSI_REST, "TRUSTED", 0, 0, 100)


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


def test_volume_regression_cannot_self_validate_as_trusted(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, quality="VOLUME_REGRESSION")
    result = _run(paths)
    assert result.status == "BLOCKED"
    assert result.event_anomaly_rows == 1
    assert "VOLUME_REGRESSION=1" in result.symbols[0].event_anomalies
    assert "UNRESOLVED_EVENT_ANOMALY" in result.symbols[0].reasons
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_partial_stream_row_cannot_self_validate_as_trusted(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, quality="PARTIAL", partial=1)
    result = _run(paths)
    assert result.status == "BLOCKED"
    assert "PARTIAL_STREAM_ROW" in result.symbols[0].reasons
    assert "UNRESOLVED_EVENT_ANOMALY" in result.symbols[0].reasons
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_idempotent_rest_pass_relies_on_immutable_canonical_history(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    assert _run(paths).status == "PASS"

    connection = sqlite3.connect(paths.source)
    connection.execute(
        """
        UPDATE minute_bars
        SET quality_status='VOLUME_REGRESSION', is_partial=1
        WHERE symbol='FPT' AND trading_date=?
        """,
        (DAY,),
    )
    connection.commit()
    connection.close()

    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )
    assert proof.complete
    assert proof.unsafe_stream_source == ()


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


def test_intraday_no_data_and_official_zero_daily_settles_proven_zero(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="NO_DATA",
        daily_status="COMPLETED",
    )

    result = _run(paths, bars=(_daily(volume=0),))

    assert result.status == "PASS"
    assert result.symbols_trusted == 1
    assert result.symbols[0].represented_volume == 0
    assert result.symbols[0].daily_volume == 0
    assert result.daily_rows_inserted == 1
    assert result.minute_rows_inserted == 0
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 1


def test_canonical_completeness_accepts_official_zero_daily_without_minutes(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="NO_DATA",
        daily_status="COMPLETED",
    )
    _run(paths, bars=(_daily(volume=0),))

    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )

    assert proof.complete
    assert proof.complete_symbols == ("FPT",)
    assert proof.missing_history == ()


def test_paired_no_data_is_unavailable_while_valid_symbol_settles(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, symbol="FPT")
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="COMPLETED",
        daily_status="COMPLETED",
    )
    _insert_checkpoint_pair(
        paths,
        symbol="ZZZ",
        intraday_status="NO_DATA",
        daily_status="NO_DATA",
    )

    result = _run(paths, bars=(_daily(),))
    connection = sqlite3.connect(paths.source)
    connection.execute("DELETE FROM historical_bootstrap_checkpoints")
    connection.execute("DELETE FROM eod_daily_checkpoints")
    connection.commit()
    connection.close()
    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )

    by_symbol = {item.symbol: item for item in result.symbols}
    assert result.status == "PASS"
    assert (result.symbols_trusted, result.symbols_unavailable) == (1, 1)
    assert by_symbol["FPT"].status == "TRUSTED"
    assert by_symbol["ZZZ"].status == "UNAVAILABLE"
    assert by_symbol["ZZZ"].reasons == ("PROVIDER_NO_DATA",)
    assert _count(paths.history, "minute_bars") == 1
    assert _count(paths.market, "daily_bars") == 1
    assert proof.complete
    assert proof.expected_symbols == ("FPT", "ZZZ")
    assert proof.complete_symbols == ("FPT",)
    assert proof.provider_unavailable == ("ZZZ",)
    assert _count_symbol(paths.source, "minute_bars", "ZZZ") == 0
    assert _count_symbol(paths.history, "minute_bars", "ZZZ") == 0
    assert _count_symbol(paths.market, "daily_bars", "ZZZ") == 0


def test_non_provider_unavailable_journal_reason_does_not_complete_day(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source, symbol="FPT")
    result = _run(paths, bars=(_daily(),))
    assert result.status == "PASS"

    connection = sqlite3.connect(paths.history)
    details = json.loads(
        connection.execute(
            "SELECT details_json FROM daily_finalize_runs WHERE trading_date=?",
            (DAY,),
        ).fetchone()[0]
    )
    details.append(
        {
            "symbol": "ZZZ",
            "status": "UNAVAILABLE",
            "reasons": ["SOURCE_MISSING"],
        }
    )
    connection.execute(
        "UPDATE daily_finalize_runs SET details_json=? WHERE trading_date=?",
        (json.dumps(details), DAY),
    )
    connection.commit()
    connection.close()

    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )

    assert not proof.complete
    assert proof.complete_symbols == ("FPT",)
    assert proof.provider_unavailable == ()
    assert proof.missing_daily_bars == ("ZZZ",)


def test_paired_no_data_alone_is_explicitly_complete_but_not_trusted(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="ZZZ",
        intraday_status="NO_DATA",
        daily_status="NO_DATA",
    )

    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )

    assert proof.complete
    assert proof.expected_symbols == ("ZZZ",)
    assert proof.complete_symbols == ()
    assert proof.provider_unavailable == ("ZZZ",)
    assert proof.missing_daily_bars == ()


def test_inconsistent_checkpoint_pair_is_not_provider_unavailable(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="COMPLETED",
        daily_status="NO_DATA",
    )

    proof = daily_finalize_module.canonical_day_completeness(
        source_path=paths.source,
        history_path=paths.history,
        market_path=paths.market,
        trading_date=DAY,
    )

    assert not proof.complete
    assert proof.expected_symbols == ("FPT",)
    assert proof.complete_symbols == ()
    assert proof.provider_unavailable == ()
    assert proof.unsafe_history == ("FPT",)


def test_intraday_no_data_with_nonzero_daily_is_blocked(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="NO_DATA",
        daily_status="COMPLETED",
    )

    result = _run(paths, bars=(_daily(volume=100),))

    assert result.status == "BLOCKED"
    assert result.symbols[0].reasons == ("VOLUME_MISMATCH",)
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_intraday_completed_with_daily_no_data_is_blocked(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="COMPLETED",
        daily_status="NO_DATA",
    )

    result = _run(paths, bars=())

    assert result.status == "BLOCKED"
    assert result.symbols[0].reasons == ("DAILY_NO_DATA_WITH_INTRADAY",)
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_failed_eod_checkpoint_pair_is_blocked(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_checkpoint_pair(
        paths,
        symbol="FPT",
        intraday_status="FAILED",
        daily_status="NO_DATA",
    )

    result = _run(paths, bars=())

    assert result.status == "BLOCKED"
    assert result.symbols[0].reasons == ("CHECKPOINT_FAILED",)
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0


def test_degraded_atc_does_not_block_valid_rest_daily_settlement(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source, quality="DEGRADED")

    result = _run(paths)

    assert result.status == "PASS"
    assert result.symbols_trusted == 1
    assert result.atc_proven_inserted == 0
    assert result.atc_conflicts == 0
    assert _count(paths.history, "minute_bars") == 1
    assert _count(paths.market, "daily_bars") == 1
    assert _count(paths.market, "auction_session_history") == 0


def test_missing_auction_does_not_block_valid_rest_daily_settlement(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)

    result = _run(paths)

    assert result.status == "PASS"
    assert result.symbols_trusted == 1
    assert result.ato_proven_inserted == 0
    assert result.atc_proven_inserted == 0
    assert _count(paths.history, "minute_bars") == 1
    assert _count(paths.market, "daily_bars") == 1
    assert _count(paths.market, "auction_session_history") == 0


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


def test_wrong_provider_session_auction_is_ignored_without_blocking_rest(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source, auction_type=OPEN_AUCTION, provider_session="LO")
    result = _run(paths)
    assert result.status == "PASS"
    assert result.symbols_trusted == 1
    assert result.ato_conflicts == 0
    assert _count(paths.market, "auction_session_history") == 0


def test_conflicting_new_proven_auction_still_blocks_symbol(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _insert_minute(paths.source)
    _insert_auction(paths.source, volume=40)
    connection = sqlite3.connect(paths.market)
    store_auction_history_row(
        connection,
        _auction_history_row(DAY, auction_type=CLOSE_AUCTION, quality=PROVEN),
        recorded_at=NOW_TEXT,
    )
    connection.commit()
    connection.close()

    result = _run(paths)

    assert result.status == "BLOCKED"
    assert result.symbols_blocked == 1
    assert result.atc_conflicts == 1
    assert result.symbols[0].reasons == ("AUCTION_CONFLICT",)
    assert _count(paths.history, "minute_bars") == 0
    assert _count(paths.market, "daily_bars") == 0
    assert _count(paths.market, "auction_session_history") == 1


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
