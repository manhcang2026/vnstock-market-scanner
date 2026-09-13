from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.universe import load_exchange_map


class MetadataResponse:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[Any]:
        return self.rows


def test_load_exchange_map_from_mock_supabase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> MetadataResponse:
        captured.update(url=url, **kwargs)
        return MetadataResponse(
            [
                {"symbol": "HPG", "exchange": "HSX"},
                {"symbol": "SHS", "exchange": "HNX"},
                {"symbol": "BSR", "exchange": "UPCO"},
            ]
        )

    monkeypatch.setattr("app.universe.requests.get", fake_get)
    settings = SimpleNamespace(
        supabase_url="https://example.supabase.co/",
        supabase_key="test-public-key",
    )

    assert load_exchange_map(settings) == {
        "HPG": "HOSE",
        "SHS": "HNX",
        "BSR": "UPCOM",
    }
    assert captured["url"] == (
        "https://example.supabase.co/rest/v1/stock_metadata"
    )
    assert captured["params"] == {
        "select": "symbol,exchange",
        "order": "symbol.asc",
        "limit": "2000",
    }
    assert captured["timeout"] == 30


def test_load_exchange_map_ignores_and_reports_invalid_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_get(url: str, **kwargs: Any) -> MetadataResponse:
        return MetadataResponse(
            [
                {"symbol": "HPG", "exchange": None},
                {"symbol": "SSI", "exchange": "UNKNOWN"},
                {"symbol": "VIX", "exchange": "HOSE"},
                {"symbol": "?", "exchange": "HNX"},
            ]
        )

    monkeypatch.setattr("app.universe.requests.get", fake_get)
    settings = SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_key="secret-not-for-logs",
    )

    assert load_exchange_map(settings) == {"VIX": "HOSE"}
    assert "invalid exchange=None" in caplog.text
    assert "invalid exchange='UNKNOWN'" in caplog.text
    assert "invalid symbol='?'" in caplog.text
    assert "secret-not-for-logs" not in caplog.text
