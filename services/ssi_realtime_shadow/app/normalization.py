from __future__ import annotations

from datetime import date, datetime
from typing import Any


TRADING_DATE_FORMATS = (
    "%d%m%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def parse_trading_date(value: Any, *, fallback: date | None = None) -> str | None:
    """Normalize supported SSI dates without guessing malformed values."""
    if value is None or not str(value).strip():
        return fallback.isoformat() if fallback is not None else None
    text = str(value).strip()
    for fmt in TRADING_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None
