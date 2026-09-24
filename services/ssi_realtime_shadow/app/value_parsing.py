"""Dependency-light parsing helpers for optional provider values."""

from __future__ import annotations

import math
from typing import Any


def finite_float(value: Any, *, positive: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def nonnegative_int(value: Any) -> int | None:
    number = finite_float(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)
