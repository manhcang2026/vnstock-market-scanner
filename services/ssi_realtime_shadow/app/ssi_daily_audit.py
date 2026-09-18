"""Read-only SSI daily-history audit harness and bootstrap planner."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .daily_history import DailyBar, normalize_daily_ohlc_record
from .daily_ma import DailyClose, calculate_moving_averages
from .market_session import normalize_exchange
from .normalization import parse_trading_date
from .ssi_historical import (
    DAILY_MAX_RANGE_DAYS,
    DAILY_OHLC_PATH,
    MAX_PAGE_INDEX,
    SSIHTTPError,
    SSIHistoricalClient,
    SSIHistoricalError,
    SSIRequestTelemetry,
)


AUDIT_VERSION = "2.0.0"
SECURITIES_PATH = "api/v2/Market/Securities"
SUPPORTED_EXCHANGES = ("HOSE", "HNX", "UPCOM")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}$")
BULK_STATUSES = {
    "SUPPORTED_AND_COMPLETE",
    "SUPPORTED_BUT_AMBIGUOUS",
    "NOT_SUPPORTED",
    "NOT_TESTED",
}
COVERAGE_STATUSES = {
    "MA200_READY",
    "INSUFFICIENT_HISTORY",
    "NO_SSI_HISTORY",
    "EXCHANGE_MISMATCH",
    "INVALID_PROVIDER_DATA",
    "PROVIDER_ERROR",
    "NOT_AUDITED",
}


class SSIAuditError(RuntimeError):
    """Raised when audit evidence is incomplete or contradictory."""


class SSIAuditConflict(SSIAuditError):
    """Raised for conflicting provider rows sharing one canonical identity."""


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return None


def _canonical_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_trading_date(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid trading date")
    return date.fromisoformat(parsed)


def _canonical_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"Invalid symbol: {value!r}")
    return symbol


@dataclass(frozen=True, slots=True)
class SecurityRecord:
    symbol: str
    exchange: str


@dataclass(frozen=True, slots=True)
class SecuritiesFetchResult:
    market: str
    records: tuple[SecurityRecord, ...]
    raw_rows: int
    totalrecord: int | None
    pages: int
    duplicates: int
    malformed_rows: int
    response_shapes: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class SSIUniverseResult:
    records: tuple[SecurityRecord, ...]
    markets: tuple[SecuritiesFetchResult, ...]


@dataclass(frozen=True, slots=True)
class UniverseAuditRow:
    symbol: str
    ccc_exchange: str | None
    ssi_exchange: str | None
    status: str


@dataclass(frozen=True, slots=True)
class UniverseAuditResult:
    details: tuple[UniverseAuditRow, ...]
    total_ccc: int
    matched: int
    missing: int
    exchange_mismatch: int
    ssi_only: int


@dataclass(frozen=True, slots=True)
class BulkDailyResult:
    rows: tuple[Mapping[str, Any], ...]
    totalrecord: int | None
    pages: int
    distinct_symbols: int
    markets: tuple[str, ...]
    duplicates: int
    malformed_rows: int
    response_shapes: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class HistoryCoverageRow:
    symbol: str
    expected_exchange: str
    returned_completed_sessions: int
    earliest_session: str | None
    latest_session: str | None
    trusted_valid_sessions: int
    ma10_ready: bool
    ma200_ready: bool
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class BootstrapPlan:
    universe_size: int
    from_date: str
    to_date: str
    date_chunks: int
    page_size: int
    page_index_capacity: int
    per_symbol_estimated_requests: int
    bulk_estimated_requests: int | None
    per_symbol_capacity_risk: bool
    bulk_capacity_risk: bool | None
    observed_safe_requests_per_second: float | None
    per_symbol_elapsed_seconds: float | None
    bulk_elapsed_seconds: float | None
    recommended_strategy: str


class AuditTelemetryCollector:
    """In-memory collector containing no request headers, bodies, or tokens."""

    def __init__(self) -> None:
        self.events: list[SSIRequestTelemetry] = []

    def __call__(self, event: SSIRequestTelemetry) -> None:
        self.events.append(event)

    def summary(self, *, path: str | None = None) -> dict[str, Any]:
        events = [event for event in self.events if path is None or event.path == path]
        rate_observations = [
            {
                "limit": event.rate_limit_limit,
                "remaining": event.rate_limit_remaining,
                "reset": event.rate_limit_reset,
                "retry_after": event.retry_after,
            }
            for event in events
            if any(
                value is not None
                for value in (
                    event.rate_limit_limit,
                    event.rate_limit_remaining,
                    event.rate_limit_reset,
                    event.retry_after,
                )
            )
        ]
        shapes = sorted(
            {event.response_keys for event in events if event.response_keys is not None}
        )
        return {
            "request_count": len(events),
            "retry_count": sum(event.is_retry for event in events),
            "http_429_count": sum(event.http_status == 429 for event in events),
            "request_durations_ms": [event.duration_ms for event in events],
            "rate_limit_observations": rate_observations,
            "response_shapes_observed": [list(shape) for shape in shapes],
        }


class SSIAuditClient:
    """Read-only audit methods reusing the authenticated historical client."""

    def __init__(self, historical: SSIHistoricalClient) -> None:
        self.historical = historical

    def _fetch_paged(
        self,
        *,
        path: str,
        endpoint_name: str,
        params: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], int | None, int, tuple[tuple[str, ...], ...]]:
        rows: list[dict[str, Any]] = []
        total: int | None = None
        shapes: set[tuple[str, ...]] = set()
        pages = 0
        capacity = self.historical.page_size * self.historical.max_pages_per_range
        for page_index in range(1, self.historical.max_pages_per_range + 1):
            payload = self.historical._request_json(
                "GET",
                path,
                params={
                    **params,
                    "pageIndex": page_index,
                    "pageSize": self.historical.page_size,
                },
                authenticated=True,
            )
            pages += 1
            shapes.add(tuple(sorted(str(key) for key in payload)))
            page_rows, page_total = self.historical._rows_and_total(
                payload, endpoint_name
            )
            if page_index == 1:
                total = page_total
                if total is not None and total > capacity:
                    raise SSIHistoricalError(
                        f"SSI {endpoint_name} total {total} exceeds pagination "
                        f"capacity {capacity}"
                    )
            elif page_total != total:
                raise SSIHistoricalError(
                    f"SSI {endpoint_name} totalrecord changed while paging"
                )
            rows.extend(page_rows)
            if total is not None:
                if len(rows) >= total:
                    break
                if not page_rows:
                    raise SSIHistoricalError(
                        f"SSI {endpoint_name} pagination ended early: "
                        f"{len(rows)}/{total}"
                    )
            elif len(page_rows) < self.historical.page_size:
                break
        if total is not None and len(rows) != total:
            raise SSIHistoricalError(
                f"SSI {endpoint_name} pagination incomplete: {len(rows)}/{total}"
            )
        if total is None and len(rows) >= capacity:
            raise SSIHistoricalError(
                f"SSI {endpoint_name} omitted totalrecord at pagination capacity"
            )
        return rows, total, pages, tuple(sorted(shapes))

    def fetch_securities_market(self, market: str) -> SecuritiesFetchResult:
        expected = normalize_exchange(market)
        raw_rows, total, pages, shapes = self._fetch_paged(
            path=SECURITIES_PATH,
            endpoint_name="Securities",
            params={"market": expected},
        )
        unique: dict[str, SecurityRecord] = {}
        duplicates = malformed = 0
        for raw in raw_rows:
            try:
                symbol = _canonical_symbol(_first(raw, "symbol", "Symbol"))
                raw_exchange = _first(
                    raw, "market", "Market", "exchange", "Exchange"
                )
                exchange = normalize_exchange(
                    str(raw_exchange) if raw_exchange not in (None, "") else expected
                )
            except ValueError:
                malformed += 1
                continue
            record = SecurityRecord(symbol, exchange)
            existing = unique.get(symbol)
            if existing is None:
                unique[symbol] = record
            elif existing == record:
                duplicates += 1
            else:
                raise SSIAuditConflict(
                    f"Conflicting SSI Securities rows for {symbol}"
                )
        return SecuritiesFetchResult(
            market=expected,
            records=tuple(unique[key] for key in sorted(unique)),
            raw_rows=len(raw_rows),
            totalrecord=total,
            pages=pages,
            duplicates=duplicates,
            malformed_rows=malformed,
            response_shapes=shapes,
        )

    def fetch_securities_universe(self) -> SSIUniverseResult:
        market_results = tuple(
            self.fetch_securities_market(market) for market in SUPPORTED_EXCHANGES
        )
        unique: dict[str, SecurityRecord] = {}
        for result in market_results:
            for record in result.records:
                existing = unique.get(record.symbol)
                if existing is not None and existing != record:
                    raise SSIAuditConflict(
                        f"SSI lists {record.symbol} on multiple exchanges"
                    )
                unique[record.symbol] = record
        return SSIUniverseResult(
            records=tuple(unique[key] for key in sorted(unique)),
            markets=market_results,
        )

    def fetch_bulk_daily_ohlc(self, trading_date: date | str) -> BulkDailyResult:
        target = _canonical_date(trading_date, "trading_date")
        raw_rows, total, pages, shapes = self._fetch_paged(
            path=DAILY_OHLC_PATH,
            endpoint_name="DailyOhlc bulk",
            params={
                "fromDate": target.strftime("%d/%m/%Y"),
                "toDate": target.strftime("%d/%m/%Y"),
                "ascending": True,
            },
        )
        unique: dict[tuple[str, str], Mapping[str, Any]] = {}
        markets: set[str] = set()
        duplicates = malformed = 0
        for raw in raw_rows:
            try:
                symbol = _canonical_symbol(_first(raw, "symbol", "Symbol"))
                trading_day = parse_trading_date(
                    _first(
                        raw,
                        "tradingdate",
                        "TradingDate",
                        "tradingDate",
                        "trading_date",
                    )
                )
                if trading_day is None:
                    raise ValueError("invalid trading date")
                if date.fromisoformat(trading_day) != target:
                    raise ValueError("row is outside requested bulk date")
                exchange = normalize_exchange(
                    str(_first(raw, "market", "Market", "exchange", "Exchange") or "")
                )
            except ValueError:
                malformed += 1
                continue
            key = (symbol, trading_day)
            existing = unique.get(key)
            if existing is None:
                unique[key] = raw
                markets.add(exchange)
            elif dict(existing) == dict(raw):
                duplicates += 1
            else:
                raise SSIAuditConflict(
                    f"Conflicting bulk DailyOhlc rows for {symbol}/{trading_day}"
                )
        return BulkDailyResult(
            rows=tuple(unique[key] for key in sorted(unique)),
            totalrecord=total,
            pages=pages,
            distinct_symbols=len({key[0] for key in unique}),
            markets=tuple(sorted(markets)),
            duplicates=duplicates,
            malformed_rows=malformed,
            response_shapes=shapes,
        )


def normalize_reference_universe(
    rows: Iterable[SecurityRecord | Mapping[str, Any]],
) -> tuple[SecurityRecord, ...]:
    unique: dict[str, SecurityRecord] = {}
    for raw in rows:
        if isinstance(raw, SecurityRecord):
            record = SecurityRecord(
                _canonical_symbol(raw.symbol), normalize_exchange(raw.exchange)
            )
        else:
            record = SecurityRecord(
                _canonical_symbol(_first(raw, "symbol", "Symbol")),
                normalize_exchange(
                    str(_first(raw, "exchange", "Exchange", "market", "Market") or "")
                ),
            )
        existing = unique.get(record.symbol)
        if existing is not None and existing != record:
            raise SSIAuditConflict(
                f"Conflicting CCC reference rows for {record.symbol}"
            )
        unique[record.symbol] = record
    return tuple(unique[key] for key in sorted(unique))


def compare_universes(
    ccc_rows: Iterable[SecurityRecord | Mapping[str, Any]],
    ssi_rows: Iterable[SecurityRecord | Mapping[str, Any]],
) -> UniverseAuditResult:
    ccc = {row.symbol: row for row in normalize_reference_universe(ccc_rows)}
    ssi = {row.symbol: row for row in normalize_reference_universe(ssi_rows)}
    details: list[UniverseAuditRow] = []
    for symbol, ccc_row in sorted(ccc.items()):
        ssi_row = ssi.get(symbol)
        if ssi_row is None:
            status = "MISSING_IN_SSI"
        elif ssi_row.exchange != ccc_row.exchange:
            status = "EXCHANGE_MISMATCH"
        else:
            status = "MATCHED"
        details.append(
            UniverseAuditRow(
                symbol,
                ccc_row.exchange,
                ssi_row.exchange if ssi_row else None,
                status,
            )
        )
    for symbol, ssi_row in sorted(ssi.items()):
        if symbol not in ccc:
            details.append(
                UniverseAuditRow(symbol, None, ssi_row.exchange, "SSI_ONLY")
            )
    counts = {status: 0 for status in (
        "MATCHED", "MISSING_IN_SSI", "EXCHANGE_MISMATCH", "SSI_ONLY"
    )}
    for row in details:
        counts[row.status] += 1
    return UniverseAuditResult(
        details=tuple(details),
        total_ccc=len(ccc),
        matched=counts["MATCHED"],
        missing=counts["MISSING_IN_SSI"],
        exchange_mismatch=counts["EXCHANGE_MISMATCH"],
        ssi_only=counts["SSI_ONLY"],
    )


def _raw_exchange(raw: Mapping[str, Any]) -> str | None:
    value = _first(raw, "market", "Market", "exchange", "Exchange")
    if value in (None, ""):
        return None
    try:
        return normalize_exchange(str(value))
    except ValueError:
        return None


def audit_ma200_coverage(
    reference_rows: Iterable[SecurityRecord | Mapping[str, Any]],
    rows_by_symbol: Mapping[str, Sequence[DailyBar | Mapping[str, Any]]],
    *,
    as_of_date: date | str,
    provider_errors: Mapping[str, str] | None = None,
) -> tuple[HistoryCoverageRow, ...]:
    cutoff = _canonical_date(as_of_date, "as_of_date")
    provider_errors = {
        str(key).strip().upper(): str(value)
        for key, value in (provider_errors or {}).items()
    }
    supplied = {str(key).strip().upper(): value for key, value in rows_by_symbol.items()}
    results: list[HistoryCoverageRow] = []
    for reference in normalize_reference_universe(reference_rows):
        symbol = reference.symbol
        if symbol in provider_errors:
            results.append(
                HistoryCoverageRow(
                    symbol, reference.exchange, 0, None, None, 0, False, False,
                    "PROVIDER_ERROR", provider_errors[symbol],
                )
            )
            continue
        if symbol not in supplied:
            results.append(
                HistoryCoverageRow(
                    symbol, reference.exchange, 0, None, None, 0, False, False,
                    "NOT_AUDITED", "No audit result supplied",
                )
            )
            continue

        canonical: dict[str, DailyBar] = {}
        invalid = 0
        mismatch = False
        for raw in supplied[symbol]:
            if isinstance(raw, DailyBar):
                bar = raw
                if normalize_exchange(bar.exchange) != reference.exchange:
                    mismatch = True
                    continue
                parsed = parse_trading_date(bar.trading_date)
                if parsed is None:
                    invalid += 1
                    continue
                if date.fromisoformat(parsed) >= cutoff:
                    continue
            else:
                parsed = parse_trading_date(
                    _first(
                        raw,
                        "tradingdate",
                        "TradingDate",
                        "tradingDate",
                        "trading_date",
                    )
                )
                if parsed is not None and date.fromisoformat(parsed) >= cutoff:
                    continue
                returned_exchange = _raw_exchange(raw)
                if returned_exchange is not None and returned_exchange != reference.exchange:
                    mismatch = True
                    continue
                bar = normalize_daily_ohlc_record(
                    raw,
                    exchange_hint=reference.exchange,
                    as_of_date=cutoff,
                )
                if bar is None:
                    invalid += 1
                    continue
            existing = canonical.get(bar.trading_date)
            if existing is not None and existing != bar:
                invalid += 1
                continue
            canonical[bar.trading_date] = bar

        bars = tuple(canonical[key] for key in sorted(canonical))
        closes = tuple(
            DailyClose(bar.trading_date, bar.close, bar.quality_status)
            for bar in bars
        )
        trusted = sum(
            close.quality_status == "TRUSTED"
            and math.isfinite(close.close)
            and close.close > 0
            for close in closes
        )
        earliest = bars[0].trading_date if bars else None
        latest = bars[-1].trading_date if bars else None
        if mismatch:
            status, reason = "EXCHANGE_MISMATCH", "SSI exchange differs from CCC"
            ma10_ready = ma200_ready = False
        elif invalid:
            status, reason = "INVALID_PROVIDER_DATA", f"{invalid} invalid/conflicting rows"
            ma10_ready = ma200_ready = False
        elif not bars:
            status, reason = "NO_SSI_HISTORY", "No completed SSI daily history"
            ma10_ready = ma200_ready = False
        else:
            ma = calculate_moving_averages(
                symbol=symbol, as_of_date=cutoff, bars=closes
            )
            ma10_ready = ma.ma10 is not None
            ma200_ready = ma.ma200 is not None
            if ma200_ready:
                status, reason = "MA200_READY", "Exact trusted MA200 window available"
            else:
                status = "INSUFFICIENT_HISTORY"
                reason = ma.ma200_reason or "MA200 unavailable"
        results.append(
            HistoryCoverageRow(
                symbol=symbol,
                expected_exchange=reference.exchange,
                returned_completed_sessions=len(bars),
                earliest_session=earliest,
                latest_session=latest,
                trusted_valid_sessions=trusted,
                ma10_ready=ma10_ready,
                ma200_ready=ma200_ready,
                status=status,
                reason=reason,
            )
        )
    return tuple(results)


def plan_bootstrap(
    *,
    universe_size: int,
    from_date: date | str,
    to_date: date | str,
    page_size: int = 1000,
    max_page_index: int = MAX_PAGE_INDEX,
    expected_rows_per_symbol: int,
    bulk_status: str = "NOT_TESTED",
    observed_safe_requests_per_second: float | None = None,
) -> BootstrapPlan:
    if universe_size < 1 or expected_rows_per_symbol < 0:
        raise ValueError("universe_size must be positive and rows nonnegative")
    if not 1 <= page_size <= 1000 or not 1 <= max_page_index <= MAX_PAGE_INDEX:
        raise ValueError("page size/index exceed SSI contract")
    if bulk_status not in BULK_STATUSES:
        raise ValueError("invalid bulk_status")
    if observed_safe_requests_per_second is not None and observed_safe_requests_per_second <= 0:
        raise ValueError("observed safe rate must be positive")
    start = _canonical_date(from_date, "from_date")
    end = _canonical_date(to_date, "to_date")
    if start > end:
        raise ValueError("from_date must not be after to_date")
    chunks = math.ceil(((end - start).days + 1) / DAILY_MAX_RANGE_DAYS)
    average_symbol_rows_per_chunk = math.ceil(expected_rows_per_symbol / chunks)
    symbol_pages_per_chunk = max(1, math.ceil(average_symbol_rows_per_chunk / page_size))
    per_symbol_requests = universe_size * chunks * symbol_pages_per_chunk
    capacity = page_size * max_page_index
    per_symbol_risk = average_symbol_rows_per_chunk > capacity

    bulk_requests: int | None = None
    bulk_risk: bool | None = None
    if bulk_status == "SUPPORTED_AND_COMPLETE":
        average_bulk_rows_per_chunk = average_symbol_rows_per_chunk * universe_size
        bulk_pages_per_chunk = max(1, math.ceil(average_bulk_rows_per_chunk / page_size))
        bulk_requests = chunks * bulk_pages_per_chunk
        bulk_risk = average_bulk_rows_per_chunk > capacity

    per_elapsed = bulk_elapsed = None
    recommended = "UNKNOWN"
    if observed_safe_requests_per_second is not None:
        per_elapsed = per_symbol_requests / observed_safe_requests_per_second
        if bulk_requests is not None:
            bulk_elapsed = bulk_requests / observed_safe_requests_per_second
        if bulk_status == "SUPPORTED_AND_COMPLETE" and bulk_risk is False:
            recommended = "BULK" if bulk_requests < per_symbol_requests else "PER_SYMBOL"
        elif bulk_status == "NOT_SUPPORTED":
            recommended = "PER_SYMBOL"
    return BootstrapPlan(
        universe_size=universe_size,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        date_chunks=chunks,
        page_size=page_size,
        page_index_capacity=capacity,
        per_symbol_estimated_requests=per_symbol_requests,
        bulk_estimated_requests=bulk_requests,
        per_symbol_capacity_risk=per_symbol_risk,
        bulk_capacity_risk=bulk_risk,
        observed_safe_requests_per_second=observed_safe_requests_per_second,
        per_symbol_elapsed_seconds=per_elapsed,
        bulk_elapsed_seconds=bulk_elapsed,
        recommended_strategy=recommended,
    )


def classify_bulk_probe(
    result: BulkDailyResult | None, error: Exception | None = None
) -> str:
    if result is None and error is None:
        return "NOT_TESTED"
    if error is not None:
        if isinstance(error, SSIHTTPError) and error.status_code in {400, 404, 405}:
            return "NOT_SUPPORTED"
        return "SUPPORTED_BUT_AMBIGUOUS"
    assert result is not None
    if result.totalrecord is None or result.malformed_rows:
        return "SUPPORTED_BUT_AMBIGUOUS"
    return "SUPPORTED_AND_COMPLETE"


def _safe_base_host(base_url: str) -> str:
    parsed = urlsplit(base_url)
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{hostname}{port}" if parsed.scheme else hostname + port


def base_audit_document(
    *,
    environment_label: str,
    base_url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    universe_count: int = 0,
    exchanges: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "metadata": {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "environment_label": environment_label,
            "ssi_base_host": _safe_base_host(base_url),
            "requested_date_range": {"from": from_date, "to": to_date},
            "universe_count": universe_count,
            "exchanges": list(exchanges),
        },
        "provider": {
            "endpoint": None,
            "response_shapes_observed": [],
            "rate_limit_observations": [],
            "request_count": 0,
            "retry_count": 0,
            "http_429_count": 0,
            "request_durations_ms": [],
        },
        "universe": {
            "total_ccc": universe_count,
            "matched": 0,
            "missing": 0,
            "exchange_mismatch": 0,
            "ssi_only": 0,
        },
        "history": {
            "audited_symbols": 0,
            "ma10_ready": 0,
            "ma200_ready": 0,
            "insufficient": 0,
            "no_history": 0,
            "provider_errors": 0,
        },
        "bulk_probe": {
            "status": "NOT_TESTED",
            "totalrecord": None,
            "pages": None,
            "distinct_symbols": None,
            "completeness_notes": None,
        },
        "planner": {
            "per_symbol_estimated_requests": None,
            "bulk_estimated_requests": None,
            "observed_safe_rate_information": None,
            "estimated_elapsed_time": None,
            "recommended_strategy": "UNKNOWN",
        },
    }


def redact_secrets(value: Any, secrets: Iterable[str]) -> Any:
    protected = tuple(secret for secret in secrets if secret)
    if isinstance(value, str):
        result = value
        for secret in protected:
            result = result.replace(secret, "[REDACTED]")
        return result
    if isinstance(value, dict):
        return {key: redact_secrets(item, protected) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item, protected) for item in value]
    return value


def render_json(document: Mapping[str, Any], *, secrets: Iterable[str] = ()) -> str:
    safe = redact_secrets(dict(document), secrets)
    return json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True)


def render_csv(
    rows: Iterable[Mapping[str, Any]], *, secrets: Iterable[str] = ()
) -> str:
    safe_rows = [redact_secrets(dict(row), secrets) for row in rows]
    if not safe_rows:
        return ""
    fieldnames = sorted({key for row in safe_rows for key in row})
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in safe_rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()


def load_universe_file(path: Path) -> tuple[SecurityRecord, ...]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("universe")
        if not isinstance(payload, list):
            raise ValueError("JSON universe must be a list or contain universe list")
        return normalize_reference_universe(payload)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return normalize_reference_universe(csv.DictReader(handle))


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--csv-out", type=Path)


def _emit_outputs(
    document: Mapping[str, Any],
    details: Iterable[Mapping[str, Any]],
    args: argparse.Namespace,
) -> None:
    secrets = (
        os.getenv("SSI_CONSUMER_SECRET", ""),
        os.getenv("SUPABASE_KEY", ""),
    )
    json_text = render_json(document, secrets=secrets)
    csv_text = render_csv(details, secrets=secrets)
    if getattr(args, "json_out", None):
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json_text + "\n", encoding="utf-8")
    if getattr(args, "csv_out", None):
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        args.csv_out.write_text(csv_text, encoding="utf-8")
    print(json_text)


def _client_from_process_environment(
    telemetry: AuditTelemetryCollector,
    *,
    page_size: int = 1000,
) -> SSIHistoricalClient:
    consumer_id = os.getenv("SSI_CONSUMER_ID", "")
    consumer_secret = os.getenv("SSI_CONSUMER_SECRET", "")
    if not consumer_id or not consumer_secret:
        raise RuntimeError("SSI credentials are unavailable in the process environment")
    return SSIHistoricalClient(
        base_url=os.getenv("SSI_URL", "https://fc-data.ssi.com.vn/"),
        consumer_id=consumer_id,
        consumer_secret=consumer_secret,
        auth_type=os.getenv("SSI_AUTH_TYPE", "Bearer"),
        page_size=page_size,
        telemetry_sink=telemetry,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-label", default="local-audit")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--universe-size", type=int, required=True)
    plan.add_argument("--from-date", required=True)
    plan.add_argument("--to-date", required=True)
    plan.add_argument("--expected-rows-per-symbol", type=int, required=True)
    plan.add_argument("--page-size", type=int, default=1000)
    plan.add_argument("--bulk-status", choices=sorted(BULK_STATUSES), default="NOT_TESTED")
    plan.add_argument("--observed-safe-rps", type=float)
    _add_output_arguments(plan)

    universe = subparsers.add_parser("universe")
    universe.add_argument("--universe-file", type=Path, required=True)
    universe.add_argument("--page-size", type=int, default=1000)
    _add_output_arguments(universe)

    bulk = subparsers.add_parser("bulk")
    bulk.add_argument("--date", required=True)
    bulk.add_argument("--page-size", type=int, default=1000)
    _add_output_arguments(bulk)

    probe = subparsers.add_parser("probe")
    probe.add_argument("--symbol", action="append", required=True)
    probe.add_argument("--from-date", required=True)
    probe.add_argument("--to-date", required=True)
    probe.add_argument("--as-of-date", required=True)
    _add_output_arguments(probe)

    coverage = subparsers.add_parser("coverage")
    coverage.add_argument("--universe-file", type=Path, required=True)
    coverage.add_argument("--history-file", type=Path, required=True)
    coverage.add_argument("--provider-errors-file", type=Path)
    coverage.add_argument("--as-of-date", required=True)
    _add_output_arguments(coverage)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_url = os.getenv("SSI_URL", "https://fc-data.ssi.com.vn/")
    if args.mode == "plan":
        plan = plan_bootstrap(
            universe_size=args.universe_size,
            from_date=args.from_date,
            to_date=args.to_date,
            page_size=args.page_size,
            expected_rows_per_symbol=args.expected_rows_per_symbol,
            bulk_status=args.bulk_status,
            observed_safe_requests_per_second=args.observed_safe_rps,
        )
        document = base_audit_document(
            environment_label=args.environment_label,
            base_url=base_url,
            from_date=plan.from_date,
            to_date=plan.to_date,
            universe_count=plan.universe_size,
        )
        document["planner"] = asdict(plan)
        _emit_outputs(document, [asdict(plan)], args)
        return 0

    if args.mode == "coverage":
        ccc = load_universe_file(args.universe_file)
        history_payload = json.loads(args.history_file.read_text(encoding="utf-8"))
        if not isinstance(history_payload, dict):
            raise ValueError("history file must be a symbol-to-rows JSON object")
        errors: Mapping[str, str] = {}
        if args.provider_errors_file:
            loaded_errors = json.loads(
                args.provider_errors_file.read_text(encoding="utf-8")
            )
            if not isinstance(loaded_errors, dict):
                raise ValueError("provider errors file must be a JSON object")
            errors = {str(key): str(value) for key, value in loaded_errors.items()}
        coverage_rows = audit_ma200_coverage(
            ccc,
            history_payload,
            as_of_date=args.as_of_date,
            provider_errors=errors,
        )
        document = base_audit_document(
            environment_label=args.environment_label,
            base_url=base_url,
            to_date=args.as_of_date,
            universe_count=len(ccc),
            exchanges=sorted({row.exchange for row in ccc}),
        )
        document["history"] = {
            "audited_symbols": sum(row.status != "NOT_AUDITED" for row in coverage_rows),
            "ma10_ready": sum(row.ma10_ready for row in coverage_rows),
            "ma200_ready": sum(row.ma200_ready for row in coverage_rows),
            "insufficient": sum(
                row.status == "INSUFFICIENT_HISTORY" for row in coverage_rows
            ),
            "no_history": sum(row.status == "NO_SSI_HISTORY" for row in coverage_rows),
            "provider_errors": sum(row.status == "PROVIDER_ERROR" for row in coverage_rows),
        }
        _emit_outputs(document, (asdict(row) for row in coverage_rows), args)
        return 0

    telemetry = AuditTelemetryCollector()
    client = _client_from_process_environment(
        telemetry, page_size=getattr(args, "page_size", 1000)
    )
    audit_client = SSIAuditClient(client)
    if args.mode == "universe":
        ccc = load_universe_file(args.universe_file)
        provider = audit_client.fetch_securities_universe()
        result = compare_universes(ccc, provider.records)
        document = base_audit_document(
            environment_label=args.environment_label,
            base_url=base_url,
            universe_count=len(ccc),
            exchanges=SUPPORTED_EXCHANGES,
        )
        document["provider"].update(telemetry.summary(path=SECURITIES_PATH))
        document["provider"]["endpoint"] = SECURITIES_PATH
        document["universe"] = {
            "total_ccc": result.total_ccc,
            "matched": result.matched,
            "missing": result.missing,
            "exchange_mismatch": result.exchange_mismatch,
            "ssi_only": result.ssi_only,
        }
        _emit_outputs(document, (asdict(row) for row in result.details), args)
        return 0
    if args.mode == "bulk":
        result = audit_client.fetch_bulk_daily_ohlc(args.date)
        document = base_audit_document(
            environment_label=args.environment_label,
            base_url=base_url,
            from_date=args.date,
            to_date=args.date,
        )
        document["provider"].update(telemetry.summary(path=DAILY_OHLC_PATH))
        document["provider"]["endpoint"] = DAILY_OHLC_PATH
        document["bulk_probe"] = {
            "status": classify_bulk_probe(result),
            "totalrecord": result.totalrecord,
            "pages": result.pages,
            "distinct_symbols": result.distinct_symbols,
            "completeness_notes": (
                f"duplicates={result.duplicates}; malformed={result.malformed_rows}"
            ),
        }
        _emit_outputs(
            document,
            (
                {
                    "symbol": _first(row, "symbol", "Symbol"),
                    "market": _first(row, "market", "Market"),
                    "tradingdate": _first(
                        row, "tradingdate", "TradingDate", "tradingDate"
                    ),
                }
                for row in result.rows
            ),
            args,
        )
        return 0

    specifications: list[SecurityRecord] = []
    for raw in args.symbol:
        try:
            symbol, exchange = raw.split(":", 1)
        except ValueError as exc:
            raise SystemExit("--symbol must use SYMBOL:EXCHANGE") from exc
        specifications.append(
            SecurityRecord(_canonical_symbol(symbol), normalize_exchange(exchange))
        )
    if not 1 <= len(specifications) <= 5:
        raise SystemExit("probe requires between one and five symbols")
    details: list[dict[str, Any]] = []
    for specification in specifications:
        before = len(telemetry.events)
        try:
            rows = client.fetch_daily_ohlc(
                specification.symbol, args.from_date, args.to_date
            )
            normalized: list[DailyBar] = []
            rejected = 0
            returned_exchanges: set[str] = set()
            for row in rows:
                exchange = _raw_exchange(row)
                if exchange:
                    returned_exchanges.add(exchange)
                bar = normalize_daily_ohlc_record(
                    row,
                    exchange_hint=specification.exchange,
                    as_of_date=args.as_of_date,
                )
                if bar is None:
                    rejected += 1
                else:
                    normalized.append(bar)
            mismatched_exchange = any(
                exchange != specification.exchange for exchange in returned_exchanges
            )
            if mismatched_exchange or rejected:
                status = "FAIL"
            elif normalized:
                status = "PASS"
            else:
                status = "WARN"
            error = None
        except Exception as exc:
            rows, normalized, rejected, returned_exchanges = [], [], 0, set()
            status, error = "FAIL", type(exc).__name__
        events = telemetry.events[before:]
        dates = sorted(bar.trading_date for bar in normalized)
        details.append({
            "requested_symbol": specification.symbol,
            "expected_exchange": specification.exchange,
            "ssi_returned_exchange": sorted(returned_exchanges),
            "requested_from": args.from_date,
            "requested_to": args.to_date,
            "returned_rows": len(rows),
            "earliest_date": dates[0] if dates else None,
            "latest_date": dates[-1] if dates else None,
            "ohlc_valid": rejected == 0,
            "volume_value_valid": rejected == 0,
            "response_shape_observed": sorted({
                event.response_keys for event in events
                if event.path == DAILY_OHLC_PATH and event.response_keys is not None
            }),
            "request_count": sum(event.path == DAILY_OHLC_PATH for event in events),
            "retry_count": sum(
                event.path == DAILY_OHLC_PATH and event.is_retry for event in events
            ),
            "http_429_count": sum(
                event.path == DAILY_OHLC_PATH and event.http_status == 429
                for event in events
            ),
            "rate_limit_observations": [
                {
                    "limit": event.rate_limit_limit,
                    "remaining": event.rate_limit_remaining,
                    "reset": event.rate_limit_reset,
                    "retry_after": event.retry_after,
                }
                for event in events
                if event.path == DAILY_OHLC_PATH
                and any(
                    value is not None
                    for value in (
                        event.rate_limit_limit,
                        event.rate_limit_remaining,
                        event.rate_limit_reset,
                        event.retry_after,
                    )
                )
            ],
            "status": status,
            "error": error,
        })
    document = base_audit_document(
        environment_label=args.environment_label,
        base_url=base_url,
        from_date=args.from_date,
        to_date=args.to_date,
        universe_count=len(specifications),
        exchanges=sorted({item.exchange for item in specifications}),
    )
    document["provider"].update(telemetry.summary(path=DAILY_OHLC_PATH))
    document["provider"]["endpoint"] = DAILY_OHLC_PATH
    document["history"]["audited_symbols"] = len(specifications)
    document["probe_details"] = details
    _emit_outputs(document, details, args)
    return 0 if all(row["status"] != "FAIL" for row in details) else 2


if __name__ == "__main__":
    raise SystemExit(main())
