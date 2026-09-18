from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from websockets.exceptions import ConnectionClosed
from websockets.server import serve

from .access_control import SupabaseEntitlementClient

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ALLOWED_RESOLUTIONS = {5, 15, 30, 60, 1440}

QUOTE_COLUMNS = (
    "symbol",
    "trading_date",
    "event_time",
    "last_price",
    "total_volume",
    "ref_price",
    "open",
    "high",
    "low",
    "close",
    "bid_price1",
    "bid_vol1",
    "ask_price1",
    "ask_vol1",
    "change",
    "ratio_change",
    "exchange",
    "trading_session",
    "trading_status",
    "updated_at",
)


def _normalize_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not (2 <= len(symbol) <= 12 and symbol.isalnum()):
        raise ValueError("invalid symbol")
    return symbol


def _normalize_resolution(value: object) -> int:
    resolution = int(value)
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError("unsupported resolution")
    return resolution


def _bucket_start(event_time: str, resolution: int) -> str:
    if resolution == 1440:
        return "00:00"
    hour, minute, *_ = (int(part) for part in event_time.split(":"))
    absolute = hour * 60 + minute
    bucket = absolute - (absolute % resolution)
    bucket_hour, bucket_minute = divmod(bucket, 60)
    return f"{bucket_hour:02d}:{bucket_minute:02d}"


class LiveSQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=2500")
        return conn

    def latest_quote(self, symbol: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT {', '.join(QUOTE_COLUMNS)} "
                "FROM latest_quotes WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if row is None:
                return None
            payload = {column: row[column] for column in QUOTE_COLUMNS}
            payload["source"] = "SSI_STREAM"
            return payload
        finally:
            conn.close()

    def current_candle(
        self,
        *,
        symbol: str,
        trading_date: str,
        event_time: str,
        resolution: int,
    ) -> dict | None:
        bucket_start = _bucket_start(event_time, resolution)
        event_minute = event_time[:5]

        conn = self._connect()
        try:
            if resolution == 1440:
                rows = conn.execute(
                    """
                    SELECT minute, open, high, low, close, volume,
                           data_source, provider_time
                    FROM minute_bars
                    WHERE symbol = ?
                      AND trading_date = ?
                    ORDER BY minute
                    """,
                    (symbol, trading_date),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT minute, open, high, low, close, volume,
                           data_source, provider_time
                    FROM minute_bars
                    WHERE symbol = ?
                      AND trading_date = ?
                      AND minute >= ?
                      AND minute <= ?
                    ORDER BY minute
                    """,
                    (symbol, trading_date, bucket_start, event_minute),
                ).fetchall()
        finally:
            conn.close()

        if not rows:
            return None

        first = rows[0]
        last = rows[-1]
        highs = [float(row["high"]) for row in rows if row["high"] is not None]
        lows = [float(row["low"]) for row in rows if row["low"] is not None]
        volumes = [int(row["volume"] or 0) for row in rows]

        if first["open"] is None or last["close"] is None or not highs or not lows:
            return None

        return {
            "trading_date": trading_date,
            "minute": "09:00" if resolution == 1440 else bucket_start,
            "resolution": resolution,
            "open": float(first["open"]),
            "high": max(highs),
            "low": min(lows),
            "close": float(last["close"]),
            "volume": sum(volumes),
            "data_source": str(last["data_source"] or "SSI_STREAM"),
            "provider_time": last["provider_time"],
        }

    def snapshot(self, *, symbol: str, resolution: int) -> dict:
        quote = self.latest_quote(symbol)
        if quote is None:
            return {
                "type": "snapshot",
                "symbol": symbol,
                "resolution": resolution,
                "quote": None,
                "candle": None,
                "server_time": datetime.now(VN_TZ).isoformat(),
            }

        candle = self.current_candle(
            symbol=symbol,
            trading_date=str(quote["trading_date"]),
            event_time=str(quote["event_time"]),
            resolution=resolution,
        )
        return {
            "type": "snapshot",
            "symbol": symbol,
            "resolution": resolution,
            "quote": quote,
            "candle": candle,
            "server_time": datetime.now(VN_TZ).isoformat(),
        }


class LiveGateway:
    def __init__(
        self,
        *,
        store: LiveSQLiteStore,
        interval_seconds: float = 3.0,
        revalidate_seconds: float = 30.0,
        access_client: SupabaseEntitlementClient | None = None,
    ) -> None:
        self.store = store
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.revalidate_seconds = max(10.0, float(revalidate_seconds))
        self.access_client = access_client or SupabaseEntitlementClient()

    def _authorize(self, *, token: str, symbol: str) -> bool:
        decision = self.access_client.check(token=token, symbol=symbol)
        return bool(decision.technical_allowed)

    async def _receive_subscription(self, websocket) -> tuple[str, int, str]:
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("type") != "subscribe":
            raise ValueError("subscribe message required")
        if payload.get("channel", "chart") != "chart":
            raise ValueError("unsupported channel")
        symbol = _normalize_symbol(payload.get("symbol"))
        resolution = _normalize_resolution(payload.get("resolution", 5))
        token = str(payload.get("token") or "").strip()
        return symbol, resolution, token

    async def handler(self, websocket) -> None:
        try:
            symbol, resolution, token = await self._receive_subscription(websocket)
        except (ValueError, TypeError, json.JSONDecodeError, asyncio.TimeoutError):
            await websocket.close(code=4400, reason="INVALID_SUBSCRIPTION")
            return

        try:
            while True:
                snapshot = self.store.snapshot(symbol=symbol, resolution=resolution)
                await websocket.send(
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                )

                try:
                    raw = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    continue

                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue

                if payload.get("type") == "ping":
                    await websocket.send('{"type":"pong"}')
                    continue

                if payload.get("type") == "subscribe":
                    if payload.get("channel", "chart") != "chart":
                        await websocket.close(code=4400, reason="INVALID_SUBSCRIPTION")
                        return
                    next_symbol = _normalize_symbol(payload.get("symbol", symbol))
                    next_resolution = _normalize_resolution(
                        payload.get("resolution", resolution)
                    )
                    next_token = str(payload.get("token") or token).strip()
                    symbol = next_symbol
                    resolution = next_resolution
                    token = next_token
        except ConnectionClosed:
            return
        except (sqlite3.Error, OSError):
            await websocket.close(code=1011, reason="LIVE_STORE_ERROR")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCC V2 live WebSocket gateway")
    parser.add_argument(
        "--realtime",
        type=Path,
        default=Path("/app/data/ssi_shadow.db"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--revalidate", type=float, default=30.0)
    return parser


async def _run(args) -> None:
    gateway = LiveGateway(
        store=LiveSQLiteStore(args.realtime),
        interval_seconds=args.interval,
        revalidate_seconds=args.revalidate,
    )
    async with serve(
        gateway.handler,
        args.host,
        args.port,
        ping_interval=20,
        ping_timeout=20,
        max_size=64 * 1024,
    ):
        await asyncio.Future()


def main() -> int:
    args = build_parser().parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
