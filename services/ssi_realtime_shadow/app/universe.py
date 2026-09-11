from __future__ import annotations

import logging
import re
from pathlib import Path

import requests

from .settings import Settings

LOG = logging.getLogger(__name__)
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}$")


def _normalize(symbols: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if SYMBOL_RE.match(symbol):
            out.add(symbol)
    return out


def _load_file(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: list[str] = []
    for line in lines:
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        values.extend(part.strip() for part in value.replace(",", " ").split())
    return _normalize(values)


def _load_supabase(settings: Settings) -> set[str]:
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "No usable UNIVERSE_FILE and SUPABASE_URL/SUPABASE_KEY are not configured"
        )
    url = settings.supabase_url.rstrip("/") + "/rest/v1/stock_snapshot"
    headers = {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Accept": "application/json",
    }
    params = {"select": "symbol", "order": "symbol.asc", "limit": "2000"}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    rows = response.json()
    return _normalize([row.get("symbol", "") for row in rows if isinstance(row, dict)])


def load_universe(settings: Settings) -> set[str]:
    symbols: set[str]
    if settings.universe_file and settings.universe_file.exists():
        symbols = _load_file(settings.universe_file)
        source = str(settings.universe_file)
    else:
        symbols = _load_supabase(settings)
        source = "Supabase stock_snapshot"

    if len(symbols) < settings.min_universe_size:
        raise RuntimeError(
            f"Universe has only {len(symbols)} symbols from {source}; "
            f"minimum is {settings.min_universe_size}. Collector stopped for safety."
        )
    LOG.info("Loaded %s symbols from %s", len(symbols), source)
    return symbols
