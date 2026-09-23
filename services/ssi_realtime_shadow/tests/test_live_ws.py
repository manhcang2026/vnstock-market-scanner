from pathlib import Path
import asyncio
import json
import sqlite3

from websockets.exceptions import ConnectionClosed

from app.live_ws import LiveGateway, LiveSQLiteStore, _bucket_start


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE latest_quotes (
          symbol TEXT PRIMARY KEY,
          trading_date TEXT,
          event_time TEXT,
          last_price REAL,
          total_volume INTEGER,
          ref_price REAL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          bid_price1 REAL,
          bid_vol1 INTEGER,
          ask_price1 REAL,
          ask_vol1 INTEGER,
          change REAL,
          ratio_change REAL,
          exchange TEXT,
          trading_session TEXT,
          trading_status TEXT,
          updated_at TEXT
        );

        CREATE TABLE minute_bars (
          trading_date TEXT,
          minute TEXT,
          symbol TEXT,
          exchange TEXT,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          volume INTEGER,
          quality_status TEXT,
          data_source TEXT,
          provider_time TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO latest_quotes VALUES (
          'FPT','2026-09-17','10:17:30',
          73800,1000000,72700,73000,74000,72800,73800,
          73700,1000,73800,2000,1100,1.51,'HOSE','C','N',
          '2026-09-17T10:17:30+07:00'
        )
        """
    )
    rows = [
        ('2026-09-17','10:15','FPT','HOSE',73000,73500,72900,73400,100000,'TRUSTED','SSI_STREAM','10:15:59'),
        ('2026-09-17','10:16','FPT','HOSE',73400,73800,73300,73700,120000,'TRUSTED','SSI_STREAM','10:16:59'),
        ('2026-09-17','10:17','FPT','HOSE',73700,74000,73600,73800,90000,'TRUSTED','SSI_STREAM','10:17:30'),
    ]
    conn.executemany("INSERT INTO minute_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_bucket_start() -> None:
    assert _bucket_start("10:17:30", 5) == "10:15"
    assert _bucket_start("10:17:30", 15) == "10:15"
    assert _bucket_start("10:17:30", 30) == "10:00"
    assert _bucket_start("10:17:30", 60) == "10:00"
    assert _bucket_start("10:17:30", 1440) == "00:00"


def test_snapshot_builds_current_five_minute_candle(tmp_path: Path) -> None:
    db = tmp_path / "live.db"
    _make_db(db)
    _seed(db)

    snapshot = LiveSQLiteStore(db).snapshot(symbol="FPT", resolution=5)

    assert snapshot["quote"]["last_price"] == 73800
    candle = snapshot["candle"]
    assert candle["minute"] == "10:15"
    assert candle["open"] == 73000
    assert candle["high"] == 74000
    assert candle["low"] == 72900
    assert candle["close"] == 73800
    assert candle["volume"] == 310000


def test_snapshot_builds_daily_candle(tmp_path: Path) -> None:
    db = tmp_path / "live.db"
    _make_db(db)
    _seed(db)

    snapshot = LiveSQLiteStore(db).snapshot(symbol="FPT", resolution=1440)
    candle = snapshot["candle"]

    assert candle["minute"] == "09:00"
    assert candle["open"] == 73000
    assert candle["high"] == 74000
    assert candle["low"] == 72900
    assert candle["close"] == 73800
    assert candle["volume"] == 310000


def test_public_chart_subscription_does_not_require_token(tmp_path: Path) -> None:
    class FakeWebSocket:
        async def recv(self):
            return json.dumps({
                "type": "subscribe",
                "channel": "chart",
                "symbol": "HPG",
                "resolution": 15,
            })

    gateway = LiveGateway(store=LiveSQLiteStore(tmp_path / "missing.db"))
    symbol, resolution, token = asyncio.run(
        gateway._receive_subscription(FakeWebSocket())
    )

    assert (symbol, resolution, token) == ("HPG", 15, "")


def test_anonymous_handler_enters_public_snapshot_path() -> None:
    class SnapshotStore:
        def __init__(self):
            self.calls = []

        def snapshot(self, *, symbol, resolution):
            self.calls.append((symbol, resolution))
            return {
                "type": "snapshot",
                "symbol": symbol,
                "resolution": resolution,
                "quote": None,
                "candle": None,
                "server_time": "2026-09-23T10:00:00+07:00",
            }

    class FakeWebSocket:
        def __init__(self):
            self.sent = []

        async def recv(self):
            return json.dumps({
                "type": "subscribe",
                "channel": "chart",
                "symbol": "HPG",
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
