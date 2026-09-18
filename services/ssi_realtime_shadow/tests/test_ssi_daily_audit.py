from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest

from app.daily_history import DailyBar
from app.ssi_daily_audit import (
    AuditTelemetryCollector,
    SSIAuditClient,
    SSIAuditConflict,
    SecurityRecord,
    audit_ma200_coverage,
    base_audit_document,
    classify_bulk_probe,
    compare_universes,
    main,
    plan_bootstrap,
    render_csv,
    render_json,
)
from app.ssi_historical import SSIHistoricalClient, SSIHistoricalError


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def token(value: str = "test-token") -> FakeResponse:
    return FakeResponse({"status": "SUCCESS", "data": {"accessToken": value}})


def envelope(
    rows: list[dict[str, Any]],
    total: int | None,
    *,
    headers: dict[str, str] | None = None,
) -> FakeResponse:
    payload: dict[str, Any] = {
        "status": "SUCCESS",
        "message": "SUCCESS",
        "dataList": rows,
    }
    if total is not None:
        payload["totalrecord"] = total
    return FakeResponse(payload, headers=headers)


def security(symbol: str, market: str) -> dict[str, Any]:
    return {"symbol": symbol, "market": market}


def daily_row(
    symbol: str = "HPG",
    market: str = "HOSE",
    trading_date: str = "17/09/2026",
    **updates: Any,
) -> dict[str, Any]:
    row = {
        "symbol": symbol,
        "market": market,
        "tradingdate": trading_date,
        "time": "",
        "open": 28000,
        "high": 28500,
        "low": 27900,
        "close": 28300,
        "volume": 1_000_000,
        "value": 28_300_000_000,
    }
    row.update(updates)
    return row


def historical_client(
    session: FakeSession,
    *,
    page_size: int = 1000,
    max_pages: int = 10,
    telemetry: AuditTelemetryCollector | None = None,
    sleeps: list[float] | None = None,
    consumer_id: str = "consumer-id",
    secret: str = "consumer-secret",
) -> SSIHistoricalClient:
    return SSIHistoricalClient(
        base_url="https://fc-data.ssi.com.vn/",
        consumer_id=consumer_id,
        consumer_secret=secret,
        session=session,
        page_size=page_size,
        max_pages_per_range=max_pages,
        telemetry_sink=telemetry,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def audit_client(
    responses: list[FakeResponse],
    *,
    page_size: int = 1000,
    max_pages: int = 10,
    telemetry: AuditTelemetryCollector | None = None,
) -> tuple[SSIAuditClient, FakeSession]:
    session = FakeSession([token(), *responses])
    return (
        SSIAuditClient(
            historical_client(
                session,
                page_size=page_size,
                max_pages=max_pages,
                telemetry=telemetry,
            )
        ),
        session,
    )


@pytest.mark.parametrize("market", ["HOSE", "HNX", "UPCOM"])
def test_securities_paginates_each_supported_market(market: str) -> None:
    client, session = audit_client(
        [
            envelope([security("AAA", market)], 2),
            envelope([security("BBB", market)], 2),
        ],
        page_size=1,
    )
    result = client.fetch_securities_market(market)
    assert result.records == (
        SecurityRecord("AAA", market), SecurityRecord("BBB", market)
    )
    assert session.calls[1]["params"]["market"] == market
    assert [call["params"]["pageIndex"] for call in session.calls[1:]] == [1, 2]


def test_securities_paginates_and_deduplicates() -> None:
    duplicate = security("AAA", "HOSE")
    client, session = audit_client(
        [
            envelope([duplicate, security("BBB", "HOSE")], 3),
            envelope([duplicate], 3),
        ],
        page_size=2,
    )
    result = client.fetch_securities_market("HSX")
    assert [row.symbol for row in result.records] == ["AAA", "BBB"]
    assert result.duplicates == 1 and result.pages == 2
    assert [call["params"]["pageIndex"] for call in session.calls[1:]] == [1, 2]


def test_securities_rejects_incomplete_pagination() -> None:
    client, _ = audit_client(
        [envelope([security("AAA", "HOSE")], 2), envelope([], 2)],
        page_size=1,
    )
    with pytest.raises(SSIHistoricalError, match="ended early"):
        client.fetch_securities_market("HOSE")


def test_securities_rejects_total_change_between_pages() -> None:
    client, _ = audit_client(
        [
            envelope([security("AAA", "HOSE")], 2),
            envelope([security("BBB", "HOSE")], 3),
        ],
        page_size=1,
    )
    with pytest.raises(SSIHistoricalError, match="changed"):
        client.fetch_securities_market("HOSE")


def test_securities_counts_malformed_rows_without_inventing_symbols() -> None:
    client, _ = audit_client(
        [envelope([security("AAA", "HOSE"), {"market": "HOSE"}], 2)]
    )
    result = client.fetch_securities_market("HOSE")
    assert result.records == (SecurityRecord("AAA", "HOSE"),)
    assert result.malformed_rows == 1


def test_universe_comparison_reports_all_four_categories_and_aliases() -> None:
    result = compare_universes(
        [
            {"symbol": "AAA", "exchange": "HSX"},
            {"symbol": "BBB", "exchange": "HNX"},
            {"symbol": "CCC", "exchange": "UPCOM"},
        ],
        [
            {"symbol": "AAA", "market": "HOSE"},
            {"symbol": "BBB", "market": "UPCOM"},
            {"symbol": "DDD", "market": "HNX"},
        ],
    )
    assert (result.matched, result.missing, result.exchange_mismatch, result.ssi_only) == (
        1, 1, 1, 1
    )
    assert {row.symbol: row.status for row in result.details} == {
        "AAA": "MATCHED",
        "BBB": "EXCHANGE_MISMATCH",
        "CCC": "MISSING_IN_SSI",
        "DDD": "SSI_ONLY",
    }


def test_bulk_request_omits_symbol_and_accepts_multi_symbol_page() -> None:
    client, session = audit_client(
        [envelope([daily_row("HPG"), daily_row("SHS", "HNX")], 2)]
    )
    result = client.fetch_bulk_daily_ohlc("17/09/2026")
    assert result.distinct_symbols == 2
    assert result.markets == ("HNX", "HOSE")
    assert "symbol" not in session.calls[1]["params"]
    assert classify_bulk_probe(result) == "SUPPORTED_AND_COMPLETE"


def test_bulk_multi_page_deduplicates_deterministically() -> None:
    duplicate = daily_row("HPG")
    client, _ = audit_client(
        [
            envelope([duplicate, daily_row("SHS", "HNX")], 3),
            envelope([duplicate], 3),
        ],
        page_size=2,
    )
    result = client.fetch_bulk_daily_ohlc("17/09/2026")
    assert result.pages == 2 and result.duplicates == 1
    assert result.distinct_symbols == 2


def test_bulk_conflicting_duplicate_is_rejected() -> None:
    client, _ = audit_client(
        [envelope([daily_row("HPG"), daily_row("HPG", close=28100)], 2)]
    )
    with pytest.raises(SSIAuditConflict, match="Conflicting bulk"):
        client.fetch_bulk_daily_ohlc("17/09/2026")


def test_bulk_incomplete_pagination_is_rejected() -> None:
    client, _ = audit_client(
        [envelope([daily_row("HPG")], 2), envelope([], 2)], page_size=1
    )
    with pytest.raises(SSIHistoricalError, match="ended early"):
        client.fetch_bulk_daily_ohlc("17/09/2026")


def test_bulk_capacity_overflow_is_rejected() -> None:
    client, _ = audit_client(
        [envelope([daily_row("HPG")], 2)], page_size=1, max_pages=1
    )
    with pytest.raises(SSIHistoricalError, match="exceeds pagination capacity"):
        client.fetch_bulk_daily_ohlc("17/09/2026")


def test_bulk_malformed_rows_make_capability_ambiguous() -> None:
    client, _ = audit_client(
        [envelope([daily_row("HPG"), {"market": "HOSE"}], 2)]
    )
    result = client.fetch_bulk_daily_ohlc("17/09/2026")
    assert result.malformed_rows == 1
    assert classify_bulk_probe(result) == "SUPPORTED_BUT_AMBIGUOUS"


def test_bulk_row_outside_requested_date_is_malformed() -> None:
    client, _ = audit_client(
        [envelope([daily_row("HPG", trading_date="16/09/2026")], 1)]
    )
    result = client.fetch_bulk_daily_ohlc("17/09/2026")
    assert result.rows == () and result.malformed_rows == 1
    assert classify_bulk_probe(result) == "SUPPORTED_BUT_AMBIGUOUS"


def test_rate_telemetry_captures_safe_headers_and_response_shape() -> None:
    collector = AuditTelemetryCollector()
    session = FakeSession([
        token(),
        envelope(
            [],
            0,
            headers={
                "X-RATELIMIT-LIMIT": "120",
                "X-RATELIMIT-REMAINING": "119",
                "X-RATELIMIT-RESET": "60",
            },
        ),
    ])
    client = historical_client(session, telemetry=collector)
    assert client.fetch_daily_ohlc("HPG", "17/09/2026", "17/09/2026") == []
    summary = collector.summary(path="api/v2/Market/DailyOhlc")
    assert summary["request_count"] == 1
    assert len(summary["request_durations_ms"]) == 1
    assert summary["request_durations_ms"][0] >= 0
    assert summary["rate_limit_observations"] == [{
        "limit": "120", "remaining": "119", "reset": "60", "retry_after": None
    }]
    assert summary["response_shapes_observed"] == [
        ["dataList", "message", "status", "totalrecord"]
    ]


def test_rate_telemetry_records_absent_headers_as_unavailable() -> None:
    collector = AuditTelemetryCollector()
    session = FakeSession([token(), envelope([], 0)])
    client = historical_client(session, telemetry=collector)
    client.fetch_daily_ohlc("HPG", "17/09/2026", "17/09/2026")
    event = [item for item in collector.events if item.path.endswith("DailyOhlc")][0]
    assert event.rate_limit_limit is None
    assert event.rate_limit_remaining is None
    assert event.rate_limit_reset is None
    assert event.retry_after is None


def test_rate_telemetry_records_429_retry_and_retry_after() -> None:
    collector = AuditTelemetryCollector()
    sleeps: list[float] = []
    session = FakeSession([
        token(),
        FakeResponse({}, 429, {"Retry-After": "3"}),
        envelope([], 0),
    ])
    client = historical_client(
        session, telemetry=collector, sleeps=sleeps
    )
    client.fetch_daily_ohlc("HPG", "17/09/2026", "17/09/2026")
    summary = collector.summary(path="api/v2/Market/DailyOhlc")
    assert summary["request_count"] == 2
    assert summary["retry_count"] == 1
    assert summary["http_429_count"] == 1
    assert summary["rate_limit_observations"][0]["retry_after"] == "3"
    assert sleeps == [3.0]


def completed_bars(
    count: int,
    *,
    symbol: str = "HPG",
    exchange: str = "HOSE",
) -> list[DailyBar]:
    start = date(2025, 1, 1)
    return [
        DailyBar(
            symbol=symbol,
            trading_date=(start + timedelta(days=index)).isoformat(),
            exchange=exchange,
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1000 + index,
            value=None,
        )
        for index in range(count)
    ]


def coverage(rows: list[DailyBar | dict[str, Any]]) -> Any:
    return audit_ma200_coverage(
        [SecurityRecord("HPG", "HOSE")],
        {"HPG": rows},
        as_of_date="2026-09-18",
    )[0]


def test_ma_coverage_200_valid_sessions_is_ready() -> None:
    result = coverage(completed_bars(200))
    assert result.status == "MA200_READY"
    assert result.ma10_ready and result.ma200_ready
    assert result.trusted_valid_sessions == 200


def test_ma_coverage_199_sessions_is_insufficient() -> None:
    result = coverage(completed_bars(199))
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.ma10_ready and not result.ma200_ready


def test_ma_coverage_zero_rows_is_no_history() -> None:
    assert coverage([]).status == "NO_SSI_HISTORY"


def test_ma_coverage_degraded_required_window_is_not_ready() -> None:
    bars = completed_bars(201)
    degraded = bars[-1]
    bars[-1] = DailyBar(
        symbol=degraded.symbol,
        trading_date=degraded.trading_date,
        exchange=degraded.exchange,
        open=degraded.open,
        high=degraded.high,
        low=degraded.low,
        close=degraded.close,
        volume=degraded.volume,
        value=degraded.value,
        quality_status="DEGRADED",
    )
    result = coverage(bars)
    assert result.status == "INSUFFICIENT_HISTORY"
    assert not result.ma200_ready


def test_ma_coverage_invalid_provider_row_is_not_ready() -> None:
    rows: list[dict[str, Any]] = [daily_row(high=27000)]
    assert coverage(rows).status == "INVALID_PROVIDER_DATA"


def test_ma_coverage_excludes_same_day_incomplete_row() -> None:
    rows: list[DailyBar | dict[str, Any]] = completed_bars(200)
    rows.append(daily_row(trading_date="18/09/2026", close=999999, high=999999))
    result = coverage(rows)
    assert result.status == "MA200_READY"
    assert result.returned_completed_sessions == 200


def test_ma_coverage_exchange_mismatch() -> None:
    assert coverage([daily_row(market="HNX")]).status == "EXCHANGE_MISMATCH"


def test_ma_coverage_provider_error_and_not_audited() -> None:
    reference = [SecurityRecord("HPG", "HOSE"), SecurityRecord("SHS", "HNX")]
    results = audit_ma200_coverage(
        reference,
        {},
        as_of_date="2026-09-18",
        provider_errors={"HPG": "timeout"},
    )
    assert [row.status for row in results] == ["PROVIDER_ERROR", "NOT_AUDITED"]


def test_planner_thirty_day_boundaries_and_multi_year_range() -> None:
    thirty = plan_bootstrap(
        universe_size=10, from_date="01/01/2025", to_date="30/01/2025",
        expected_rows_per_symbol=20,
    )
    thirty_one = plan_bootstrap(
        universe_size=10, from_date="01/01/2025", to_date="31/01/2025",
        expected_rows_per_symbol=21,
    )
    multi_year = plan_bootstrap(
        universe_size=10, from_date="01/01/2020", to_date="31/12/2024",
        expected_rows_per_symbol=1250,
    )
    assert thirty.date_chunks == 1
    assert thirty_one.date_chunks == 2
    assert multi_year.date_chunks == 61


def test_planner_per_symbol_and_bulk_estimates_without_invented_rate() -> None:
    plan = plan_bootstrap(
        universe_size=800,
        from_date="01/01/2025",
        to_date="31/12/2025",
        page_size=1000,
        expected_rows_per_symbol=250,
        bulk_status="NOT_TESTED",
    )
    assert plan.date_chunks == 13
    assert plan.per_symbol_estimated_requests == 10_400
    assert plan.bulk_estimated_requests is None
    assert plan.per_symbol_elapsed_seconds is None
    assert plan.recommended_strategy == "UNKNOWN"


def test_planner_observed_rate_produces_deterministic_elapsed_estimate() -> None:
    plan = plan_bootstrap(
        universe_size=10,
        from_date="01/01/2025",
        to_date="31/12/2025",
        page_size=100,
        expected_rows_per_symbol=300,
        bulk_status="SUPPORTED_AND_COMPLETE",
        observed_safe_requests_per_second=2,
    )
    assert plan.per_symbol_estimated_requests == 130
    assert plan.bulk_estimated_requests == 39
    assert plan.per_symbol_elapsed_seconds == pytest.approx(65)
    assert plan.bulk_elapsed_seconds == pytest.approx(19.5)
    assert plan.recommended_strategy == "BULK"


def test_planner_reports_bulk_pagination_capacity_risk() -> None:
    plan = plan_bootstrap(
        universe_size=800,
        from_date="01/01/2025",
        to_date="30/01/2025",
        expected_rows_per_symbol=30,
        bulk_status="SUPPORTED_AND_COMPLETE",
        observed_safe_requests_per_second=1,
    )
    assert plan.bulk_capacity_risk is True
    assert plan.recommended_strategy == "UNKNOWN"


def test_json_csv_and_telemetry_outputs_never_expose_sentinel_secrets() -> None:
    consumer_id = "CONSUMER_ID_SENTINEL"
    secret = "CONSUMER_SECRET_SENTINEL"
    access_token = "ACCESS_TOKEN_SENTINEL"
    supabase_key = "SUPABASE_KEY_SENTINEL"
    bearer = f"Bearer {access_token}"
    collector = AuditTelemetryCollector()
    session = FakeSession([token(access_token), envelope([], 0)])
    client = historical_client(
        session, telemetry=collector, consumer_id=consumer_id, secret=secret
    )
    client.fetch_daily_ohlc("HPG", "17/09/2026", "17/09/2026")
    document = base_audit_document(
        environment_label="test", base_url="https://user:password@ssi.example/path"
    )
    document["provider"].update(collector.summary())
    document["diagnostic"] = f"{secret} {access_token} {bearer} {supabase_key}"
    secrets = (secret, access_token, bearer, supabase_key)
    rendered_json = render_json(document, secrets=secrets)
    rendered_csv = render_csv([document["provider"]], secrets=secrets)
    for sentinel in secrets:
        assert sentinel not in rendered_json
        assert sentinel not in rendered_csv
        assert sentinel not in repr(collector.events)
    assert consumer_id not in rendered_json
    assert consumer_id not in rendered_csv
    assert consumer_id not in repr(collector.events)
    assert document["metadata"]["ssi_base_host"] == "https://ssi.example"
    json.loads(rendered_json)


def test_plan_cli_prints_valid_json_without_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([
        "plan", "--universe-size", "800", "--from-date", "01/01/2025",
        "--to-date", "31/12/2025", "--expected-rows-per-symbol", "250",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["planner"]["per_symbol_estimated_requests"] == 10_400


def test_plan_cli_writes_valid_json_and_csv(
    tmp_path: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_path = tmp_path / "audit.json"
    csv_path = tmp_path / "audit.csv"
    assert main([
        "plan", "--universe-size", "10", "--from-date", "01/01/2025",
        "--to-date", "30/01/2025", "--expected-rows-per-symbol", "20",
        "--json-out", str(json_path), "--csv-out", str(csv_path),
    ]) == 0
    json.loads(json_path.read_text(encoding="utf-8"))
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "per_symbol_estimated_requests" in csv_text
    json.loads(capsys.readouterr().out)
