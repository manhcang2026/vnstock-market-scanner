from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from websockets.exceptions import ConnectionClosed
from websockets.server import serve

from .canonical_market_reader import CanonicalMarketReader

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ALLOWED_RESOLUTIONS = {5, 15, 30, 60, 1440}

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


class LiveCanonicalStore:
    def __init__(self, market_dir: Path) -> None:
        self.reader = CanonicalMarketReader(market_dir, busy_timeout_ms=2500)

    def latest_quote(self, symbol: str) -> dict | None:
        return self.reader.latest_quote(symbol)

    def current_candle(
        self,
        *,
        symbol: str,
        trading_date: str,
        event_time: str | None,
        resolution: int,
    ) -> dict | None:
        if resolution == 1440:
            bucket_start = "00:00"
            rows = self.reader.candle_rows(
                symbol=symbol,
                trading_date=trading_date,
            )
        else:
            if not event_time:
                return None
            bucket_start = _bucket_start(event_time, resolution)
            rows = self.reader.candle_rows(
                symbol=symbol,
                trading_date=trading_date,
                minute_from=bucket_start,
                minute_to=event_time[:5],
            )

        if not rows:
            return None

        required_ohlc = ("open", "high", "low", "close")
        if any(row[field] is None for row in rows for field in required_ohlc):
            return None

        first = rows[0]
        last = rows[-1]
        highs = [float(row["high"]) for row in rows]
        lows = [float(row["low"]) for row in rows]
        volume = (
            None
            if any(row["volume"] is None for row in rows)
            else sum(int(row["volume"]) for row in rows)
        )

        return {
            "trading_date": trading_date,
            "minute": "09:00" if resolution == 1440 else bucket_start,
            "resolution": resolution,
            "open": float(first["open"]),
            "high": max(highs),
            "low": min(lows),
            "close": float(last["close"]),
            "volume": volume,
            "data_source": str(last["data_source"]),
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
            event_time=(
                str(quote["event_time"])
                if quote.get("event_time") is not None
                else None
            ),
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
        store: LiveCanonicalStore,
        interval_seconds: float = 3.0,
    ) -> None:
        self.store = store
        self.interval_seconds = max(1.0, float(interval_seconds))

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
        "--canonical-market-dir",
        type=Path,
        default=Path(os.getenv("CANONICAL_MARKET_DIR", "/app/data")),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--interval", type=float, default=3.0)
    return parser


async def _run(args) -> None:
    gateway = LiveGateway(
        store=LiveCanonicalStore(args.canonical_market_dir),
        interval_seconds=args.interval,
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
