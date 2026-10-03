from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import NewsItem

_TOKEN_RE = re.compile(r"[A-Z0-9]+")
_SPACE_RE = re.compile(r"\s+")

# Bare ticker matching is intentionally conservative. These feeds are about
# listed-company events, but a generic business/banking story may contain words
# such as CEO/API/NET that are also valid Vietnamese tickers.
_MARKET_TICKER_CATEGORIES = frozenset(
    {"MARKET", "STOCKS", "INSIDER_TRADING", "LISTING", "DIVIDEND", "CAPITAL_MA"}
)
_MARKET_CONTEXT_PHRASES = (
    "CO PHIEU",
    "CHOT QUYEN",
    "CO TUC",
    "NIEM YET",
    "GIAO DICH NOI BO",
    "MUA THEM",
    "BAN RA",
    "NANG SO HUU",
    "GIAM SO HUU",
)

_LEGAL_PREFIXES = (
    "CONG TY CO PHAN ",
    "CTCP ",
    "TONG CONG TY CO PHAN ",
    "TONG CONG TY ",
    "TAP DOAN ",
    "NGAN HANG THUONG MAI CO PHAN ",
    "NGAN HANG TMCP ",
    "CONG TY TNHH ",
    "CONG TY ",
)
_LEGAL_SUFFIXES = (" CTCP", " JSC", " JOINT STOCK COMPANY", " CORPORATION")
_GENERIC_ALIASES = frozenset(
    {
        "DAU TU",
        "XAY DUNG",
        "CHUNG KHOAN",
        "BAT DONG SAN",
        "THUONG MAI",
        "DICH VU",
        "CONG NGHE",
        "TAI CHINH",
        "NGAN HANG",
    }
)


@dataclass(frozen=True, slots=True)
class StockIdentity:
    symbol: str
    exchange: str
    organ_name: str


@dataclass(frozen=True, slots=True)
class SymbolMatch:
    symbol: str
    match_type: str
    matched_text: str


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _strip_legal_name(name: str) -> str:
    current = normalize_text(name)
    changed = True
    while changed and current:
        changed = False
        for prefix in _LEGAL_PREFIXES:
            if current.startswith(prefix):
                current = current[len(prefix) :].strip()
                changed = True
                break
    changed = True
    while changed and current:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if current.endswith(suffix):
                current = current[: -len(suffix)].strip()
                changed = True
                break
    return current


def _strong_alias(value: str) -> bool:
    if not value or value in _GENERIC_ALIASES:
        return False
    tokens = value.split()
    if len(tokens) >= 2:
        return len(value.replace(" ", "")) >= 6
    return len(value) >= 5


def _aliases(identity: StockIdentity) -> set[str]:
    full = normalize_text(identity.organ_name)
    short = _strip_legal_name(identity.organ_name)
    aliases: set[str] = set()
    if _strong_alias(full):
        aliases.add(full)
    if _strong_alias(short):
        aliases.add(short)
    return aliases


def load_stock_identities(path: Path | str) -> list[StockIdentity]:
    source = Path(path)
    rows: list[StockIdentity] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = normalize_text(row.get("symbol"))
            exchange = normalize_text(row.get("exchange"))
            organ_name = str(row.get("organ_name") or "").strip()
            if not symbol or not re.fullmatch(r"[A-Z0-9]{2,12}", symbol):
                continue
            if not organ_name:
                continue
            rows.append(StockIdentity(symbol=symbol, exchange=exchange, organ_name=organ_name))
    return rows


class SymbolMapper:
    def __init__(self, identities: Iterable[StockIdentity]) -> None:
        self.identities = tuple(identities)
        self.symbols = {identity.symbol for identity in self.identities}
        alias_symbols: dict[str, set[str]] = {}
        for identity in self.identities:
            for alias in _aliases(identity):
                alias_symbols.setdefault(alias, set()).add(identity.symbol)
        # Ambiguous aliases are deliberately discarded rather than guessed.
        self.alias_to_symbol = {
            alias: next(iter(symbols))
            for alias, symbols in alias_symbols.items()
            if len(symbols) == 1
        }
        # Longest first prevents a short alias from obscuring a stronger one.
        self.aliases = tuple(sorted(self.alias_to_symbol, key=lambda value: (-len(value), value)))

    @classmethod
    def from_csv(cls, path: Path | str) -> "SymbolMapper":
        return cls(load_stock_identities(path))

    def match(self, item: NewsItem) -> list[SymbolMatch]:
        text = normalize_text(f"{item.title} {item.summary}")
        if not text:
            return []
        padded = f" {text} "
        matches: dict[str, SymbolMatch] = {}

        for alias in self.aliases:
            if f" {alias} " not in padded:
                continue
            symbol = self.alias_to_symbol[alias]
            matches[symbol] = SymbolMatch(symbol=symbol, match_type="NAME", matched_text=alias)

        allow_bare_tickers = (
            item.category in _MARKET_TICKER_CATEGORIES
            and any(phrase in text for phrase in _MARKET_CONTEXT_PHRASES)
        )
        if allow_bare_tickers:
            for token in _TOKEN_RE.findall(text):
                if token not in self.symbols or token in matches:
                    continue
                matches[token] = SymbolMatch(symbol=token, match_type="TICKER", matched_text=token)

        return sorted(matches.values(), key=lambda match: match.symbol)
