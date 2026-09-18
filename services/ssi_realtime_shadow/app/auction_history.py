from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from .market_session import normalize_exchange
from .market_storage_schema import canonical_timestamp
from .volume_baseline import load_candidate_market_sessions


CLOSE_AUCTION = "CLOSE_AUCTION"
OPEN_AUCTION = "OPEN_AUCTION"
PROVEN = "PROVEN"
INFERRED_BOUNDARY = "INFERRED_BOUNDARY"
MIXED = "MIXED"
UNAVAILABLE = "UNAVAILABLE"
SSI_REST = "SSI_REST"
SSI_STREAM = "SSI_STREAM"
CROSS_PROVIDER_PROOF = "CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1"
CONFIRMED_CLASSIFICATION = "CONFIRMED_INFERRED_BOUNDARY"


class AuctionHistoryConflict(RuntimeError):
    """Raised when one canonical identity has conflicting immutable evidence."""


@dataclass(frozen=True, slots=True)
class AuctionHistoryRow:
    symbol: str
    trading_date: str
    exchange: str
    auction_type: str
    auction_price: float
    pre_auction_price: float | None
    auction_volume: int
    provider_session: str | None
    source: str
    quality: str
    proof_code: str | None
    finalized: bool

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not 2 <= len(symbol) <= 12:
            raise ValueError("symbol must contain 2..12 characters")
        object.__setattr__(self, "symbol", symbol)
        date.fromisoformat(self.trading_date)
        object.__setattr__(self, "exchange", normalize_exchange(self.exchange))
        auction_type = str(self.auction_type or "").strip().upper()
        if auction_type != CLOSE_AUCTION:
            raise ValueError("BETA-04C supports CLOSE_AUCTION history only")
        object.__setattr__(self, "auction_type", auction_type)
        if self.auction_price <= 0:
            raise ValueError("auction_price must be positive")
        if self.pre_auction_price is not None and self.pre_auction_price <= 0:
            raise ValueError("pre_auction_price must be positive or null")
        if isinstance(self.auction_volume, bool) or self.auction_volume < 0:
            raise ValueError("auction_volume must be nonnegative")
        if not self.finalized:
            raise ValueError("canonical auction history must be finalized")
        source = str(self.source or "").strip().upper()
        quality = str(self.quality or "").strip().upper()
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "quality", quality)
        if quality == INFERRED_BOUNDARY:
            if source != SSI_REST or self.proof_code != CROSS_PROVIDER_PROOF:
                raise ValueError("inferred history requires approved SSI REST proof")
        elif quality == PROVEN:
            if source != SSI_STREAM:
                raise ValueError("PROVEN history requires SSI_STREAM")
        else:
            raise ValueError("unsupported history quality")
        provider_session = (
            str(self.provider_session).strip().upper()
            if self.provider_session is not None
            else None
        )
        object.__setattr__(self, "provider_session", provider_session or None)


@dataclass(slots=True)
class BootstrapReport:
    eligible_rows: int = 0
    would_insert: int = 0
    inserted: int = 0
    already_identical: int = 0
    conflicts: int = 0
    protected_proven: int = 0
    rejected: int = 0
    superseded: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Exact10Result:
    symbol: str
    as_of_date: str
    candidate_dates: tuple[str, ...]
    sessions_used: int
    proven_sessions: int
    inferred_sessions: int
    missing_sessions: tuple[str, ...]
    avg_closing_auction_volume: float | None
    baseline_usable: bool
    baseline_quality: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["candidate_dates"] = list(self.candidate_dates)
        result["missing_sessions"] = list(self.missing_sessions)
        return result


_CANONICAL_FIELDS = (
    "symbol",
    "trading_date",
    "exchange",
    "auction_type",
    "auction_price",
    "pre_auction_price",
    "auction_volume",
    "provider_session",
    "source",
    "quality",
    "proof_code",
    "finalized",
)


def _existing_row(
    connection: sqlite3.Connection, row: AuctionHistoryRow
) -> sqlite3.Row | None:
    connection.row_factory = sqlite3.Row
    return connection.execute(
        """
        SELECT * FROM auction_session_history
        WHERE symbol=? AND trading_date=? AND auction_type=?
        """,
        (row.symbol, row.trading_date, row.auction_type),
    ).fetchone()


def _same_canonical(existing: Mapping[str, Any], incoming: AuctionHistoryRow) -> bool:
    expected = asdict(incoming)
    expected["finalized"] = 1 if incoming.finalized else 0
    return all(existing[name] == expected[name] for name in _CANONICAL_FIELDS)


def store_auction_history_row(
    connection: sqlite3.Connection,
    row: AuctionHistoryRow,
    *,
    recorded_at: str,
    dry_run: bool = False,
) -> str:
    timestamp = canonical_timestamp(recorded_at)
    existing = _existing_row(connection, row)
    if existing is None:
        if dry_run:
            return "WOULD_INSERT"
        connection.execute(
            """
            INSERT INTO auction_session_history (
                symbol, trading_date, exchange, auction_type,
                auction_price, pre_auction_price, auction_volume,
                provider_session, source, quality, proof_code, finalized,
                previous_source, previous_quality, previous_proof_code,
                superseded_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                row.symbol,
                row.trading_date,
                row.exchange,
                row.auction_type,
                row.auction_price,
                row.pre_auction_price,
                row.auction_volume,
                row.provider_session,
                row.source,
                row.quality,
                row.proof_code,
                1 if row.finalized else 0,
                timestamp,
                timestamp,
            ),
        )
        return "INSERTED"

    if _same_canonical(existing, row):
        return "ALREADY_IDENTICAL"
    if existing["quality"] == PROVEN and row.quality == INFERRED_BOUNDARY:
        return "PROTECTED_PROVEN"
    if existing["quality"] == INFERRED_BOUNDARY and row.quality == PROVEN:
        if dry_run:
            return "WOULD_SUPERSEDE"
        connection.execute(
            """
            UPDATE auction_session_history
            SET exchange=?, auction_price=?, pre_auction_price=?, auction_volume=?,
                provider_session=?, source=?, quality=?, proof_code=?, finalized=?,
                previous_source=source, previous_quality=quality,
                previous_proof_code=proof_code, superseded_at=?, updated_at=?
            WHERE symbol=? AND trading_date=? AND auction_type=?
            """,
            (
                row.exchange,
                row.auction_price,
                row.pre_auction_price,
                row.auction_volume,
                row.provider_session,
                row.source,
                row.quality,
                row.proof_code,
                1 if row.finalized else 0,
                timestamp,
                timestamp,
                row.symbol,
                row.trading_date,
                row.auction_type,
            ),
        )
        return "SUPERSEDED"
    raise AuctionHistoryConflict(
        f"Conflicting {existing['quality']} auction history for "
        f"{row.symbol}/{row.trading_date}/{row.auction_type}"
    )


def _parse_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def approved_inferred_row(record: Mapping[str, Any]) -> AuctionHistoryRow | None:
    if (
        record.get("classification") != CONFIRMED_CLASSIFICATION
        or record.get("quality") != INFERRED_BOUNDARY
        or record.get("proof") != CROSS_PROVIDER_PROOF
        or record.get("source") != SSI_REST
    ):
        return None
    if record.get("auction_type") not in (None, "", CLOSE_AUCTION):
        return None
    if _parse_json_list(record.get("failure_reasons")):
        return None
    try:
        return AuctionHistoryRow(
            symbol=str(record["symbol"]),
            trading_date=str(record["trading_date"]),
            exchange="HOSE",  # Locked BETA-04B audit universe is entirely HOSE.
            auction_type=CLOSE_AUCTION,
            auction_price=float(record["ssi_boundary_price"]),
            pre_auction_price=float(record["ssi_last_continuous_price"]),
            auction_volume=int(record["ssi_boundary_volume"]),
            provider_session=None,
            source=str(record["source"]),
            quality=str(record["quality"]),
            proof_code=str(record["proof"]),
            finalized=True,
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_approved_proof_rows(path: Path) -> tuple[list[AuctionHistoryRow], int]:
    eligible: list[AuctionHistoryRow] = []
    rejected = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            row = approved_inferred_row(record)
            if row is None:
                rejected += 1
            else:
                eligible.append(row)
    return eligible, rejected


def bootstrap_auction_history(
    connection: sqlite3.Connection,
    rows: Iterable[AuctionHistoryRow],
    *,
    recorded_at: str,
    dry_run: bool = True,
    rejected: int = 0,
) -> BootstrapReport:
    report = BootstrapReport(rejected=rejected)
    for row in rows:
        report.eligible_rows += 1
        try:
            outcome = store_auction_history_row(
                connection, row, recorded_at=recorded_at, dry_run=dry_run
            )
        except AuctionHistoryConflict as exc:
            report.conflicts += 1
            report.details.append(
                {"symbol": row.symbol, "trading_date": row.trading_date, "error": str(exc)}
            )
            continue
        if outcome == "WOULD_INSERT":
            report.would_insert += 1
        elif outcome == "INSERTED":
            report.inserted += 1
        elif outcome == "ALREADY_IDENTICAL":
            report.already_identical += 1
        elif outcome == "PROTECTED_PROVEN":
            report.protected_proven += 1
        elif outcome == "SUPERSEDED":
            report.superseded += 1
        elif outcome == "WOULD_SUPERSEDE":
            report.details.append(
                {"symbol": row.symbol, "trading_date": row.trading_date, "outcome": outcome}
            )
    return report


def read_atc_exact10(
    auction_connection: sqlite3.Connection,
    history_connection: sqlite3.Connection,
    daily_connection: sqlite3.Connection,
    *,
    symbol: str,
    as_of_date: str,
) -> Exact10Result:
    canonical_symbol = str(symbol or "").strip().upper()
    candidate_dates = tuple(
        load_candidate_market_sessions(
            history_connection,
            daily_connection,
            as_of_date=as_of_date,
            lookback=10,
        )
    )
    if not candidate_dates:
        rows: dict[str, sqlite3.Row] = {}
    else:
        auction_connection.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in candidate_dates)
        rows = {
            str(row["trading_date"]): row
            for row in auction_connection.execute(
                f"""
                SELECT trading_date, auction_volume, quality
                FROM auction_session_history
                WHERE symbol=? AND auction_type=?
                  AND finalized=1 AND trading_date IN ({placeholders})
                """,
                (canonical_symbol, CLOSE_AUCTION, *candidate_dates),
            )
        }
    missing = tuple(item for item in candidate_dates if item not in rows)
    proven = sum(row["quality"] == PROVEN for row in rows.values())
    inferred = sum(row["quality"] == INFERRED_BOUNDARY for row in rows.values())
    sessions_used = len(rows)
    usable = len(candidate_dates) == 10 and sessions_used == 10 and not missing
    average = (
        sum(int(row["auction_volume"]) for row in rows.values()) / 10
        if usable
        else None
    )
    if not usable:
        quality = UNAVAILABLE
    elif proven == 10:
        quality = PROVEN
    elif inferred == 10:
        quality = INFERRED_BOUNDARY
    else:
        quality = MIXED
    return Exact10Result(
        symbol=canonical_symbol,
        as_of_date=as_of_date,
        candidate_dates=candidate_dates,
        sessions_used=sessions_used,
        proven_sessions=proven,
        inferred_sessions=inferred,
        missing_sessions=missing,
        avg_closing_auction_volume=average,
        baseline_usable=usable,
        baseline_quality=quality,
    )
