from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from app.canonical_engine_store import CanonicalEngineStore
from app.canonical_eod import (
    resolve_eod_target,
    run_canonical_eod,
    validate_eod_pairs,
)
from app.canonical_market_store import (
    CanonicalMarketStore,
    DailyBar,
    MinuteBar,
    RealtimeMarketEvent,
)
from app.canonical_premarket import premarket_refusal_reason, validate_rebuild
from app.market_session import VN_TZ
from app.ssi_historical import SSINoDataFound


DAY = date(2026, 9, 28)
EXCHANGES = {"AAA": "HOSE"}


def _minute(symbol: str, day: date = DAY) -> dict[str, object]:
    return {
        "Symbol": symbol,
        "TradingDate": day.strftime("%d/%m/%Y"),
        "Time": "09:15:00",
        "Market": "HOSE",
        "Open": 10,
        "High": 11,
        "Low": 9,
        "Close": 10.5,
        "Volume": 100,
    }


def _daily(symbol: str, day: date = DAY) -> dict[str, object]:
    row = _minute(symbol, day)
    row.pop("Time")
    return row


def _seed_live(
    store: CanonicalMarketStore, symbol: str = "AAA", day: date = DAY
) -> None:
    store.upsert_minute_bars(
        [
            MinuteBar(
                symbol,
                day.isoformat(),
                "09:16",
                exchange="HOSE",
                close=10,
                source="SSI_STREAM",
            )
        ]
    )


def _seed_quote(
    store: CanonicalMarketStore,
    *,
    symbol: str = "AAA",
    day: date = DAY,
    price: float = 10,
    total_volume: int = 90,
    ref_price: float | None = None,
    change: float | None = None,
    ratio_change: float | None = None,
) -> None:
    event_at = datetime(day.year, day.month, day.day, 14, 30, tzinfo=VN_TZ)
    store.write_realtime_event(
        RealtimeMarketEvent(
            symbol=symbol,
            trading_date=day.isoformat(),
            event_at=event_at,
            minute="14:30",
            exchange="HOSE",
            price=price,
            total_volume=total_volume,
            provider_session="ATC",
            ref_price=ref_price,
            open=price - 1,
            high=price + 1,
            low=price - 2,
            close=price,
            bid_price1=price - 0.1,
            bid_vol1=100,
            ask_price1=price + 0.1,
            ask_vol1=200,
            change=change,
            ratio_change=ratio_change,
            trading_status="TRADE",
        ),
        observed_at=event_at,
    )


def _trusted_daily_bar(
    *,
    symbol: str = "AAA",
    day: date = DAY,
    exchange: str | None = "HOSE",
    open_price: float | None = 10,
    high: float | None = 11,
    low: float | None = 9,
    close: float | None = 10.5,
    volume: int | None = 100,
    quality_status: str = "TRUSTED",
) -> DailyBar:
    return DailyBar(
        symbol,
        day.isoformat(),
        exchange=exchange,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quality_status=quality_status,
    )


def _mark_rest_session_proof(
    store: CanonicalMarketStore, *, symbol: str = "AAA", day: date = DAY
) -> None:
    store.mark_rest_sessions_completed(
        mode="minute",
        symbol=symbol,
        resolution=1,
        rows_by_date={day.isoformat(): 1},
    )


class PairFetcher:
    def __init__(self, minute: object = "COMPLETED", daily: object = "COMPLETED"):
        self.minute = minute
        self.daily = daily
        self.calls = 0

    def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
        self.calls += 1
        if isinstance(self.minute, Exception):
            raise self.minute
        if self.minute == "NO_DATA":
            raise SSINoDataFound("NoDataFound")
        return [_minute(symbol)]

    def fetch_daily_ohlc(self, symbol, from_date, to_date):
        self.calls += 1
        if isinstance(self.daily, Exception):
            raise self.daily
        if self.daily == "NO_DATA":
            raise SSINoDataFound("NoDataFound")
        if self.daily == "EMPTY":
            return []
        return [_daily(symbol)]


def test_completed_minute_and_daily_pass_and_rerun_is_idempotent(tmp_path: Path) -> None:
    fetcher = PairFetcher()
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        first = run_canonical_eod(
            day=DAY, store=store, client=fetcher, exchange_map=EXCHANGES
        )
        second = run_canonical_eod(
            day=DAY, store=store, client=fetcher, exchange_map=EXCHANGES
        )
        assert first is not None and first.status == "PASS"
        assert second is not None and second.status == "PASS"
        assert fetcher.calls == 2
        assert store.connection(2026).execute(
            "SELECT COUNT(*) FROM daily_bars WHERE trading_date=?", (DAY.isoformat(),)
        ).fetchone()[0] == 1
        quote = store.connection(2026).execute(
            "SELECT * FROM latest_quotes WHERE symbol='AAA'"
        ).fetchone()
        assert tuple(
            quote[field]
            for field in (
                "last_price", "total_volume", "open", "high", "low", "close"
            )
        ) == (10.5, 100, 10.0, 11.0, 9.0, 10.5)
        assert tuple(
            quote[field]
            for field in (
                "event_time", "last_price_at", "ref_price", "bid_price1",
                "bid_vol1", "ask_price1", "ask_vol1", "provider_session",
                "trading_status",
            )
        ) == (None, None, None, None, None, None, None, None, None)


def test_hpg_eod_finalizes_stream_quote_preserves_facts_and_rejects_replay(
    tmp_path: Path,
) -> None:
    hpg_day = date(2026, 10, 2)
    exchanges = {"HPG": "HOSE"}

    class HpgFetcher(PairFetcher):
        def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
            self.calls += 1
            return [
                {
                    **_minute(symbol, hpg_day),
                    "Close": 20050,
                    "Volume": 35378700,
                }
            ]

        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            self.calls += 1
            return [
                {
                    **_daily(symbol, hpg_day),
                    "Open": 19800,
                    "High": 20200,
                    "Low": 19700,
                    "Close": 20050,
                    "Volume": 35378700,
                }
            ]

    fetcher = HpgFetcher()
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(
            store,
            symbol="HPG",
            day=hpg_day,
            price=19600,
            total_volume=28824200,
            ref_price=19500,
            change=100,
            ratio_change=0.51,
        )
        result = run_canonical_eod(
            day=hpg_day, store=store, client=fetcher, exchange_map=exchanges
        )
        assert result is not None and result.status == "PASS"
        connection = store.connection(2026)
        first = connection.execute(
            "SELECT * FROM latest_quotes WHERE symbol='HPG'"
        ).fetchone()
        assert tuple(
            first[field]
            for field in (
                "last_price", "total_volume", "open", "high", "low", "close"
            )
        ) == (20050, 35378700, 19800, 20200, 19700, 20050)
        assert tuple(
            first[field]
            for field in (
                "event_time", "last_price_at", "provider_session",
                "trading_status", "ref_price", "bid_price1", "bid_vol1",
                "ask_price1", "ask_vol1",
            )
        ) == (
            "14:30:00", None, "ATC", "TRADE", 19500, 19599.9, 100,
            19600.1, 200,
        )
        assert first["change"] == 550
        assert first["ratio_change"] == pytest.approx(550 / 19500 * 100)
        first_values = tuple(first)

        repeated = run_canonical_eod(
            day=hpg_day, store=store, client=fetcher, exchange_map=exchanges
        )
        assert repeated is not None and repeated.status == "PASS"
        assert fetcher.calls == 2
        assert tuple(
            connection.execute(
                "SELECT * FROM latest_quotes WHERE symbol='HPG'"
            ).fetchone()
        ) == first_values

        replay_at = datetime(2026, 10, 2, 15, 0, tzinfo=VN_TZ)
        replay = store.write_realtime_event(
            RealtimeMarketEvent(
                symbol="HPG", trading_date=hpg_day.isoformat(),
                event_at=replay_at, minute="15:00", exchange="HOSE",
                price=19600, total_volume=28824200, provider_session="ATC",
            ),
            observed_at=replay_at,
        )
        final = connection.execute(
            "SELECT last_price,total_volume FROM latest_quotes WHERE symbol='HPG'"
        ).fetchone()
        assert replay.rest_session_locked is True
        assert tuple(final) == (20050, 35378700)


def test_eod_quote_without_ref_price_nulls_stale_change_fields(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(
            store, ref_price=None, change=999, ratio_change=999
        )
        result = run_canonical_eod(
            day=DAY, store=store, client=PairFetcher(), exchange_map=EXCHANGES
        )
        assert result is not None and result.status == "PASS"
        quote = store.connection(2026).execute(
            "SELECT ref_price,change,ratio_change FROM latest_quotes WHERE symbol='AAA'"
        ).fetchone()
    assert tuple(quote) == (None, None, None)


def test_eod_preserves_last_price_at_when_stream_price_already_matches_close(
    tmp_path: Path,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=10.5, total_volume=90)
        result = run_canonical_eod(
            day=DAY, store=store, client=PairFetcher(), exchange_map=EXCHANGES
        )
        quote = store.connection(2026).execute(
            "SELECT last_price,last_price_at FROM latest_quotes WHERE symbol='AAA'"
        ).fetchone()
    assert result is not None and result.status == "PASS"
    assert tuple(quote) == (10.5, "14:30:00")


def test_minute_nodata_and_ambiguous_daily_is_accepted_degraded_without_daily(
    tmp_path: Path,
) -> None:
    exchanges = {"AAA": "HOSE", "BBB": "HOSE"}

    class Fetcher(PairFetcher):
        def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
            if symbol == "BBB":
                raise SSINoDataFound("NoDataFound")
            return [_minute(symbol)]

        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            return [] if symbol == "BBB" else [_daily(symbol)]

    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        _seed_live(store, "BBB")
        result = run_canonical_eod(
            day=DAY, store=store, client=Fetcher(), exchange_map=exchanges
        )
        assert result is not None and result.status == "DEGRADED"
        assert result.accepted_degraded == 1 and result.critical_failures == 0
        stream_row = store.connection(2026).execute(
            """SELECT source FROM minute_bars
               WHERE symbol='BBB' AND trading_date=?""",
            (DAY.isoformat(),),
        ).fetchone()
        assert stream_row["source"] == "SSI_STREAM"
        assert store.connection(2026).execute(
            "SELECT 1 FROM daily_bars WHERE symbol='BBB' AND trading_date=?",
            (DAY.isoformat(),),
        ).fetchone() is None


def test_minute_nodata_and_daily_nodata_preserve_stream_rows_as_degraded(
    tmp_path: Path,
) -> None:
    exchanges = {"AAA": "HOSE", "BBB": "HOSE"}

    class Fetcher(PairFetcher):
        def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
            if symbol == "BBB":
                raise SSINoDataFound("NoDataFound")
            return [_minute(symbol)]

        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            if symbol == "BBB":
                raise SSINoDataFound("NoDataFound")
            return [_daily(symbol)]

    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        _seed_live(store, "BBB")
        result = run_canonical_eod(
            day=DAY, store=store, client=Fetcher(), exchange_map=exchanges
        )
        assert result is not None and result.status == "DEGRADED"
        assert result.accepted_degraded == 1 and result.critical_failures == 0
        assert store.connection(2026).execute(
            """SELECT source FROM minute_bars
               WHERE symbol='BBB' AND trading_date=?""",
            (DAY.isoformat(),),
        ).fetchone()["source"] == "SSI_STREAM"
        assert store.connection(2026).execute(
            "SELECT 1 FROM daily_bars WHERE symbol='BBB' AND trading_date=?",
            (DAY.isoformat(),),
        ).fetchone() is None


def test_completed_minute_and_ambiguous_daily_fails(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        result = run_canonical_eod(
            day=DAY,
            store=store,
            client=PairFetcher(daily="EMPTY"),
            exchange_map=EXCHANGES,
        )
    assert result is not None and result.status == "FAIL"
    assert result.critical_failures == 1


def test_minute_failure_fails(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        result = run_canonical_eod(
            day=DAY,
            store=store,
            client=PairFetcher(minute=RuntimeError("boom")),
            exchange_map=EXCHANGES,
        )
    assert result is not None and result.status == "FAIL"
    assert result.minute_failed == 1


def test_no_live_evidence_skips_without_calling_provider(tmp_path: Path) -> None:
    output: list[str] = []
    fetcher = PairFetcher()
    with CanonicalMarketStore(tmp_path) as store:
        result = run_canonical_eod(
            day=DAY,
            store=store,
            client=fetcher,
            exchange_map=EXCHANGES,
            output=output.append,
        )
    assert result is None and fetcher.calls == 0
    assert output == ["SKIP_NO_LIVE_EVIDENCE day=2026-09-28"]


def test_wrong_date_daily_cannot_complete_selected_day(tmp_path: Path) -> None:
    class WrongDateFetcher(PairFetcher):
        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            return [_daily(symbol, date(2026, 9, 27))]

    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        result = run_canonical_eod(
            day=DAY,
            store=store,
            client=WrongDateFetcher(),
            exchange_map=EXCHANGES,
        )
        assert result is not None and result.status == "FAIL"
        assert store.connection(2026).execute(
            "SELECT COUNT(*) FROM daily_bars"
        ).fetchone()[0] == 0


def test_completed_checkpoint_without_session_proof_is_repaired_once(
    tmp_path: Path,
) -> None:
    class RepairFetcher(PairFetcher):
        minute_calls = 0
        daily_calls = 0

        def fetch_intraday_ohlc(self, *args, **kwargs):
            self.minute_calls += 1
            return [_minute("AAA")]

        def fetch_daily_ohlc(self, *args, **kwargs):
            self.daily_calls += 1
            raise AssertionError("completed daily checkpoint was retried")

    fetcher = RepairFetcher()
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=9, total_volume=90)
        store.upsert_daily_bars([_trusted_daily_bar()])
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode,
                symbol="AAA",
                from_date=DAY.isoformat(),
                to_date=DAY.isoformat(),
                resolution=resolution,
                year=2026,
                status="COMPLETED",
                rows_received=1,
                rows_written=1,
            )
        result = run_canonical_eod(
            day=DAY, store=store, client=fetcher, exchange_map=EXCHANGES
        )
        quote = store.connection(2026).execute(
            "SELECT last_price,total_volume FROM latest_quotes WHERE symbol='AAA'"
        ).fetchone()
        replay_at = datetime(2026, 9, 28, 15, 0, tzinfo=VN_TZ)
        replay = store.write_realtime_event(
            RealtimeMarketEvent(
                symbol="AAA", trading_date=DAY.isoformat(), event_at=replay_at,
                minute="15:00", exchange="HOSE", price=9, total_volume=90,
                provider_session="ATC",
            ),
            observed_at=replay_at,
        )
        repeated = run_canonical_eod(
            day=DAY, store=store, client=fetcher, exchange_map=EXCHANGES
        )
    assert result is not None and result.status == "PASS"
    assert repeated is not None and repeated.status == "PASS"
    assert tuple(quote) == (10.5, 100)
    assert replay.rest_session_locked is True
    assert fetcher.minute_calls == 1 and fetcher.daily_calls == 0


@pytest.mark.parametrize(
    "failure",
    [SSINoDataFound("NoDataFound"), RuntimeError("repair failed")],
)
def test_completed_checkpoint_session_repair_failure_is_fail_closed(
    tmp_path: Path,
    failure: Exception,
) -> None:
    class FailingRepair(PairFetcher):
        minute_calls = 0

        def fetch_intraday_ohlc(self, *args, **kwargs):
            self.minute_calls += 1
            raise failure

        def fetch_daily_ohlc(self, *args, **kwargs):
            raise AssertionError("completed daily checkpoint was retried")

    fetcher = FailingRepair()
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=9, total_volume=90)
        store.upsert_daily_bars([_trusted_daily_bar()])
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED", rows_received=1, rows_written=1,
            )
        connection = store.connection(2026)
        before = tuple(
            connection.execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
        result = run_canonical_eod(
            day=DAY, store=store, client=fetcher, exchange_map=EXCHANGES
        )
        after = tuple(
            connection.execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
        proof_count = connection.execute(
            "SELECT COUNT(*) FROM rest_session_status"
        ).fetchone()[0]
    assert result is not None and result.status == "FAIL"
    assert after == before
    assert proof_count == 0
    assert fetcher.minute_calls == 1


@pytest.mark.parametrize(
    ("minute_status", "daily_status"),
    [
        ("NO_DATA", "COMPLETED"),
        ("FAILED", "COMPLETED"),
        ("COMPLETED", "NO_DATA"),
        ("COMPLETED", "FAILED"),
        (None, "COMPLETED"),
        ("COMPLETED", None),
    ],
)
def test_eod_quote_finalization_requires_both_completed_proofs(
    tmp_path: Path,
    minute_status: str | None,
    daily_status: str | None,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=9, total_volume=90)
        store.upsert_daily_bars([_trusted_daily_bar()])
        for mode, resolution, status in (
            ("minute", 1, minute_status),
            ("daily", 0, daily_status),
        ):
            if status is not None:
                store.mark_fetch_status(
                    mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                    to_date=DAY.isoformat(), resolution=resolution, year=2026,
                    status=status,
                )
        before = tuple(
            store.connection(2026).execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
        finalized = store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        )
        after = tuple(
            store.connection(2026).execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
    assert finalized is False
    assert after == before


def test_completed_pair_without_exact_session_proof_fails_validation(
    tmp_path: Path,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store)
        store.upsert_daily_bars([_trusted_daily_bar()])
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED", rows_received=1, rows_written=1,
            )
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == (
        "AAA:MINUTE_COMPLETED_WITHOUT_REST_SESSION_PROOF",
    )


@pytest.mark.parametrize(
    "daily",
    [
        _trusted_daily_bar(quality_status="PARTIAL"),
        _trusted_daily_bar(open_price=None),
        _trusted_daily_bar(high=None),
        _trusted_daily_bar(low=None),
        _trusted_daily_bar(close=None),
        _trusted_daily_bar(volume=None),
        _trusted_daily_bar(high=8),
        _trusted_daily_bar(volume=-1),
    ],
)
def test_partial_or_invalid_daily_bar_cannot_overwrite_stream_quote(
    tmp_path: Path,
    daily: DailyBar,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=9, total_volume=90)
        store.upsert_daily_bars([daily])
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        connection = store.connection(2026)
        before = tuple(
            connection.execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
        assert store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        ) is False
        after = tuple(
            connection.execute(
                "SELECT * FROM latest_quotes WHERE symbol='AAA'"
            ).fetchone()
        )
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert after == before
    assert result.status == "FAIL"
    assert result.reasons[0].startswith("AAA:DAILY_QUOTE_NOT_AUTHORITATIVE:")


def test_partial_daily_bar_does_not_create_minimal_quote(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        store.upsert_daily_bars(
            [_trusted_daily_bar(quality_status="PARTIAL")]
        )
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        assert store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        ) is False
        assert store.connection(2026).execute(
            "SELECT COUNT(*) FROM latest_quotes"
        ).fetchone()[0] == 0
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == (
        "AAA:DAILY_QUOTE_NOT_AUTHORITATIVE:QUALITY_PARTIAL",
    )


def test_missing_daily_row_prevents_finalization_and_fails_validation(
    tmp_path: Path,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store)
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        assert store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        ) is False
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == ("AAA:DAILY_COMPLETED_WITHOUT_EXACT_IDENTITY",)


def test_completed_pair_with_stale_quote_fails_explicit_quote_validation(
    tmp_path: Path,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_quote(store, price=9, total_volume=90)
        store.upsert_daily_bars(
            [_trusted_daily_bar()]
        )
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == (
        "AAA:LATEST_QUOTE_DAILY_MISMATCH:last_price,total_volume,open,high,low,close",
    )


def test_completed_pair_without_quote_fails_explicit_quote_validation(
    tmp_path: Path,
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        store.upsert_daily_bars([_trusted_daily_bar()])
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == ("AAA:LATEST_QUOTE_MISSING_FOR_COMPLETED_PAIR",)


def test_daily_identity_mismatch_is_critical(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        store.upsert_daily_bars(
            [_trusted_daily_bar(exchange="HNX")]
        )
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode, symbol="AAA", from_date=DAY.isoformat(),
                to_date=DAY.isoformat(), resolution=resolution, year=2026,
                status="COMPLETED",
            )
        assert store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        ) is False
        result = validate_eod_pairs(
            store=store, day=DAY, exchange_map=EXCHANGES
        )
    assert result.status == "FAIL"
    assert result.reasons == ("AAA:DAILY_CANONICAL_IDENTITY_MISMATCH",)


def test_premarket_refuses_after_session_start_or_today_evidence(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        assert premarket_refusal_reason(
            market_db_dir=tmp_path,
            day=DAY,
            now=datetime(2026, 9, 28, 9, 1),
            exchange_map=EXCHANGES,
        ) == "MARKET_DAY_ALREADY_STARTED"
        _seed_live(store)
        assert premarket_refusal_reason(
            market_db_dir=tmp_path,
            day=DAY,
            now=datetime(2026, 9, 28, 8, 55),
            exchange_map=EXCHANGES,
        ) == "TODAY_HAS_CANONICAL_LIVE_EVIDENCE"


def test_premarket_allows_more_than_ten_minutes_before_market(tmp_path: Path) -> None:
    assert premarket_refusal_reason(
        market_db_dir=tmp_path,
        day=DAY,
        now=datetime(2026, 9, 28, 8, 49),
        exchange_map=EXCHANGES,
    ) is None


@pytest.mark.parametrize(
    ("clock", "reason"),
    [
        ((8, 50), "INSUFFICIENT_PREMARKET_LEAD"),
        ((8, 59), "INSUFFICIENT_PREMARKET_LEAD"),
        ((9, 0), "MARKET_DAY_ALREADY_STARTED"),
    ],
)
def test_premarket_refuses_inside_lead_window_and_at_market_start(
    tmp_path: Path, clock: tuple[int, int], reason: str
) -> None:
    assert premarket_refusal_reason(
        market_db_dir=tmp_path,
        day=DAY,
        now=datetime(2026, 9, 28, clock[0], clock[1]),
        exchange_map=EXCHANGES,
    ) == reason


def test_eod_resolver_selects_today_after_close(tmp_path: Path) -> None:
    tuesday = date(2026, 9, 29)
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store, day=tuesday)
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, 16, 15),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "EOD_TARGET" and resolution.day == tuesday


@pytest.mark.parametrize("clock", [(15, 0), (16, 14)])
def test_eod_resolver_refuses_current_day_before_1615(
    tmp_path: Path, clock: tuple[int, int]
) -> None:
    tuesday = date(2026, 9, 29)
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store, day=tuesday)
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, clock[0], clock[1]),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "REFUSED_EOD_NOT_READY"
    assert resolution.day == tuesday


def test_eod_resolver_selects_prior_day_before_market(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, 8, 20),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "EOD_TARGET" and resolution.day == DAY


@pytest.mark.parametrize("clock", [(9, 30), (12, 0), (13, 30)])
def test_eod_resolver_refuses_during_entire_active_market_day(
    tmp_path: Path, clock: tuple[int, int]
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, clock[0], clock[1]),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "REFUSED_ACTIVE_MARKET"
    assert resolution.day is None


def test_eod_resolver_selects_latest_prior_evidence_on_weekend(tmp_path: Path) -> None:
    friday = date(2026, 10, 2)
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store, day=friday)
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 10, 3, 10, 0),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "EOD_TARGET" and resolution.day == friday


def test_eod_resolver_skips_safely_when_no_target_exists(tmp_path: Path) -> None:
    resolution = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, 8, 20),
        exchange_map=EXCHANGES,
    )
    assert resolution.status == "SKIP_NO_EOD_TARGET"
    assert resolution.reason == "NO_CANONICAL_LIVE_EVIDENCE"


def test_eod_resolver_skips_latest_evidence_already_completed(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        _seed_live(store)
        store.upsert_daily_bars([_trusted_daily_bar()])
        _mark_rest_session_proof(store)
        for mode, resolution in (("minute", 1), ("daily", 0)):
            store.mark_fetch_status(
                mode=mode,
                symbol="AAA",
                from_date=DAY.isoformat(),
                to_date=DAY.isoformat(),
                resolution=resolution,
                year=DAY.year,
                status="COMPLETED",
            )
        assert store.finalize_eod_latest_quote(
            symbol="AAA", trading_date=DAY.isoformat(), expected_exchange="HOSE"
        ) is True
    resolved = resolve_eod_target(
        db_dir=tmp_path,
        now=datetime(2026, 9, 29, 8, 20),
        exchange_map=EXCHANGES,
    )
    assert resolved.status == "SKIP_NO_EOD_TARGET"
    assert resolved.day == DAY
    assert resolved.reason == "LATEST_EVIDENCE_ALREADY_PASS"


def test_rebuild_validation_counts_today_and_preserves_signal_events(
    tmp_path: Path,
) -> None:
    engine = tmp_path / "ccc_engine.db"
    with CanonicalEngineStore(engine) as store:
        store.connection.execute(
            "INSERT INTO technical_baseline VALUES (?,?,?,?,?,?,?,?)",
            ("AAA", DAY.isoformat(), 10, 10, 10, 10, 10, "now"),
        )
        store.connection.execute(
            "INSERT INTO volume_baseline_curve VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("AAA", "09:15", DAY.isoformat(), 100, 10, 10, 10, 10, 10, "now"),
        )
        store.connection.execute(
            """INSERT INTO current_state(
               symbol,trading_date,quality_status,reason_codes_json,updated_at
               ) VALUES ('AAA',?,'OK','[]','now')""",
            (DAY.isoformat(),),
        )
        store.connection.execute(
            """INSERT INTO signal_events(
               symbol,signal_state,signal_level,signal_direction,reason_codes_json,
               engine_version,config_version,detected_at
               ) VALUES ('AAA','WATCHING',1,'NEUTRAL','[]','e','c','now')"""
        )
        store.connection.commit()
        store.begin_rebuild(DAY.isoformat())
        assert store.connection.execute(
            "SELECT COUNT(*) FROM signal_events"
        ).fetchone()[0] == 1
        # Restore the disposable rows to exercise the standalone validator.
        store.connection.execute(
            "INSERT INTO technical_baseline VALUES (?,?,?,?,?,?,?,?)",
            ("AAA", DAY.isoformat(), 10, 10, 10, 10, 10, "now"),
        )
        store.connection.execute(
            "INSERT INTO volume_baseline_curve VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("AAA", "09:15", DAY.isoformat(), 100, 10, 10, 10, 10, 10, "now"),
        )
        store.connection.execute(
            """INSERT INTO current_state(
               symbol,trading_date,quality_status,reason_codes_json,updated_at
               ) VALUES ('AAA',?,'OK','[]','now')""",
            (DAY.isoformat(),),
        )
        store.connection.commit()
    assert validate_rebuild(
        engine_db=engine, day=DAY, expected_symbols=1
    ) == {
        "technical_baseline": 1,
        "volume_baseline_curve": 1,
        "current_state": 1,
    }


def test_new_wrappers_are_canonical_and_restart_only_collector() -> None:
    base = Path(__file__).resolve().parents[1] / "ops" / "systemd"
    eod = (base / "ccc-canonical-eod-wrapper.sh").read_text(encoding="utf-8")
    premarket = (base / "ccc-canonical-premarket-wrapper.sh").read_text(
        encoding="utf-8"
    )
    forbidden = ("ssi_history_", "ccc_market_v2", "ccc_v2_baseline", "chart-api", "live-ws")
    for wrapper in (eod, premarket):
        assert "trap restart_collector EXIT" in wrapper
        assert 'stop collector' in wrapper
        assert 'up -d collector' in wrapper
        assert all(value not in wrapper for value in forbidden)
    assert "app.canonical_eod" in eod
    resolution = eod.index("--resolve-target")
    trap = eod.index("trap restart_collector EXIT")
    stop = eod.index("stop collector")
    assert resolution < trap < stop
    assert (
        "REFUSED_ACTIVE_MARKET*|REFUSED_EOD_NOT_READY*|SKIP_NO_EOD_TARGET*"
        in eod
    )
    assert "app.rebuild_engine" in premarket
    premarket_check = premarket.index("app.canonical_premarket check")
    premarket_trap = premarket.index("trap restart_collector EXIT")
    premarket_stop = premarket.index("stop collector")
    assert premarket_check < premarket_trap < premarket_stop


def test_timer_persistence_matches_safety_policy() -> None:
    base = Path(__file__).resolve().parents[1] / "ops" / "systemd"
    eod = (base / "ccc-canonical-eod.timer").read_text(encoding="utf-8")
    premarket = (base / "ccc-canonical-premarket.timer").read_text(
        encoding="utf-8"
    )
    assert "OnCalendar=Mon..Fri *-*-* 16:15:00 Asia/Ho_Chi_Minh" in eod
    assert "Persistent=false" in eod
    assert "OnCalendar=Mon..Fri *-*-* 08:20:00 Asia/Ho_Chi_Minh" in premarket
    assert "Persistent=true" in premarket


def test_retired_timer_is_absent_and_not_referenced_by_canonical_units() -> None:
    base = Path(__file__).resolve().parents[1] / "ops" / "systemd"
    assert not (base / "ccc-ssi-daily-finalize.timer").exists()
    canonical = "\n".join(
        path.read_text(encoding="utf-8")
        for path in base.glob("ccc-canonical-*")
    )
    assert "ccc-ssi-daily-finalize" not in canonical
