from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

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
