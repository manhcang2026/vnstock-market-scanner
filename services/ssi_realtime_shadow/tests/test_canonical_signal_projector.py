from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from app.canonical_engine_store import CanonicalEngineStore, CurrentState
from app.canonical_signal_projector import (
    CanonicalSignalProjector,
    build_technical_state,
)
from app.signal_config import load_signal_config
from app.market_session import VN_TZ


DAY = "2026-09-25"
UPDATED_AT = "2026-09-25T03:00:00+00:00"
OBSERVED_AT = datetime(2026, 9, 25, 10, 0, tzinfo=VN_TZ)


def _state(**changes: object) -> CurrentState:
    state = CurrentState(
        symbol="AAA",
        exchange="HNX",
        trading_date=DAY,
        minute="10:00",
        last_price=101,
        cumulative_volume=1_000,
        day_rvol=1.0,
        rvol15=1.0,
        rvol30=1.0,
        price5_pct=0.0,
        price15_pct=0.0,
        ma10=100,
        ma200=95,
        distance_ma10_pct=1.0,
        distance_ma200_pct=6.315,
        baseline_sessions_used=10,
        day_rvol_sessions_used=10,
        rvol15_sessions_used=10,
        rvol30_sessions_used=10,
        quality_status="OK",
        reason_codes_json="[]",
        updated_at=UPDATED_AT,
    )
    return replace(state, **changes)


def _strong_positive(**changes: object) -> CurrentState:
    return _state(
        day_rvol=1.4,
        rvol15=2.0,
        rvol30=2.0,
        price5_pct=0.8,
        price15_pct=1.2,
        **changes,
    )


def _projector(tmp_path: Path) -> CanonicalSignalProjector:
    return CanonicalSignalProjector(CanonicalEngineStore(tmp_path / "engine.db"))


def _signal(projector: CanonicalSignalProjector):
    row = projector.engine_store.signal_row("AAA")
    assert row is not None
    return row


def _project(
    projector: CanonicalSignalProjector,
    state: CurrentState,
    observed_at: datetime = OBSERVED_AT,
):
    return projector.project(state, observed_at)


def _observed(hour: int, minute: int, *, day: int = 25) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=VN_TZ)


def test_signal_schema_is_additive_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "engine.db"
    first = CanonicalEngineStore(path)
    first.close()
    second = CanonicalEngineStore(path)
    tables = {
        row[0]
        for row in second.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    current_columns = {
        row[1]
        for row in second.connection.execute(
            "PRAGMA table_info(signal_state_current)"
        )
    }
    assert {"signal_state_current", "signal_events"} <= tables
    assert {
        "session_type",
        "signal_direction",
        "metrics_trusted",
        "baseline_sessions_used",
        "engine_version",
        "config_version",
    } <= current_columns
    assert second.connection.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0] == "3"


@pytest.mark.parametrize(
    ("expected", "state"),
    (
        (
            "FLOW_APPEARING",
            _state(
                day_rvol=1.2,
                rvol15=1.8,
                rvol30=1.8,
                price5_pct=0.5,
                price15_pct=0.8,
            ),
        ),
        ("FLOW_PRICE_CONFIRMED", _strong_positive()),
        (
            "SELLING_PRESSURE",
            _state(
                day_rvol=1.2,
                rvol15=1.8,
                rvol30=1.8,
                price5_pct=-0.8,
                price15_pct=-1.2,
            ),
        ),
    ),
)
def test_canonical_continuous_state_uses_existing_classifier(
    tmp_path: Path, expected: str, state: CurrentState
) -> None:
    projector = _projector(tmp_path)
    _project(projector, state)
    assert _signal(projector)["signal_state"] == expected


@pytest.mark.parametrize("sessions", (10, 9, 8))
def test_usable_canonical_baseline_can_emit_same_strong_signal(
    tmp_path: Path, sessions: int
) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _strong_positive(
            day_rvol_sessions_used=sessions,
            rvol15_sessions_used=sessions,
            rvol30_sessions_used=sessions,
        )
    )
    row = _signal(projector)
    assert row["signal_state"] == "FLOW_PRICE_CONFIRMED"
    assert row["baseline_sessions_used"] == sessions
    assert row["metrics_trusted"] == 1


def test_seven_session_baseline_blocks_strong_but_allows_watching(
    tmp_path: Path,
) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _strong_positive(
            day_rvol_sessions_used=10,
            rvol15_sessions_used=9,
            rvol30_sessions_used=7,
        )
    )
    row = _signal(projector)
    assert row["signal_state"] == "WATCHING"
    assert row["baseline_sessions_used"] == 7
    assert row["metrics_trusted"] == 0


def test_missing_ma200_does_not_make_signal_metrics_untrusted(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _strong_positive(
            ma200=None,
            distance_ma200_pct=None,
            quality_status="PARTIAL",
            reason_codes_json='["INSUFFICIENT_MA200"]',
        )
    )
    row = _signal(projector)
    assert row["metrics_trusted"] == 1
    assert row["signal_state"] == "FLOW_PRICE_CONFIRMED"


@pytest.mark.parametrize("reason", ("CURRENT_GAP", "NO_BASELINE"))
def test_canonical_trust_blockers_prevent_strong_signal(
    tmp_path: Path, reason: str
) -> None:
    projector = _projector(tmp_path)
    _project(
        projector, _strong_positive(reason_codes_json=json.dumps([reason]))
    )
    row = _signal(projector)
    assert row["metrics_trusted"] == 0
    assert row["signal_state"] == "WATCHING"


def test_missing_price_and_rvol_are_preserved_as_none(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    state = _state(
        last_price=None,
        day_rvol=None,
        rvol15=None,
        rvol30=None,
        price5_pct=None,
        price15_pct=None,
        cumulative_volume=None,
    )
    technical = build_technical_state(state, load_signal_config(), OBSERVED_AT)
    assert technical.last_price is None
    assert technical.day_rvol is None
    assert technical.rvol15 is None
    assert technical.rvol30 is None
    assert technical.price5_pct is None
    assert technical.price15_pct is None
    assert not technical.metrics_trusted


def test_price_confirmed_state_can_become_momentum_maintained(
    tmp_path: Path,
) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _state(
            day_rvol=1.4,
            rvol30=2.0,
            price15_pct=1.2,
        )
    )
    _project(
        projector,
        _state(rvol30=1.4, price15_pct=-0.2, updated_at="2026-09-25T03:01:00+00:00")
    )
    row = _signal(projector)
    assert row["signal_state"] == "MOMENTUM_MAINTAINED"
    assert row["previous_signal_state"] == "FLOW_PRICE_CONFIRMED"
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 2


def test_maintained_state_becomes_contextual_weakening_with_one_event(
    tmp_path: Path,
) -> None:
    projector = _projector(tmp_path)
    _project(projector, _strong_positive(), _observed(10, 0))
    _project(
        projector,
        _state(
            minute="10:01",
            rvol30=1.4,
            price15_pct=-0.2,
            updated_at="2026-09-25T03:01:00+00:00",
        ),
        _observed(10, 1),
    )
    before = projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0]

    result = _project(
        projector,
        _state(
            minute="10:02",
            day_rvol=1.4,
            rvol15=1.6,
            rvol30=1.5,
            price5_pct=-0.8,
            price15_pct=-0.5,
            updated_at="2026-09-25T03:02:00+00:00",
        ),
        _observed(10, 2),
    )

    row = _signal(projector)
    after = projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0]
    event = projector.engine_store.connection.execute(
        """SELECT previous_signal_state,signal_state
           FROM signal_events ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert result.event_appended
    assert row["signal_state"] == "MOMENTUM_WEAKENING"
    assert row["previous_signal_state"] == "MOMENTUM_MAINTAINED"
    assert after == before + 1
    assert tuple(event) == ("MOMENTUM_MAINTAINED", "MOMENTUM_WEAKENING")


def test_same_state_does_not_append_duplicate_event(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    state = _state(
        day_rvol=1.2,
        rvol15=1.8,
        rvol30=1.8,
        price5_pct=-0.8,
        price15_pct=-1.2,
    )
    _project(projector, state)
    first = dict(_signal(projector))
    result = _project(
        projector,
        replace(state, updated_at="2026-09-25T03:01:00+00:00")
    )
    second = _signal(projector)
    assert not result.event_appended
    assert second["state_changed_at"] == first["state_changed_at"]
    assert second["signal_at"] == first["signal_at"]
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1


def test_first_normal_state_appends_no_event(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    result = _project(projector, _state())
    assert not result.event_appended
    assert _signal(projector)["previous_signal_state"] is None
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (_state(day_rvol=1.3), "WATCHING"),
        (_strong_positive(), "FLOW_PRICE_CONFIRMED"),
    ),
)
def test_first_actionable_state_appends_one_event_with_null_previous(
    tmp_path: Path, state: CurrentState, expected: str
) -> None:
    projector = _projector(tmp_path)
    result = _project(projector, state)
    event = projector.engine_store.connection.execute(
        "SELECT previous_signal_state,signal_state FROM signal_events"
    ).fetchone()
    assert result.event_appended
    assert tuple(event) == (None, expected)
    assert _signal(projector)["previous_signal_state"] is None
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1


def test_state_transition_appends_exactly_one_event(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    _project(projector, _state())
    result = _project(
        projector,
        _strong_positive(updated_at="2026-09-25T03:01:00+00:00")
    )
    event = projector.engine_store.connection.execute(
        "SELECT previous_signal_state,signal_state FROM signal_events"
    ).fetchone()
    assert result.event_appended
    assert tuple(event) == ("NORMAL", "FLOW_PRICE_CONFIRMED")
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1


def test_previous_trading_date_state_is_not_reused(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _strong_positive(
            trading_date="2026-09-24",
            updated_at="2026-09-24T03:00:00+00:00",
        )
    )
    _project(
        projector,
        _state(rvol30=1.4, price15_pct=-0.2, updated_at=UPDATED_AT)
    )
    row = _signal(projector)
    assert row["trading_date"] == DAY
    assert row["signal_state"] == "NORMAL"
    assert row["previous_signal_state"] is None


def test_inactive_session_preserves_existing_state(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    _project(projector, _strong_positive())
    result = _project(
        projector,
        _state(
            minute="11:29",
            day_rvol=2.0,
            rvol15=3.0,
            rvol30=3.0,
            price5_pct=-2.0,
            price15_pct=-2.0,
            updated_at="2026-09-25T04:30:00+00:00",
        ),
        _observed(12, 0),
    )
    row = _signal(projector)
    assert row["session_type"] == "LUNCH_BREAK"
    assert row["signal_state"] == "FLOW_PRICE_CONFIRMED"
    assert not result.event_appended


def test_open_auction_projection_is_skipped(tmp_path: Path) -> None:
    projector = _projector(tmp_path)
    result = _project(
        projector,
        _strong_positive(exchange="HOSE", minute="09:00"),
        _observed(9, 5),
    )
    assert not result.state_written
    assert not result.event_appended
    assert projector.engine_store.signal_row("AAA") is None
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "continuous_state",
    (
        _strong_positive(exchange="HOSE"),
        _state(
            exchange="HOSE",
            day_rvol=1.2,
            rvol15=1.8,
            rvol30=1.8,
            price5_pct=-0.8,
            price15_pct=-1.2,
        ),
    ),
)
def test_close_auction_preserves_existing_continuous_signal(
    tmp_path: Path, continuous_state: CurrentState
) -> None:
    projector = _projector(tmp_path)
    _project(projector, continuous_state, _observed(10, 0))
    before = dict(_signal(projector))
    result = _project(
        projector,
        _state(
            exchange="HOSE",
            minute="14:29",
            day_rvol=1.2,
            rvol15=1.8,
            rvol30=1.8,
            price5_pct=-0.8,
            price15_pct=-1.2,
        ),
        _observed(14, 35),
    )
    assert not result.state_written
    assert not result.event_appended
    assert dict(_signal(projector)) == before
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1


def test_begin_rebuild_expires_old_signal_current_but_keeps_events(
    tmp_path: Path,
) -> None:
    projector = _projector(tmp_path)
    _project(
        projector,
        _strong_positive(
            trading_date="2026-09-24",
            updated_at="2026-09-24T03:00:00+00:00",
        ),
        _observed(10, 0, day=24),
    )
    assert projector.engine_store.signal_row("AAA") is not None
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1

    projector.engine_store.begin_rebuild(DAY)

    assert projector.engine_store.signal_row("AAA") is None
    assert projector.engine_store.connection.execute(
        "SELECT COUNT(*) FROM signal_events"
    ).fetchone()[0] == 1
