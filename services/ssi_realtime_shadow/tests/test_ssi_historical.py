from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import requests

from app.historical_bootstrap import build_parser, run_bootstrap
from app.market_session import VN_TZ
from app.ssi_historical import (
    SSIHTTPError,
    SSIHistoricalClient,
    SSIHistoricalError,
    SSINoDataFound,
    SSIRateLimitCircuitOpen,
    normalize_historical_record,
    normalize_historical_rows,
)
from app.storage import HistoricalCanonicalConflict, SQLiteStore


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def token_response() -> FakeResponse:
    return FakeResponse(200, {"status": 200, "data": {"accessToken": "test-token"}})


def row(
    *,
    symbol: str = "HPG",
    market: str = "HOSE",
    trading_date: str = "12/09/2026",
    provider_time: str = "09:15:00",
    volume: int = 1234,
) -> dict[str, Any]:
    return {
        "Symbol": symbol,
        "Market": market,
        "TradingDate": trading_date,
        "Time": provider_time,
        "Open": 27.1,
        "High": 27.5,
        "Low": 27.0,
        "Close": 27.4,
        "Volume": volume,
        "Value": 33800000,
    }


def client(session: FakeSession, **kwargs: Any) -> SSIHistoricalClient:
    return SSIHistoricalClient(
        base_url="https://fc-data.ssi.com.vn/",
        consumer_id="consumer",
        consumer_secret="secret",
        session=session,
        sleep=kwargs.pop("sleep", lambda _: None),
        **kwargs,
    )


def test_cli_accepts_required_dates_symbol_subset_and_limit() -> None:
    args = build_parser().parse_args(
        [
            "--from-date",
            "01/09/2026",
            "--to-date",
            "11/09/2026",
            "--symbols",
            "HPG,SSI,VIX",
            "--limit-symbols",
            "2",
            "--resolution",
            "1",
        ]
    )
    assert args.from_date == date(2026, 9, 1)
    assert args.to_date == date(2026, 9, 11)
    assert args.symbols == "HPG,SSI,VIX"
    assert args.limit_symbols == 2
    assert args.resolution == 1


def test_cli_requires_explicit_bounded_symbols() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--from-date", "01/09/2026", "--to-date", "11/09/2026"]
        )


def test_paginates_using_total_record_and_reuses_access_token() -> None:
    session = FakeSession(
        [
            token_response(),
            FakeResponse(200, {"status": 200, "data": [row()], "totalRecord": 2}),
            FakeResponse(
                200,
                {
                    "status": 200,
                    "data": [row(provider_time="09:16:00")],
                    "totalRecord": 2,
                },
            ),
        ]
    )
    rows = client(session, page_size=1).fetch_intraday_ohlc(
        "hpg", "12/09/2026", "12/09/2026"
    )

    assert len(rows) == 2
    assert len([call for call in session.calls if call["method"] == "POST"]) == 1
    gets = [call for call in session.calls if call["method"] == "GET"]
    assert [call["params"]["pageIndex"] for call in gets] == [1, 2]
    assert all(call["params"]["pageSize"] == 1 for call in gets)
    assert all(call["params"]["resolution"] == 1 for call in gets)
    assert all(call["headers"]["Authorization"] == "Bearer test-token" for call in gets)


@pytest.mark.parametrize(
    "provider_status", ["Success", "success", 200, 200.0, "200", "200.0"]
)
def test_accepts_documented_provider_success_status(provider_status: Any) -> None:
    payload = {
        "data": [row()],
        "message": "Success",
        "status": provider_status,
        "totalRecord": 1,
    }
    session = FakeSession([token_response(), FakeResponse(200, payload)])
    assert len(
        client(session).fetch_intraday_ohlc(
            "HPG", "12/09/2026", "12/09/2026"
        )
    ) == 1


def test_rejects_unknown_provider_status_string() -> None:
    session = FakeSession(
        [
            token_response(),
            FakeResponse(
                200,
                {
                    "data": [row()],
                    "message": "Failed",
                    "status": "Failed",
                    "totalRecord": 1,
                },
            ),
        ]
    )
    with pytest.raises(SSIHistoricalError, match="provider status 'Failed'"):
        client(session).fetch_intraday_ohlc(
            "HPG", "12/09/2026", "12/09/2026"
        )


def test_duplicate_provider_rows_are_deduplicated() -> None:
    duplicate = row()
    session = FakeSession(
        [token_response(), FakeResponse(200, {"status": 200, "data": [duplicate, duplicate], "totalRecord": 2})]
    )
    assert len(client(session).fetch_intraday_ohlc("HPG", date(2026, 9, 12), date(2026, 9, 12))) == 1


def test_large_ranges_are_split_without_silent_truncation() -> None:
    session = FakeSession(
        [
            token_response(),
            FakeResponse(200, {"status": 200, "data": [row()], "totalRecord": 3}),
            FakeResponse(200, {"status": 200, "data": [row()], "totalRecord": 1}),
            FakeResponse(
                200,
                {
                    "status": 200,
                    "data": [row(trading_date="13/09/2026")],
                    "totalRecord": 1,
                },
            ),
        ]
    )
    rows = client(session, page_size=2, max_pages_per_range=1).fetch_intraday_ohlc(
        "HPG", "12/09/2026", "13/09/2026"
    )
    get_calls = [call for call in session.calls if call["method"] == "GET"]
    assert len(rows) == 2
    assert get_calls[1]["params"]["fromDate"] == "12/09/2026"
    assert get_calls[1]["params"]["toDate"] == "12/09/2026"
    assert get_calls[2]["params"]["fromDate"] == "13/09/2026"


def test_page_index_never_exceeds_ten_and_large_range_is_split() -> None:
    class SplitSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append({"method": method, "url": url, **kwargs})
            if method == "POST":
                return token_response()
            params = kwargs["params"]
            page_index = params["pageIndex"]
            if params["fromDate"] != params["toDate"]:
                total = 11
            else:
                total = 6 if params["fromDate"] == "12/09/2026" else 5
            return FakeResponse(
                200,
                {
                    "status": "Success",
                    "message": "Success",
                    "data": [
                        row(
                            trading_date=params["fromDate"],
                            provider_time=f"09:{page_index:02d}:00",
                        )
                    ],
                    "totalRecord": total,
                },
            )

    session = SplitSession()
    rows = client(session, page_size=1).fetch_intraday_ohlc(
        "HPG", "12/09/2026", "13/09/2026"
    )
    get_calls = [call for call in session.calls if call["method"] == "GET"]
    assert len(rows) == 11
    assert max(call["params"]["pageIndex"] for call in get_calls) == 6
    assert all(call["params"]["pageIndex"] <= 10 for call in get_calls)
    assert sum(
        call["params"]["fromDate"] != call["params"]["toDate"]
        for call in get_calls
    ) == 1


def test_constructor_rejects_page_limit_above_official_maximum() -> None:
    with pytest.raises(ValueError, match="pageIndex limit 10"):
        client(FakeSession([]), max_pages_per_range=11)


def test_normalizes_strict_date_time_and_direct_interval_volume() -> None:
    bar = normalize_historical_record(row(volume=9876, provider_time="09:15:30.123"))
    assert bar is not None
    assert bar.trading_date == "2026-09-12"
    assert bar.minute == "09:15"
    assert bar.provider_time == "09:15:30.123"
    assert bar.volume == 9876
    assert (bar.open, bar.high, bar.low, bar.close) == (27.1, 27.5, 27.0, 27.4)


@pytest.mark.parametrize("exchange_hint", ["HOSE", "HNX"])
def test_missing_provider_market_uses_trusted_exchange_hint(
    exchange_hint: str,
) -> None:
    provider_row = row()
    provider_row.pop("Market")
    bar = normalize_historical_record(provider_row, exchange_hint=exchange_hint)
    assert bar is not None
    assert bar.exchange == exchange_hint


def test_missing_provider_market_without_hint_is_rejected() -> None:
    provider_row = row()
    provider_row.pop("Market")
    assert normalize_historical_record(provider_row) is None


def test_matching_provider_market_and_trusted_hint_is_accepted() -> None:
    bar = normalize_historical_record(row(market="HOSE"), exchange_hint="HSX")
    assert bar is not None
    assert bar.exchange == "HOSE"


def test_conflicting_provider_market_and_trusted_hint_is_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert (
        normalize_historical_record(row(market="HOSE"), exchange_hint="HNX")
        is None
    )
    assert "provider exchange HOSE conflicts with trusted exchange HNX" in caplog.text


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("HOSE", "HOSE"), ("HSX", "HOSE"), ("HNX", "HNX"), ("UPCOM", "UPCOM"), ("UPCO", "UPCOM")],
)
def test_normalizes_equity_market_aliases(alias: str, expected: str) -> None:
    bar = normalize_historical_record(row(market=alias))
    assert bar is not None
    assert bar.exchange == expected


def test_derivatives_and_unknown_markets_are_ignored() -> None:
    assert normalize_historical_record(row(market="DER")) is None
    assert normalize_historical_record(row(market="MYSTERY")) is None


@pytest.mark.parametrize(
    "bad_time", [None, "", "9:15", "9:15:00", "25:00:00", "not-a-time"]
)
def test_missing_or_malformed_provider_time_is_rejected(bad_time: Any) -> None:
    record = row()
    record["Time"] = bad_time
    assert normalize_historical_record(record) is None


def test_invalid_trading_date_is_rejected_without_current_date_fallback() -> None:
    assert normalize_historical_record(row(trading_date="32/09/2026")) is None


def test_fractional_or_negative_interval_volume_is_rejected() -> None:
    fractional = row()
    fractional["Volume"] = 12.5
    assert normalize_historical_record(fractional) is None
    assert normalize_historical_record(row(volume=-1)) is None


def test_normalized_rows_deduplicate_same_canonical_minute() -> None:
    bars = normalize_historical_rows([row(provider_time="09:15:01"), row(provider_time="09:15:59")])
    assert len(bars) == 1


def test_historical_insert_is_idempotent_and_keeps_direct_volume(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "bars.db")
    kwargs = dict(
        trading_date="2026-09-12",
        minute="09:15",
        symbol="HPG",
        exchange="HOSE",
        open_price=27.1,
        high=27.5,
        low=27.0,
        close=27.4,
        volume=9876,
        provider_time="09:15:00",
        updated_at="2026-09-12T09:15:01+07:00",
    )
    assert store.insert_historical_bar(**kwargs) is True
    assert store.insert_historical_bar(**kwargs) is False
    with pytest.raises(HistoricalCanonicalConflict):
        store.insert_historical_bar(**{**kwargs, "volume": 111})
    saved = store._conn.execute(
        "SELECT volume, quality_status, data_source, event_count FROM minute_bars"
    ).fetchone()
    assert dict(saved) == {
        "volume": 9876,
        "quality_status": "TRUSTED",
        "data_source": "SSI_REST",
        "event_count": 1,
    }
    store.close()


@pytest.mark.parametrize(
    ("quality", "partial", "has_gap"),
    [("TRUSTED", False, False), ("GAP", True, True), ("PARTIAL", True, False)],
)
def test_rest_never_overwrites_existing_stream_rows(
    tmp_path: Path, quality: str, partial: bool, has_gap: bool
) -> None:
    store = SQLiteStore(tmp_path / f"{quality}.db")
    store.upsert_minute_bar(
        trading_date="2026-09-12",
        minute="09:15",
        symbol="HPG",
        price=25.0,
        volume_delta=100,
        total_volume=100,
        is_partial=partial,
        exchange="HOSE",
        quality_status=quality,
        has_gap=has_gap,
        gap_from="09:14:00" if has_gap else None,
        gap_to="09:15:00" if has_gap else None,
        updated_at="original",
    )
    with pytest.raises(HistoricalCanonicalConflict):
        store.insert_historical_bar(
            trading_date="2026-09-12",
            minute="09:15",
            symbol="HPG",
            exchange="HOSE",
            open_price=99,
            high=99,
            low=99,
            close=99,
            volume=9999,
            provider_time="09:15:00",
            updated_at="replacement",
        )
    saved = store._conn.execute(
        "SELECT open, volume, quality_status, is_partial, has_gap, updated_at, data_source FROM minute_bars"
    ).fetchone()
    assert tuple(saved) == (25.0, 100, quality, int(partial), int(has_gap), "original", "SSI_STREAM")
    store.close()


def test_checkpoint_success_and_completed_resume_skip(tmp_path: Path) -> None:
    class Fetcher:
        calls = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls += 1
            assert resolution == 1
            return [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "checkpoint.db")
    fetcher = Fetcher()
    fixed_now = lambda: datetime(2026, 9, 14, 10, 0, tzinfo=VN_TZ)
    first = run_bootstrap(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
        now=fixed_now,
    )
    second = run_bootstrap(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
        now=fixed_now,
    )
    checkpoint = store.get_historical_checkpoint("HPG", "2026-09-12", "2026-09-12", 1)
    assert first.completed == 1 and first.inserted_rows == 1
    assert second.skipped == 1
    assert fetcher.calls == 1
    assert checkpoint is not None and checkpoint.status == "COMPLETED"
    assert checkpoint.row_count == 1 and checkpoint.completed_at is not None
    assert checkpoint.attempt_count == 1
    store.close()


def test_final_rows_and_completed_checkpoint_use_one_atomic_batch(
    tmp_path: Path,
) -> None:
    trace: list[str] = []

    class Fetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            store._conn.set_trace_callback(trace.append)
            return [
                row(symbol=symbol),
                row(symbol=symbol, provider_time="09:16:00"),
            ]

    path = tmp_path / "atomic-success.db"
    store = SQLiteStore(path, commit_every_events=1, commit_every_seconds=1)
    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    store._conn.set_trace_callback(None)

    statements = [statement.strip().upper() for statement in trace]
    batch_statements = [
        statement
        for statement in statements
        if statement.startswith(("BEGIN", "INSERT", "UPDATE", "COMMIT"))
    ]
    assert batch_statements[0] == "BEGIN IMMEDIATE"
    assert batch_statements[-1] == "COMMIT"
    assert sum(statement.startswith("INSERT") for statement in batch_statements) == 2
    assert sum(statement.startswith("UPDATE") for statement in batch_statements) == 1
    assert batch_statements.count("COMMIT") == 1

    observer = sqlite3.connect(path)
    try:
        row_count = observer.execute(
            "SELECT COUNT(*) FROM minute_bars WHERE symbol='HPG'"
        ).fetchone()[0]
        checkpoint = observer.execute(
            """
            SELECT status, row_count
            FROM historical_bootstrap_checkpoints
            WHERE symbol='HPG' AND from_date='2026-09-12'
              AND to_date='2026-09-12' AND resolution=1
            """
        ).fetchone()
    finally:
        observer.close()

    assert summary.completed == 1 and summary.inserted_rows == 2
    assert row_count == 2
    assert checkpoint == ("COMPLETED", 2)
    store.close()


def test_failed_atomic_batch_rolls_back_and_rerun_succeeds_idempotently(
    tmp_path: Path,
) -> None:
    class Fetcher:
        def __init__(self) -> None:
            self.calls = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls += 1
            return [
                row(symbol=symbol),
                row(symbol=symbol, provider_time="09:16:00"),
            ]

    store = SQLiteStore(
        tmp_path / "atomic-failure.db",
        commit_every_events=1,
        commit_every_seconds=1,
    )
    store._conn.execute(
        """
        CREATE TRIGGER fail_historical_batch
        BEFORE INSERT ON minute_bars
        WHEN NEW.minute = '09:16'
        BEGIN
            SELECT RAISE(ABORT, 'simulated historical batch failure');
        END
        """
    )
    store.commit()
    fetcher = Fetcher()
    kwargs = dict(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )

    failed_summary = run_bootstrap(**kwargs)
    failed_checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    partial_rows = store._conn.execute(
        "SELECT COUNT(*) FROM minute_bars WHERE symbol='HPG'"
    ).fetchone()[0]

    assert failed_summary.failed == 1 and failed_summary.completed == 0
    assert failed_checkpoint is not None and failed_checkpoint.status == "FAILED"
    assert "simulated historical batch failure" in (failed_checkpoint.error or "")
    assert partial_rows == 0

    store._conn.execute("DROP TRIGGER fail_historical_batch")
    store.commit()
    resumed_summary = run_bootstrap(**kwargs)
    skipped_summary = run_bootstrap(**kwargs)
    completed_checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    saved_rows = store._conn.execute(
        "SELECT COUNT(*) FROM minute_bars WHERE symbol='HPG'"
    ).fetchone()[0]

    assert resumed_summary.completed == 1 and resumed_summary.inserted_rows == 2
    assert skipped_summary.skipped_completed == 1
    assert completed_checkpoint is not None
    assert completed_checkpoint.status == "COMPLETED"
    assert completed_checkpoint.attempt_count == 2
    assert saved_rows == 2
    assert fetcher.calls == 2
    store.close()


def test_generic_empty_response_is_failed_and_retried_on_rerun(
    tmp_path: Path,
) -> None:
    class Fetcher:
        def __init__(self) -> None:
            self.calls = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls += 1
            return [] if self.calls == 1 else [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "empty.db")
    fetcher = Fetcher()
    kwargs = dict(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    first = run_bootstrap(**kwargs)
    failed = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    second = run_bootstrap(**kwargs)
    completed = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )

    assert first.failed == 1 and first.no_data == 0
    assert failed is not None and failed.status == "FAILED"
    assert "EMPTY_RESPONSE" in (failed.error or "")
    assert second.completed == 1 and second.skipped_completed == 0
    assert completed is not None and completed.status == "COMPLETED"
    assert completed.attempt_count == 2
    assert fetcher.calls == 2
    store.close()


def test_bootstrap_enriches_missing_provider_market_from_trusted_map(
    tmp_path: Path,
) -> None:
    class Fetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            provider_row = row(symbol=symbol)
            provider_row.pop("Market")
            return [provider_row]

    store = SQLiteStore(tmp_path / "enriched.db")
    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    saved_exchange = store._conn.execute(
        "SELECT exchange FROM minute_bars WHERE symbol = 'HPG'"
    ).fetchone()[0]
    assert summary.completed == 1 and summary.failed == 0
    assert checkpoint is not None and checkpoint.status == "COMPLETED"
    assert saved_exchange == "HOSE"
    store.close()


def test_bootstrap_missing_trusted_exchange_fails_before_provider_fetch(
    tmp_path: Path,
) -> None:
    class Fetcher:
        calls = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls += 1
            return [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "missing-exchange.db")
    fetcher = Fetcher()
    summary = run_bootstrap(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    assert summary.failed == 1 and summary.completed == 0
    assert fetcher.calls == 0
    assert checkpoint is not None and checkpoint.status == "FAILED"
    assert "missing trusted exchange metadata for HPG" in (checkpoint.error or "")
    store.close()


def test_nonempty_provider_result_with_no_valid_bars_fails_checkpoint(
    tmp_path: Path,
) -> None:
    class Fetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            return [row(symbol=symbol, provider_time="malformed")]

    store = SQLiteStore(tmp_path / "all-rejected.db")
    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    assert summary.failed == 1 and summary.completed == 0
    assert checkpoint is not None and checkpoint.status == "FAILED"
    assert "provider returned rows but none could be normalized" in (
        checkpoint.error or ""
    )
    store.close()


def test_partial_normalization_reports_raw_valid_and_rejected_counts(
    tmp_path: Path,
) -> None:
    class Fetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            invalid = row(symbol=symbol, provider_time="malformed")
            return [row(symbol=symbol), invalid]

    store = SQLiteStore(tmp_path / "partially-rejected.db")
    output: list[str] = []
    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=output.append,
        verbose=True,
    )
    assert summary.completed == 1 and summary.rejected_rows == 1
    assert "raw_count=2 valid_count=1 rejected_count=1" in output[0]
    store.close()


def test_symbol_failure_is_checkpointed_and_does_not_stop_next_symbol(tmp_path: Path) -> None:
    class Fetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            assert resolution == 1
            if symbol == "AAA":
                raise RuntimeError("provider unavailable")
            return [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "failure.db")
    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["BBB", "AAA"],
        exchange_map={"AAA": "HOSE", "BBB": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    failed = store.get_historical_checkpoint("AAA", "2026-09-12", "2026-09-12", 1)
    completed = store.get_historical_checkpoint("BBB", "2026-09-12", "2026-09-12", 1)
    assert summary.failed == 1 and summary.completed == 1
    assert failed is not None and failed.status == "FAILED"
    assert "provider unavailable" in (failed.error or "")
    assert completed is not None and completed.status == "COMPLETED"
    store.close()


def test_failed_checkpoint_resumes_and_completes(tmp_path: Path) -> None:
    class Fetcher:
        def __init__(self) -> None:
            self.calls = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "failed-resume.db")
    fetcher = Fetcher()
    kwargs = dict(
        store=store,
        client=fetcher,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )

    first = run_bootstrap(**kwargs)
    second = run_bootstrap(**kwargs)
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )

    assert first.failed == 1
    assert second.completed == 1
    assert fetcher.calls == 2
    assert checkpoint is not None and checkpoint.status == "COMPLETED"
    assert checkpoint.attempt_count == 2
    store.close()


def test_interruption_resume_does_not_redo_completed_symbols(tmp_path: Path) -> None:
    class InterruptingFetcher:
        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            if symbol == "BBB":
                raise KeyboardInterrupt
            return [row(symbol=symbol)]

    class ResumingFetcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls.append(symbol)
            return [row(symbol=symbol)]

    store = SQLiteStore(tmp_path / "interrupt-resume.db")
    kwargs = dict(
        store=store,
        symbols=["AAA", "BBB"],
        exchange_map={"AAA": "HOSE", "BBB": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    with pytest.raises(KeyboardInterrupt):
        run_bootstrap(client=InterruptingFetcher(), **kwargs)

    completed = store.get_historical_checkpoint(
        "AAA", "2026-09-12", "2026-09-12", 1
    )
    interrupted = store.get_historical_checkpoint(
        "BBB", "2026-09-12", "2026-09-12", 1
    )
    assert completed is not None and completed.status == "COMPLETED"
    assert interrupted is not None and interrupted.status == "RUNNING"

    resumed = ResumingFetcher()
    summary = run_bootstrap(client=resumed, **kwargs)

    assert summary.skipped_completed == 1 and summary.completed == 1
    assert resumed.calls == ["BBB"]
    store.close()


def test_explicit_symbol_subset_never_expands_to_exchange_map(tmp_path: Path) -> None:
    class Fetcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            self.calls.append(symbol)
            return []

    store = SQLiteStore(tmp_path / "bounded.db")
    fetcher = Fetcher()
    summary = run_bootstrap(
        store=store,
        client=fetcher,
        symbols=["SSI", "HPG"],
        exchange_map={"HPG": "HOSE", "SSI": "HOSE", "VIX": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )

    assert summary.requested == 2
    assert fetcher.calls == ["HPG", "SSI"]
    store.close()


def test_progress_summary_counters_are_correct(tmp_path: Path) -> None:
    class Fetcher:
        retry_count = 0

        def fetch_intraday_ohlc(
            self,
            symbol: str,
            from_date: date,
            to_date: date,
            resolution: int = 1,
        ) -> list[dict]:
            if symbol == "AAA":
                self.retry_count += 2
                return [
                    row(symbol=symbol),
                    row(symbol=symbol, provider_time="malformed"),
                ]
            if symbol == "BBB":
                raise SSINoDataFound("NoDataFound for test")
            raise RuntimeError("still unavailable")

    store = SQLiteStore(tmp_path / "summary.db")
    store.insert_historical_bar(
        trading_date="2026-09-12",
        minute="09:15",
        symbol="AAA",
        exchange="HOSE",
        open_price=27.1,
        high=27.5,
        low=27.0,
        close=27.4,
        volume=1234,
        provider_time="09:15:00",
        updated_at="2026-09-12T09:15:01+07:00",
    )
    store.mark_historical_checkpoint_running(
        "DDD", "2026-09-12", "2026-09-12", 1, "start"
    )
    store.mark_historical_checkpoint_completed(
        "DDD", "2026-09-12", "2026-09-12", 1, 1, "done"
    )
    store.commit()
    ticks = iter([10.0, 12.5])

    summary = run_bootstrap(
        store=store,
        client=Fetcher(),
        symbols=["DDD", "CCC", "BBB", "AAA"],
        exchange_map={symbol: "HOSE" for symbol in ("AAA", "BBB", "CCC", "DDD")},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
        monotonic=lambda: next(ticks),
    )

    assert summary.requested == 4
    assert summary.skipped_completed == 1
    assert summary.completed == 1
    assert summary.no_data == 1
    assert summary.failed == 1
    assert summary.retry_count == 2
    assert summary.valid_rows == 1
    assert summary.inserted_rows == 0
    assert summary.existing_rows == 1
    assert summary.rejected_rows == 1
    assert summary.elapsed_seconds == 2.5
    store.close()


def test_provider_no_data_found_is_checkpointed_distinctly(tmp_path: Path) -> None:
    session = FakeSession(
        [
            token_response(),
            FakeResponse(
                200,
                {"status": "NoDataFound", "message": "NoDataFound", "data": []},
            ),
        ]
    )
    store = SQLiteStore(tmp_path / "provider-no-data.db")
    kwargs = dict(
        store=store,
        client=client(session),
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    summary = run_bootstrap(**kwargs)
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )
    calls_after_first_run = len(session.calls)
    rerun = run_bootstrap(**kwargs)

    assert summary.no_data == 1 and summary.failed == 0
    assert checkpoint is not None and checkpoint.status == "NO_DATA"
    assert "NoDataFound" in (checkpoint.error or "")
    assert rerun.no_data == 1 and rerun.skipped_completed == 0
    assert len(session.calls) == calls_after_first_run
    store.close()


def test_retry_429_respects_retry_after() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(429, {}, {"Retry-After": "7"}),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    assert client(session, sleep=sleeps.append).fetch_intraday_ohlc("HPG", "12/09/2026", "12/09/2026") == []
    assert sleeps == [7.0]


def test_pacing_is_invoked_between_rest_requests() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    paced = client(session, sleep=sleeps.append, request_interval=1.25)
    paced._access_token = "test-token"

    paced.fetch_intraday_ohlc("HPG", "12/09/2026", "12/09/2026")
    paced.fetch_intraday_ohlc("SSI", "12/09/2026", "12/09/2026")

    assert sleeps == [1.25]


def test_http_429_uses_exponential_backoff_with_jitter_then_succeeds() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(429, {}),
            FakeResponse(429, {}),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    retried = client(
        session,
        sleep=sleeps.append,
        initial_retry_delay=2,
        retry_jitter_ratio=0.25,
        random_value=lambda: 0.5,
    )

    assert retried.fetch_intraday_ohlc(
        "HPG", "12/09/2026", "12/09/2026"
    ) == []
    assert sleeps == [2.25, 4.5]
    assert retried.retry_count == 2


def test_provider_429_retries_then_succeeds() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(200, {"status": 429, "message": "Rate limited"}),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    retried = client(session, sleep=sleeps.append, initial_retry_delay=3)

    assert retried.fetch_intraday_ohlc(
        "HPG", "12/09/2026", "12/09/2026"
    ) == []
    assert sleeps == [3.0]
    assert retried.retry_count == 1


def test_repeated_429_stops_after_configured_limit_and_marks_failed(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(429, {}),
            FakeResponse(429, {}),
            FakeResponse(429, {}),
        ]
    )
    retried = client(
        session,
        sleep=sleeps.append,
        max_attempts=3,
        initial_retry_delay=2,
        max_retry_delay=3,
    )

    store = SQLiteStore(tmp_path / "repeated-429.db")
    summary = run_bootstrap(
        store=store,
        client=retried,
        symbols=["HPG"],
        exchange_map={"HPG": "HOSE"},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )
    checkpoint = store.get_historical_checkpoint(
        "HPG", "2026-09-12", "2026-09-12", 1
    )

    assert summary.failed == 1 and summary.retry_count == 2
    assert checkpoint is not None and checkpoint.status == "FAILED"
    assert "SSI HTTP 429" in (checkpoint.error or "")
    assert sleeps == [2.0, 3.0]
    assert retried.retry_count == 2
    store.close()


def test_429_circuit_aborts_batch_and_rerun_resumes_unattempted_symbols(
    tmp_path: Path,
) -> None:
    first_session = FakeSession(
        [
            token_response(),
            FakeResponse(
                200,
                {"status": 200, "data": [row(symbol="AAA")], "totalRecord": 1},
            ),
            FakeResponse(429, {}),
            FakeResponse(429, {}),
        ]
    )
    store = SQLiteStore(tmp_path / "batch-circuit.db")
    bootstrap_args = dict(
        store=store,
        symbols=["AAA", "BBB", "CCC", "DDD"],
        exchange_map={symbol: "HOSE" for symbol in ("AAA", "BBB", "CCC", "DDD")},
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
    )

    with pytest.raises(SSIRateLimitCircuitOpen, match="circuit open"):
        run_bootstrap(
            client=client(
                first_session,
                max_attempts=6,
                max_consecutive_rate_limits=2,
            ),
            **bootstrap_args,
        )

    first_data_symbols = [
        call["params"]["symbol"]
        for call in first_session.calls
        if call["method"] == "GET"
    ]
    aaa = store.get_historical_checkpoint("AAA", "2026-09-12", "2026-09-12", 1)
    bbb = store.get_historical_checkpoint("BBB", "2026-09-12", "2026-09-12", 1)
    ccc = store.get_historical_checkpoint("CCC", "2026-09-12", "2026-09-12", 1)
    ddd = store.get_historical_checkpoint("DDD", "2026-09-12", "2026-09-12", 1)

    assert first_data_symbols == ["AAA", "BBB", "BBB"]
    assert aaa is not None and aaa.status == "COMPLETED"
    assert bbb is not None and bbb.status == "FAILED"
    assert "SSIRateLimitCircuitOpen" in (bbb.error or "")
    assert "circuit open" in (bbb.error or "")
    assert ccc is None and ddd is None

    resumed_session = FakeSession(
        [
            token_response(),
            *[
                FakeResponse(
                    200,
                    {
                        "status": 200,
                        "data": [row(symbol=symbol)],
                        "totalRecord": 1,
                    },
                )
                for symbol in ("BBB", "CCC", "DDD")
            ],
        ]
    )
    resumed = run_bootstrap(
        client=client(resumed_session),
        **bootstrap_args,
    )
    resumed_data_symbols = [
        call["params"]["symbol"]
        for call in resumed_session.calls
        if call["method"] == "GET"
    ]

    assert resumed.skipped_completed == 1
    assert resumed.completed == 3
    assert resumed.failed == 0
    assert resumed_data_symbols == ["BBB", "CCC", "DDD"]
    for symbol in ("AAA", "BBB", "CCC", "DDD"):
        checkpoint = store.get_historical_checkpoint(
            symbol, "2026-09-12", "2026-09-12", 1
        )
        assert checkpoint is not None and checkpoint.status == "COMPLETED"
    store.close()


def test_429_circuit_breaker_opens_before_retry_budget_is_exhausted() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [token_response(), FakeResponse(429, {}), FakeResponse(429, {})]
    )
    guarded = client(
        session,
        sleep=sleeps.append,
        max_attempts=6,
        max_consecutive_rate_limits=2,
    )

    with pytest.raises(SSIRateLimitCircuitOpen, match="circuit open"):
        guarded.fetch_intraday_ohlc("HPG", "12/09/2026", "12/09/2026")

    assert len(session.calls) == 3  # token + two bounded data requests
    assert len(sleeps) == 1


def test_5xx_transient_retry_then_succeeds() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(503, {}),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    retried = client(session, sleep=sleeps.append, initial_retry_delay=4)

    assert retried.fetch_intraday_ohlc(
        "HPG", "12/09/2026", "12/09/2026"
    ) == []
    assert sleeps == [4.0]
    assert retried.retry_count == 1


def test_retry_5xx_and_network_timeout_are_bounded() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            token_response(),
            FakeResponse(503, {}),
            requests.Timeout("slow"),
            FakeResponse(200, {"status": 200, "data": [], "totalRecord": 0}),
        ]
    )
    assert client(session, sleep=sleeps.append).fetch_intraday_ohlc("HPG", "12/09/2026", "12/09/2026") == []
    assert sleeps == [1.0, 2.0]


def test_permanent_4xx_fails_without_retry() -> None:
    session = FakeSession([token_response(), FakeResponse(400, {"message": "bad"})])
    with pytest.raises(SSIHTTPError) as exc_info:
        client(session).fetch_intraday_ohlc("HPG", "12/09/2026", "12/09/2026")
    assert exc_info.value.status_code == 400
    assert len(session.calls) == 2
