from __future__ import annotations

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
    normalize_historical_record,
    normalize_historical_rows,
)
from app.storage import SQLiteStore


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
        ]
    )
    assert args.from_date == date(2026, 9, 1)
    assert args.to_date == date(2026, 9, 11)
    assert args.symbols == "HPG,SSI,VIX"
    assert args.limit_symbols == 2


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


def test_normalizes_strict_date_time_and_direct_interval_volume() -> None:
    bar = normalize_historical_record(row(volume=9876, provider_time="09:15:30.123"))
    assert bar is not None
    assert bar.trading_date == "2026-09-12"
    assert bar.minute == "09:15"
    assert bar.provider_time == "09:15:30.123"
    assert bar.volume == 9876
    assert (bar.open, bar.high, bar.low, bar.close) == (27.1, 27.5, 27.0, 27.4)


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
    assert store.insert_historical_bar(**{**kwargs, "volume": 111}) is False
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
    assert store.insert_historical_bar(
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
    ) is False
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
        from_date=date(2026, 9, 12),
        to_date=date(2026, 9, 12),
        output=lambda _: None,
        now=fixed_now,
    )
    second = run_bootstrap(
        store=store,
        client=fetcher,
        symbols=["HPG"],
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
