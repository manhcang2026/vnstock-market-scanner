from __future__ import annotations

import asyncio
import json
from pathlib import Path

from websockets.exceptions import ConnectionClosed

from app.canonical_market_store import CanonicalMarketStore, MinuteBar
from app.live_ws import LiveCanonicalStore, LiveGateway, _bucket_start


def _seed(
    path: Path,
    *,
    null_volume: bool = False,
    incomplete_ohlc: bool = False,
) -> None:
    rows = [
        MinuteBar(
            symbol="FPT", trading_date="2026-09-17", minute="10:15",
            exchange="HOSE", open=None if incomplete_ohlc else 73000,
            high=73500, low=72900, close=73400, volume=100000,
            source="SSI_STREAM",
            quality_status="PARTIAL" if incomplete_ohlc else "TRUSTED",
            is_finalized=1,
        ),
        MinuteBar(
            symbol="FPT", trading_date="2026-09-17", minute="10:16",
            exchange="HOSE", open=73400, high=73800, low=73300, close=73700,
            volume=None if null_volume else 120000, source="SSI_STREAM",
            quality_status="MISSING_VOLUME" if null_volume else "TRUSTED",
            is_finalized=1,
        ),
        MinuteBar(
            symbol="FPT", trading_date="2026-09-17", minute="10:17",
            exchange="HOSE", open=73700, high=74000, low=73600, close=73800,
            volume=90000, source="SSI_STREAM", quality_status="TRUSTED",
            is_finalized=0,
        ),
    ]
    with CanonicalMarketStore(path) as store:
        store.upsert_minute_bars(rows)
        connection = store.connection(2026)
        connection.execute(
            """
            INSERT INTO latest_quotes(
              symbol,trading_date,event_time,last_price,last_price_at,total_volume,
              ref_price,open,high,low,close,bid_price1,bid_vol1,ask_price1,
              ask_vol1,change,ratio_change,exchange,provider_session,
              trading_status,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "FPT", "2026-09-17", "10:17:30", 73800, "10:17:30",
                1000000, 72700, 73000, 74000, 72800, 73800, 73700, 1000,
                73800, 2000, 1100, 1.51, "HOSE", "C", "N",
                "2026-09-17T10:17:30+07:00",
            ),
        )
        connection.commit()


def test_bucket_start_and_resolution_behavior() -> None:
    assert _bucket_start("10:17:30", 5) == "10:15"
    assert _bucket_start("10:17:30", 15) == "10:15"
    assert _bucket_start("10:17:30", 30) == "10:00"
    assert _bucket_start("10:17:30", 60) == "10:00"
    assert _bucket_start("10:17:30", 1440) == "00:00"


def test_snapshot_uses_canonical_quote_and_current_candle(tmp_path: Path) -> None:
    _seed(tmp_path)
    snapshot = LiveCanonicalStore(tmp_path).snapshot(symbol="FPT", resolution=5)
    assert set(snapshot) == {
        "type", "symbol", "resolution", "quote", "candle", "server_time"
    }
    assert snapshot["quote"]["source"] == "CANONICAL_MARKET"
    assert snapshot["quote"]["trading_session"] == "C"
    candle = snapshot["candle"]
    assert candle["minute"] == "10:15"
    assert candle["open"] == 73000
    assert candle["high"] == 74000
    assert candle["low"] == 72900
    assert candle["close"] == 73800
    assert candle["volume"] == 310000
    assert candle["data_source"] == "SSI_STREAM"


def test_daily_candle_remains_minute_rollup(tmp_path: Path) -> None:
    _seed(tmp_path)
    candle = LiveCanonicalStore(tmp_path).snapshot(
        symbol="FPT", resolution=1440
    )["candle"]
    assert candle["minute"] == "09:00"
    assert candle["volume"] == 310000


def test_unknown_volume_is_null_not_zero(tmp_path: Path) -> None:
    _seed(tmp_path, null_volume=True)
    candle = LiveCanonicalStore(tmp_path).snapshot(symbol="FPT", resolution=5)[
        "candle"
    ]
    assert candle is not None
    assert candle["volume"] is None


def test_incomplete_ohlc_does_not_fabricate_candle(tmp_path: Path) -> None:
    _seed(tmp_path, incomplete_ohlc=True)
    snapshot = LiveCanonicalStore(tmp_path).snapshot(symbol="FPT", resolution=5)
    assert snapshot["quote"] is not None
    assert snapshot["candle"] is None


def test_missing_canonical_shard_returns_empty_public_snapshot(tmp_path: Path) -> None:
    snapshot = LiveCanonicalStore(tmp_path).snapshot(symbol="FPT", resolution=5)
    assert snapshot["quote"] is None
    assert snapshot["candle"] is None
    assert not list(tmp_path.glob("*.db"))


def test_public_subscription_contract_and_interval_are_unchanged(tmp_path: Path) -> None:
    class FakeWebSocket:
        async def recv(self):
            return json.dumps({
                "type": "subscribe", "channel": "chart", "symbol": "HPG",
                "resolution": 15,
            })

    gateway = LiveGateway(store=LiveCanonicalStore(tmp_path), interval_seconds=0.1)
    symbol, resolution, token = asyncio.run(
        gateway._receive_subscription(FakeWebSocket())
    )
    assert (symbol, resolution, token) == ("HPG", 15, "")
    assert gateway.interval_seconds == 1.0


def test_anonymous_handler_enters_public_snapshot_path() -> None:
    class SnapshotStore:
        def __init__(self):
            self.calls = []

        def snapshot(self, *, symbol, resolution):
            self.calls.append((symbol, resolution))
            return {
                "type": "snapshot", "symbol": symbol, "resolution": resolution,
                "quote": None, "candle": None,
                "server_time": "2026-09-23T10:00:00+07:00",
            }

    class FakeWebSocket:
        def __init__(self):
            self.sent = []

        async def recv(self):
            return json.dumps({
                "type": "subscribe", "channel": "chart", "symbol": "HPG",
                "resolution": 15,
            })

        async def send(self, message):
            self.sent.append(json.loads(message))
            raise ConnectionClosed(None, None)

        async def close(self, *, code, reason):
            raise AssertionError(f"public subscription was rejected: {code} {reason}")

    store = SnapshotStore()
    websocket = FakeWebSocket()
    gateway = LiveGateway(store=store)
    asyncio.run(gateway.handler(websocket))
    assert store.calls == [("HPG", 15)]
    assert websocket.sent[0]["type"] == "snapshot"
    assert websocket.sent[0]["symbol"] == "HPG"
