from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.daily_history import (
    DailyHistoryConflict,
    bootstrap_daily_history,
    normalize_daily_ohlc_record,
    normalize_daily_ohlc_rows,
)
from app.market_session import VN_TZ
from app.market_storage_schema import ensure_market_storage_schema
from app.ssi_historical import SSIHistoricalClient, SSIHistoricalError


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def token() -> FakeResponse:
    return FakeResponse({"status": 200, "data": {"accessToken": "test-token"}})


def row(**updates: Any) -> dict[str, Any]:
    result = {
        "Symbol": "HPG", "Market": "HOSE", "TradingDate": "17/09/2026",
        "Time": "00:00:00", "Open": 28600, "High": 29000, "Low": 28400,
        "Close": 28900, "Volume": 23_382_100, "Value": 663_258_204_999.985,
    }
    result.update(updates)
    return result


def official_daily_row(**updates: Any) -> dict[str, Any]:
    result = {
        "symbol": "SSI",
        "market": "HOSE",
        "tradingdate": "04/05/2020",
        "time": "",
        "open": 12900,
        "high": 13000,
        "low": 12700,
        "close": 12700,
        "volume": 2180310,
        "value": 27943000000,
    }
    result.update(updates)
    return result


def client(session: FakeSession, **kwargs: Any) -> SSIHistoricalClient:
    return SSIHistoricalClient(
        base_url="https://fc-data.ssi.com.vn/", consumer_id="consumer",
        consumer_secret="secret", session=session, sleep=lambda _: None, **kwargs,
    )


@pytest.fixture
def database(tmp_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(tmp_path / "daily.db")
    ensure_market_storage_schema(
        connection, applied_at="2026-09-18T10:00:00+07:00"
    )
    try:
        yield connection
    finally:
        connection.close()


def test_valid_row_preserves_official_units_and_uppercases_symbol() -> None:
    bar = normalize_daily_ohlc_record(
        row(Symbol="hpg"), exchange_hint="HSX", as_of_date="2026-09-18"
    )
    assert bar is not None
    assert (bar.symbol, bar.exchange, bar.close) == ("HPG", "HOSE", 28900)
    assert bar.volume == 23_382_100
    assert bar.value == pytest.approx(663_258_204_999.985)
    assert bar.source == "SSI_DAILY_OHLC" and bar.quality_status == "TRUSTED"


def test_official_lowercase_envelope_empty_time_and_units_are_supported() -> None:
    provider_row = official_daily_row()
    session = FakeSession([
        token(),
        FakeResponse({
            "dataList": [provider_row],
            "message": "SUCCESS",
            "status": "SUCCESS",
            "totalrecord": 1,
        }),
    ])
    raw_rows = client(session).fetch_daily_ohlc(
        "SSI", "04/05/2020", "04/05/2020"
    )
    assert raw_rows == [provider_row]
    bar = normalize_daily_ohlc_record(
        raw_rows[0], exchange_hint="HOSE", as_of_date="05/05/2020"
    )
    assert bar is not None
    assert (bar.open, bar.high, bar.low, bar.close) == (
        12900, 13000, 12700, 12700
    )
    assert bar.volume == 2180310
    assert bar.value == 27943000000


@pytest.mark.parametrize(
    "updates",
    [
        {"Symbol": ""}, {"TradingDate": "32/09/2026"}, {"Open": float("nan")},
        {"High": float("inf")}, {"High": 28000}, {"Volume": -1},
        {"Volume": 1.5}, {"Value": -1}, {"Market": "HNX"},
    ],
)
def test_malformed_daily_rows_are_rejected(updates: dict[str, Any]) -> None:
    assert normalize_daily_ohlc_record(
        row(**updates), exchange_hint="HOSE", as_of_date="2026-09-18"
    ) is None


def test_null_value_stays_null_and_never_becomes_zero() -> None:
    bar = normalize_daily_ohlc_record(
        row(Value=None), exchange_hint="HOSE", as_of_date="2026-09-18"
    )
    assert bar is not None and bar.value is None


def test_current_as_of_session_is_rejected_as_incomplete() -> None:
    assert normalize_daily_ohlc_record(
        row(TradingDate="18/09/2026"),
        exchange_hint="HOSE", as_of_date="2026-09-18",
    ) is None


def test_normalization_deduplicates_equal_rows_and_rejects_conflicts() -> None:
    bars, rejected = normalize_daily_ohlc_rows(
        [row(), row()], expected_symbol="HPG", exchange_hint="HOSE",
        as_of_date="2026-09-18",
    )
    assert len(bars) == 1 and rejected == 0
    with pytest.raises(DailyHistoryConflict, match="Conflicting"):
        normalize_daily_ohlc_rows(
            [row(), row(Close=28800)], expected_symbol="HPG", exchange_hint="HOSE",
            as_of_date="2026-09-18",
        )


def test_daily_client_one_page_uses_official_endpoint_and_parameters() -> None:
    session = FakeSession([
        token(), FakeResponse({"status": 200, "data": [row()], "totalRecord": 1}),
    ])
    rows = client(session).fetch_daily_ohlc("hpg", "17/09/2026", "17/09/2026")
    assert len(rows) == 1
    call = session.calls[1]
    assert call["url"].endswith("api/v2/Market/DailyOhlc")
    assert call["params"] == {
        "symbol": "HPG", "fromDate": "17/09/2026", "toDate": "17/09/2026",
        "pageIndex": 1, "pageSize": 1000, "ascending": True,
    }


def test_daily_client_multiple_pages_and_cross_page_duplicate() -> None:
    duplicate = row()
    session = FakeSession([
        token(),
        FakeResponse({"status": 200, "data": [duplicate, row(TradingDate="16/09/2026")], "totalRecord": 3}),
        FakeResponse({"status": 200, "data": [duplicate], "totalRecord": 3}),
    ])
    rows = client(session, page_size=2).fetch_daily_ohlc(
        "HPG", "16/09/2026", "17/09/2026"
    )
    assert len(rows) == 2
    assert [call["params"]["pageIndex"] for call in session.calls[1:]] == [1, 2]


def test_daily_client_rejects_incomplete_pagination() -> None:
    session = FakeSession([
        token(),
        FakeResponse({"status": 200, "data": [row()], "totalRecord": 2}),
        FakeResponse({"status": 200, "data": [], "totalRecord": 2}),
    ])
    with pytest.raises(SSIHistoricalError, match="ended early"):
        client(session, page_size=1).fetch_daily_ohlc(
            "HPG", "17/09/2026", "17/09/2026"
        )


def test_daily_client_rejects_total_change() -> None:
    session = FakeSession([
        token(),
        FakeResponse({"status": 200, "data": [row()], "totalRecord": 2}),
        FakeResponse({"status": 200, "data": [row(TradingDate="16/09/2026")], "totalRecord": 3}),
    ])
    with pytest.raises(SSIHistoricalError, match="totalRecord changed"):
        client(session, page_size=1).fetch_daily_ohlc(
            "HPG", "16/09/2026", "17/09/2026"
        )


def test_daily_client_rejects_total_disappearing_mid_pagination() -> None:
    session = FakeSession([
        token(),
        FakeResponse({"status": 200, "data": [row()], "totalRecord": 2}),
        FakeResponse({"status": 200, "data": [row(TradingDate="16/09/2026")]}),
    ])
    with pytest.raises(SSIHistoricalError, match="totalRecord changed"):
        client(session, page_size=1).fetch_daily_ohlc(
            "HPG", "16/09/2026", "17/09/2026"
        )


def test_daily_client_splits_ranges_to_official_thirty_day_limit() -> None:
    session = FakeSession([
        token(), FakeResponse({"status": 200, "data": [], "totalRecord": 0}),
        FakeResponse({"status": 200, "data": [], "totalRecord": 0}),
    ])
    assert client(session).fetch_daily_ohlc(
        "HPG", "01/08/2026", "18/09/2026"
    ) == []
    gets = session.calls[1:]
    assert [(call["params"]["fromDate"], call["params"]["toDate"]) for call in gets] == [
        ("01/08/2026", "30/08/2026"), ("31/08/2026", "18/09/2026")
    ]


class EmptyOfficialSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if method == "POST":
            return token()
        return FakeResponse({
            "dataList": [], "message": "SUCCESS", "status": "SUCCESS",
            "totalrecord": 0,
        })


def test_exactly_thirty_calendar_days_use_one_daily_request() -> None:
    session = EmptyOfficialSession()
    assert client(session).fetch_daily_ohlc(
        "SSI", "01/01/2025", "30/01/2025"
    ) == []
    gets = [call for call in session.calls if call["method"] == "GET"]
    assert len(gets) == 1
    assert gets[0]["params"]["fromDate"] == "01/01/2025"
    assert gets[0]["params"]["toDate"] == "30/01/2025"


def test_thirty_one_calendar_days_split_into_two_daily_requests() -> None:
    session = EmptyOfficialSession()
    assert client(session).fetch_daily_ohlc(
        "SSI", "01/01/2025", "31/01/2025"
    ) == []
    gets = [call for call in session.calls if call["method"] == "GET"]
    assert [(call["params"]["fromDate"], call["params"]["toDate"]) for call in gets] == [
        ("01/01/2025", "30/01/2025"), ("31/01/2025", "31/01/2025")
    ]


def test_one_year_range_emits_only_nonoverlapping_at_most_thirty_day_requests() -> None:
    session = EmptyOfficialSession()
    assert client(session).fetch_daily_ohlc(
        "SSI", "01/01/2025", "31/12/2025"
    ) == []
    gets = [call for call in session.calls if call["method"] == "GET"]
    assert len(gets) == 13
    previous_end: date | None = None
    for call in gets:
        start = datetime.strptime(call["params"]["fromDate"], "%d/%m/%Y").date()
        end = datetime.strptime(call["params"]["toDate"], "%d/%m/%Y").date()
        assert 1 <= (end - start).days + 1 <= 30
        if previous_end is not None:
            assert start == previous_end + timedelta(days=1)
        previous_end = end
    assert previous_end == date(2025, 12, 31)


def test_duplicate_returned_across_daily_chunks_survives_only_once() -> None:
    duplicate = official_daily_row(tradingdate="30/01/2025")
    final = official_daily_row(tradingdate="31/01/2025")
    session = FakeSession([
        token(),
        FakeResponse({
            "dataList": [duplicate], "message": "SUCCESS", "status": "SUCCESS",
            "totalrecord": 1,
        }),
        FakeResponse({
            "dataList": [duplicate, final], "message": "SUCCESS",
            "status": "SUCCESS", "totalrecord": 2,
        }),
    ])
    rows = client(session).fetch_daily_ohlc(
        "SSI", "01/01/2025", "31/01/2025"
    )
    assert [item["tradingdate"] for item in rows] == ["30/01/2025", "31/01/2025"]


def test_failure_in_later_daily_chunk_fails_the_whole_fetch() -> None:
    session = FakeSession([
        token(),
        FakeResponse({
            "dataList": [official_daily_row(tradingdate="30/01/2025")],
            "message": "SUCCESS", "status": "SUCCESS", "totalrecord": 1,
        }),
        FakeResponse({}, status_code=503),
    ])
    with pytest.raises(SSIHistoricalError):
        client(session, max_attempts=1).fetch_daily_ohlc(
            "SSI", "01/01/2025", "31/01/2025"
        )


def test_daily_client_reuses_retry_policy() -> None:
    sleeps: list[float] = []
    session = FakeSession([
        token(), FakeResponse({}, 429, {"Retry-After": "2"}),
        FakeResponse({"status": 200, "data": [], "totalRecord": 0}),
    ])
    c = SSIHistoricalClient(
        base_url="https://fc-data.ssi.com.vn/", consumer_id="consumer",
        consumer_secret="secret", session=session, sleep=sleeps.append,
    )
    assert c.fetch_daily_ohlc("HPG", "17/09/2026", "17/09/2026") == []
    assert sleeps == [2.0]


def test_bootstrap_first_insert_and_idempotent_rerun(database: sqlite3.Connection) -> None:
    class Fetcher:
        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            return [row(Symbol=symbol)]

    now = datetime(2026, 9, 18, 10, 0, tzinfo=VN_TZ)
    first = bootstrap_daily_history(
        connection=database, client=Fetcher(), symbol="hpg", exchange="HOSE",
        from_date="17/09/2026", to_date="17/09/2026",
        as_of_date="18/09/2026", now=now,
    )
    second = bootstrap_daily_history(
        connection=database, client=Fetcher(), symbol="HPG", exchange="HOSE",
        from_date="17/09/2026", to_date="17/09/2026",
        as_of_date="18/09/2026", now=now,
    )
    assert (first.inserted_rows, first.existing_rows) == (1, 0)
    assert (second.inserted_rows, second.existing_rows) == (0, 1)
    assert database.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 1


def test_bootstrap_rejects_malformed_without_zero_fill(database: sqlite3.Connection) -> None:
    class Fetcher:
        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            return [row(Symbol=symbol), row(Symbol=symbol, TradingDate="16/09/2026", Volume=-1)]

    result = bootstrap_daily_history(
        connection=database, client=Fetcher(), symbol="HPG", exchange="HOSE",
        from_date="16/09/2026", to_date="17/09/2026", as_of_date="18/09/2026",
    )
    assert result.status == "PARTIAL_REJECTED" and result.rejected_rows == 1
    assert database.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 1
    assert database.execute("SELECT MIN(volume) FROM daily_bars").fetchone()[0] > 0


def test_provider_failure_happens_before_any_write(database: sqlite3.Connection) -> None:
    class Fetcher:
        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            raise SSIHistoricalError("incomplete provider response")

    with pytest.raises(SSIHistoricalError, match="incomplete"):
        bootstrap_daily_history(
            connection=database, client=Fetcher(), symbol="HPG", exchange="HOSE",
            from_date="16/09/2026", to_date="17/09/2026", as_of_date="18/09/2026",
        )
    assert database.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 0


def test_bootstrap_refuses_range_containing_as_of_session_before_fetch(
    database: sqlite3.Connection,
) -> None:
    class Fetcher:
        calls = 0

        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            self.calls += 1
            return []

    fetcher = Fetcher()
    with pytest.raises(ValueError, match="strictly before"):
        bootstrap_daily_history(
            connection=database, client=fetcher, symbol="HPG", exchange="HOSE",
            from_date="17/09/2026", to_date="18/09/2026", as_of_date="18/09/2026",
        )
    assert fetcher.calls == 0


def test_existing_conflict_rolls_back_whole_batch(database: sqlite3.Connection) -> None:
    class First:
        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            return [row(Symbol=symbol)]

    bootstrap_daily_history(
        connection=database, client=First(), symbol="HPG", exchange="HOSE",
        from_date="17/09/2026", to_date="17/09/2026", as_of_date="18/09/2026",
    )

    class Conflict:
        def fetch_daily_ohlc(self, symbol: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
            return [row(Symbol=symbol, TradingDate="16/09/2026"), row(Symbol=symbol, Close=28800)]

    with pytest.raises(DailyHistoryConflict, match="Existing canonical"):
        bootstrap_daily_history(
            connection=database, client=Conflict(), symbol="HPG", exchange="HOSE",
            from_date="16/09/2026", to_date="17/09/2026", as_of_date="18/09/2026",
        )
    assert database.execute("SELECT trading_date FROM daily_bars").fetchall() == [("2026-09-17",)]
