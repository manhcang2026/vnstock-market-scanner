from __future__ import annotations

from app.storage_benchmark import run_benchmark


def test_storage_benchmark_uses_real_schemas_and_returns_projections() -> None:
    result = run_benchmark(1_000)
    measurements = result["measurements"]
    assert set(measurements) == {"daily", "minute_1m", "archive_5m"}
    for measurement in measurements.values():
        assert measurement["rows"] == 1_000
        assert measurement["page_size"] > 0
        assert measurement["page_count"] > 0
        assert measurement["incremental_bytes_per_row"] > 0
        assert measurement["wal_bytes"] == 0
    assert result["projections"]["minute_15_sessions"]["rows"] == 3_240_000
    assert result["projections"]["archive_2_years"]["rows"] == 21_600_000
