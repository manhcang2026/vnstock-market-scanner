from __future__ import annotations

import logging
import math
import re
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable

import requests

from .market_session import normalize_exchange
from .normalization import parse_trading_date


LOG = logging.getLogger(__name__)
INTRADAY_PATH = "api/v2/Market/IntradayOhlc"
DAILY_OHLC_PATH = "api/v2/Market/DailyOhlc"
TOKEN_PATH = "api/v2/Market/AccessToken"
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
NON_EQUITY_MARKETS = {"DER"}
MAX_PAGE_INDEX = 10
DAILY_MAX_RANGE_DAYS = 30
PROVIDER_TIME_RE = re.compile(r"^(?:\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?|\d{6})$")


class SSIHistoricalError(RuntimeError):
    pass


class SSIHTTPError(SSIHistoricalError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class HistoricalBar:
    symbol: str
    exchange: str
    trading_date: str
    minute: str
    provider_time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    value: float | None


def _first(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return None


def _parse_provider_time(value: Any) -> tuple[str, str] | None:
    if value is None:
        return None
    provider_time = str(value).strip()
    if not PROVIDER_TIME_RE.fullmatch(provider_time):
        return None
    for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H%M%S"):
        try:
            parsed = datetime.strptime(provider_time, fmt)
            return parsed.strftime("%H:%M"), provider_time
        except ValueError:
            pass
    return None


def normalize_historical_record(
    record: dict[str, Any], exchange_hint: str | None = None
) -> HistoricalBar | None:
    """Normalize one official SSI REST interval bar without inventing timestamps."""
    symbol = str(_first(record, "Symbol", "symbol") or "").strip().upper()
    if not symbol:
        LOG.warning("Rejected historical row with missing Symbol")
        return None

    raw_market = next(
        (
            str(record[name]).strip().upper()
            for name in ("Market", "market", "Exchange", "exchange")
            if record.get(name) is not None and str(record[name]).strip()
        ),
        "",
    )
    if raw_market in NON_EQUITY_MARKETS:
        return None

    hint: str | None = None
    if exchange_hint is not None:
        try:
            hint = normalize_exchange(exchange_hint)
        except ValueError:
            LOG.warning(
                "Rejected historical row for %s with invalid exchange hint=%r",
                symbol,
                exchange_hint,
            )
            return None

    if raw_market:
        try:
            exchange = normalize_exchange(raw_market)
        except ValueError:
            LOG.warning(
                "Rejected historical row for %s with market=%r", symbol, raw_market
            )
            return None
        if hint is not None and exchange != hint:
            LOG.warning(
                "Rejected historical row for %s: provider exchange %s conflicts "
                "with trusted exchange %s",
                symbol,
                exchange,
                hint,
            )
            return None
    elif hint is not None:
        exchange = hint
    else:
        LOG.warning("Rejected historical row for %s with missing exchange", symbol)
        return None

    trading_date = parse_trading_date(
        _first(record, "TradingDate", "tradingDate", "tradingdate", "trading_date")
    )
    parsed_time = _parse_provider_time(_first(record, "Time", "time"))
    if trading_date is None or parsed_time is None:
        LOG.warning("Rejected historical row for %s with invalid date/time", symbol)
        return None

    try:
        open_price = float(_first(record, "Open", "open"))
        high = float(_first(record, "High", "high"))
        low = float(_first(record, "Low", "low"))
        close = float(_first(record, "Close", "close"))
        raw_volume = float(_first(record, "Volume", "volume"))
        raw_value = _first(record, "Value", "value")
        traded_value = float(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        LOG.warning("Rejected historical row for %s with invalid OHLCV", symbol)
        return None
    numbers = (open_price, high, low, close, raw_volume)
    if not all(math.isfinite(number) for number in numbers):
        LOG.warning("Rejected historical row for %s with non-finite OHLCV", symbol)
        return None
    if traded_value is not None and not math.isfinite(traded_value):
        LOG.warning("Rejected historical row for %s with non-finite Value", symbol)
        return None
    if raw_volume < 0 or not raw_volume.is_integer():
        LOG.warning("Rejected historical row for %s with invalid Volume", symbol)
        return None
    volume = int(raw_volume)

    minute, provider_time = parsed_time
    return HistoricalBar(
        symbol=symbol,
        exchange=exchange,
        trading_date=trading_date,
        minute=minute,
        provider_time=provider_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        value=traded_value,
    )


def _coerce_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_trading_date(value)
    if parsed is None:
        raise ValueError(f"Invalid trading date: {value!r}")
    return date.fromisoformat(parsed)


def _provider_status_is_success(status: Any) -> bool:
    if isinstance(status, str):
        return status.strip().casefold() in {"200", "200.0", "success"}
    return status in {200, 200.0}


class SSIHistoricalClient:
    """Small, retry-aware client following the inspected official SDK flow."""

    def __init__(
        self,
        *,
        base_url: str,
        consumer_id: str,
        consumer_secret: str,
        auth_type: str = "Bearer",
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time_module.sleep,
        request_timeout: float = 30,
        max_attempts: int = 4,
        page_size: int = 1000,
        max_pages_per_range: int = MAX_PAGE_INDEX,
        max_retry_delay: float = 60,
    ) -> None:
        if not consumer_id or not consumer_secret:
            raise ValueError("SSI credentials are required")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if max_attempts < 1 or max_pages_per_range < 1:
            raise ValueError("retry and pagination limits must be positive")
        if max_pages_per_range > MAX_PAGE_INDEX:
            raise ValueError(
                f"max_pages_per_range must not exceed SSI pageIndex limit "
                f"{MAX_PAGE_INDEX}"
            )
        self.base_url = base_url.rstrip("/") + "/"
        self.consumer_id = consumer_id
        self.consumer_secret = consumer_secret
        self.auth_type = auth_type or "Bearer"
        self.session = session or requests.Session()
        self.sleep = sleep
        self.request_timeout = request_timeout
        self.max_attempts = max_attempts
        self.page_size = page_size
        self.max_pages_per_range = max_pages_per_range
        self.max_retry_delay = max_retry_delay
        self._access_token: str | None = None

    def _url(self, path: str) -> str:
        return self.base_url + path.lstrip("/")

    def _retry_delay(self, response: Any | None, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max(
                        0.0,
                        (retry_at - datetime.now(timezone.utc)).total_seconds(),
                    )
                except (TypeError, ValueError, OverflowError):
                    delay = None
            if delay is not None:
                return min(max(0.0, delay), self.max_retry_delay)

        reset = headers.get("X-RateLimit-Reset") or headers.get("RateLimit-Reset")
        if reset:
            try:
                delay = max(0.0, float(reset) - datetime.now(timezone.utc).timestamp())
                return min(delay, self.max_retry_delay)
            except ValueError:
                pass
        return min(float(2 ** (attempt - 1)), self.max_retry_delay)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> dict[str, Any]:
        refreshed_after_unauthorized = False
        for attempt in range(1, self.max_attempts + 1):
            headers = {"Accept": "application/json"}
            if authenticated:
                headers["Authorization"] = f"{self.auth_type} {self._get_token()}"
            response = None
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self.request_timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= self.max_attempts:
                    raise SSIHistoricalError(
                        f"SSI request failed after {attempt} attempts: {type(exc).__name__}"
                    ) from exc
                self.sleep(self._retry_delay(None, attempt))
                continue

            if authenticated and response.status_code == 401 and not refreshed_after_unauthorized:
                self._access_token = None
                refreshed_after_unauthorized = True
                if attempt < self.max_attempts:
                    continue
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_attempts:
                self.sleep(self._retry_delay(response, attempt))
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise SSIHTTPError(
                    response.status_code,
                    f"SSI HTTP {response.status_code} for {path}",
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise SSIHistoricalError(f"SSI returned invalid JSON for {path}") from exc
            if not isinstance(payload, dict):
                raise SSIHistoricalError(f"SSI returned an invalid payload for {path}")
            provider_status = payload.get("status")
            if provider_status is not None and not _provider_status_is_success(
                provider_status
            ):
                raise SSIHistoricalError(
                    f"SSI provider status {provider_status!r} for {path}"
                )
            return payload
        raise SSIHistoricalError(f"SSI request attempts exhausted for {path}")

    def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        payload = self._request_json(
            "POST",
            TOKEN_PATH,
            json={
                "consumerID": self.consumer_id,
                "consumerSecret": self.consumer_secret,
            },
        )
        data = payload.get("data")
        token = data.get("accessToken") if isinstance(data, dict) else None
        if not token:
            raise SSIHistoricalError("SSI access-token response did not contain a token")
        self._access_token = str(token)
        return self._access_token

    @staticmethod
    def _rows_and_total(
        payload: dict[str, Any], endpoint: str = "IntradayOhlc"
    ) -> tuple[list[dict[str, Any]], int | None]:
        data = _first(payload, "dataList", "data")
        total = _first(payload, "totalrecord", "totalRecord")
        if isinstance(data, dict):
            nested_total = _first(data, "totalrecord", "totalRecord")
            if nested_total is not None:
                total = nested_total
            data = _first(data, "dataList", "items", "data", "rows")
        if data is None:
            data = []
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise SSIHistoricalError(
                f"SSI {endpoint} response data is not a row list"
            )
        try:
            parsed_total = int(total) if total is not None else None
        except (TypeError, ValueError) as exc:
            raise SSIHistoricalError(
                f"SSI {endpoint} totalRecord is invalid"
            ) from exc
        return data, parsed_total

    def _fetch_page(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        page_index: int,
        resolution: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        if not 1 <= page_index <= MAX_PAGE_INDEX:
            raise ValueError(
                f"page_index must be between 1 and {MAX_PAGE_INDEX}"
            )
        payload = self._request_json(
            "GET",
            INTRADAY_PATH,
            params={
                "symbol": symbol,
                "fromDate": from_date.strftime("%d/%m/%Y"),
                "toDate": to_date.strftime("%d/%m/%Y"),
                "pageIndex": page_index,
                "pageSize": self.page_size,
                "ascending": True,
                "resolution": resolution,
            },
            authenticated=True,
        )
        return self._rows_and_total(payload)

    def _fetch_range(
        self, symbol: str, from_date: date, to_date: date, resolution: int
    ) -> list[dict[str, Any]]:
        first_rows, total = self._fetch_page(
            symbol, from_date, to_date, 1, resolution
        )
        capacity = self.page_size * self.max_pages_per_range
        if total is not None and total > capacity:
            if from_date >= to_date:
                raise SSIHistoricalError(
                    f"{symbol} has {total} rows on {from_date.isoformat()}, "
                    f"above the safe pagination capacity {capacity}"
                )
            midpoint = from_date + timedelta(days=(to_date - from_date).days // 2)
            return self._fetch_range(
                symbol, from_date, midpoint, resolution
            ) + self._fetch_range(
                symbol, midpoint + timedelta(days=1), to_date, resolution
            )

        rows = list(first_rows)
        if total is not None:
            pages = max(1, math.ceil(total / self.page_size))
        else:
            pages = 1 if len(first_rows) < self.page_size else self.max_pages_per_range
        for page_index in range(2, pages + 1):
            page_rows, page_total = self._fetch_page(
                symbol, from_date, to_date, page_index, resolution
            )
            if total is not None and page_total is not None and page_total != total:
                raise SSIHistoricalError(
                    f"SSI totalRecord changed while paging {symbol}"
                )
            if not page_rows:
                if total is not None and len(rows) < total:
                    raise SSIHistoricalError(
                        f"SSI pagination ended early for {symbol}: {len(rows)}/{total}"
                    )
                break
            rows.extend(page_rows)
            if total is None and len(page_rows) < self.page_size:
                break
        if total is not None and len(rows) < total:
            raise SSIHistoricalError(
                f"SSI pagination incomplete for {symbol}: {len(rows)}/{total}"
            )
        if total is None and len(rows) >= capacity:
            raise SSIHistoricalError(
                f"SSI omitted totalRecord and {symbol} reached pagination capacity"
            )
        return rows

    def fetch_intraday_ohlc(
        self,
        symbol: str,
        from_date: date | str,
        to_date: date | str,
        resolution: int = 1,
    ) -> list[dict[str, Any]]:
        canonical_symbol = str(symbol or "").strip().upper()
        if not canonical_symbol:
            raise ValueError("symbol is required")
        if resolution != 1:
            raise ValueError("This bootstrap supports only 1-minute resolution")
        start = _coerce_date(from_date)
        end = _coerce_date(to_date)
        if start > end:
            raise ValueError("from_date must not be after to_date")

        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in self._fetch_range(canonical_symbol, start, end, resolution):
            key = (
                str(_first(row, "Symbol", "symbol") or canonical_symbol).upper(),
                str(
                    _first(
                        row,
                        "TradingDate",
                        "tradingDate",
                        "tradingdate",
                        "trading_date",
                    )
                    or ""
                ),
                str(_first(row, "Time", "time") or ""),
            )
            unique.setdefault(key, row)
        return list(unique.values())

    def _fetch_daily_page(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        page_index: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        if not 1 <= page_index <= MAX_PAGE_INDEX:
            raise ValueError(f"page_index must be between 1 and {MAX_PAGE_INDEX}")
        payload = self._request_json(
            "GET",
            DAILY_OHLC_PATH,
            params={
                "symbol": symbol,
                "fromDate": from_date.strftime("%d/%m/%Y"),
                "toDate": to_date.strftime("%d/%m/%Y"),
                "pageIndex": page_index,
                "pageSize": self.page_size,
                "ascending": True,
            },
            authenticated=True,
        )
        return self._rows_and_total(payload, "DailyOhlc")

    def _fetch_daily_range(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        first_rows, total = self._fetch_daily_page(symbol, from_date, to_date, 1)
        capacity = self.page_size * self.max_pages_per_range
        if total is not None and total > capacity:
            if from_date >= to_date:
                raise SSIHistoricalError(
                    f"{symbol} has {total} daily rows on {from_date.isoformat()}, "
                    f"above the safe pagination capacity {capacity}"
                )
            midpoint = from_date + timedelta(days=(to_date - from_date).days // 2)
            return self._fetch_daily_range(
                symbol, from_date, midpoint
            ) + self._fetch_daily_range(symbol, midpoint + timedelta(days=1), to_date)

        rows = list(first_rows)
        if total is not None:
            pages = max(1, math.ceil(total / self.page_size))
        else:
            pages = 1 if len(first_rows) < self.page_size else self.max_pages_per_range
        for page_index in range(2, pages + 1):
            page_rows, page_total = self._fetch_daily_page(
                symbol, from_date, to_date, page_index
            )
            if page_total != total:
                raise SSIHistoricalError(
                    f"SSI totalRecord changed while paging daily history for {symbol}"
                )
            if not page_rows:
                if total is not None and len(rows) < total:
                    raise SSIHistoricalError(
                        f"SSI daily pagination ended early for {symbol}: "
                        f"{len(rows)}/{total}"
                    )
                break
            rows.extend(page_rows)
            if total is None and len(page_rows) < self.page_size:
                break
        if total is not None and len(rows) < total:
            raise SSIHistoricalError(
                f"SSI daily pagination incomplete for {symbol}: {len(rows)}/{total}"
            )
        if total is not None and len(rows) > total:
            raise SSIHistoricalError(
                f"SSI daily pagination exceeded totalRecord for {symbol}: "
                f"{len(rows)}/{total}"
            )
        if total is None and len(rows) >= capacity:
            raise SSIHistoricalError(
                f"SSI DailyOhlc omitted totalRecord and {symbol} reached "
                "pagination capacity"
            )
        return rows

    def fetch_daily_ohlc(
        self,
        symbol: str,
        from_date: date | str,
        to_date: date | str,
    ) -> list[dict[str, Any]]:
        """Fetch official SSI daily OHLC rows with bounded ranges and dedupe."""
        canonical_symbol = str(symbol or "").strip().upper()
        if not canonical_symbol:
            raise ValueError("symbol is required")
        start = _coerce_date(from_date)
        end = _coerce_date(to_date)
        if start > end:
            raise ValueError("from_date must not be after to_date")

        rows: list[dict[str, Any]] = []
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(
                chunk_start + timedelta(days=DAILY_MAX_RANGE_DAYS - 1), end
            )
            rows.extend(
                self._fetch_daily_range(canonical_symbol, chunk_start, chunk_end)
            )
            chunk_start = chunk_end + timedelta(days=1)

        unique: dict[tuple[str, str], dict[str, Any]] = {}
        invalid_rows: list[dict[str, Any]] = []
        for row in rows:
            raw_symbol = str(
                _first(row, "Symbol", "symbol") or canonical_symbol
            ).strip().upper()
            raw_date = str(
                _first(
                    row,
                    "TradingDate",
                    "tradingDate",
                    "tradingdate",
                    "trading_date",
                )
                or ""
            ).strip()
            if not raw_symbol or not raw_date:
                invalid_rows.append(row)
                continue
            key = (raw_symbol, raw_date)
            existing = unique.get(key)
            if existing is None:
                unique[key] = row
            elif existing != row:
                raise SSIHistoricalError(
                    "SSI DailyOhlc returned conflicting duplicate rows for "
                    f"{raw_symbol}/{raw_date}"
                )
        return list(unique.values()) + invalid_rows


def normalize_historical_rows(
    rows: Iterable[dict[str, Any]], exchange_hint: str | None = None
) -> list[HistoricalBar]:
    unique: dict[tuple[str, str, str], HistoricalBar] = {}
    for row in rows:
        bar = normalize_historical_record(row, exchange_hint=exchange_hint)
        if bar is not None:
            unique.setdefault((bar.symbol, bar.trading_date, bar.minute), bar)
    return list(unique.values())
