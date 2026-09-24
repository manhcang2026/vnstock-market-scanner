from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean environment variable {name}: {raw!r}")


def _service_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else ROOT / path


def _symbol_list(raw: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()
        )
    )


@dataclass(frozen=True)
class Settings:
    ssi_consumer_id: str
    ssi_consumer_secret: str
    ssi_auth_type: str
    ssi_url: str
    ssi_stream_url: str
    ssi_channel: str
    database_path: Path
    canonical_market_dir: Path
    universe_file: Path | None
    supabase_url: str
    supabase_key: str
    min_universe_size: int
    stale_stream_seconds: int
    commit_every_events: int
    commit_every_seconds: int
    log_level: str
    volume_engine_enabled: bool
    live_state_enabled: bool
    volume_baseline_path: Path
    market_v2_database_path: Path
    ssi_history_path: Path
    volume_shadow_symbols: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        universe_raw = _env("UNIVERSE_FILE", "")
        universe_file = Path(universe_raw).expanduser() if universe_raw else None
        db_raw = _env("DATABASE_PATH", required=True)
        baseline_raw = _env("VOLUME_BASELINE_PATH", required=True)
        market_raw = _env("MARKET_V2_DATABASE_PATH", required=True)
        history_raw = _env("SSI_HISTORY_PATH", required=True)
        volume_engine_enabled = _env_bool("VOLUME_ENGINE_ENABLED", False)
        live_state_enabled = _env_bool("LIVE_STATE_ENABLED", False)
        if live_state_enabled and not volume_engine_enabled:
            raise RuntimeError(
                "LIVE_STATE_ENABLED=true requires VOLUME_ENGINE_ENABLED=true"
            )
        return cls(
            ssi_consumer_id=_env("SSI_CONSUMER_ID", required=True),
            ssi_consumer_secret=_env("SSI_CONSUMER_SECRET", required=True),
            ssi_auth_type=_env("SSI_AUTH_TYPE", "Bearer"),
            ssi_url=_env("SSI_URL", "https://fc-data.ssi.com.vn/"),
            ssi_stream_url=_env("SSI_STREAM_URL", "https://fc-datahub.ssi.com.vn/"),
            ssi_channel=_env("SSI_CHANNEL", "X:ALL"),
            database_path=Path(db_raw).expanduser(),
            canonical_market_dir=_service_path(
                _env("CANONICAL_MARKET_DIR", "data")
            ),
            universe_file=universe_file,
            supabase_url=_env("SUPABASE_URL", ""),
            supabase_key=_env("SUPABASE_KEY", ""),
            min_universe_size=_env_int("MIN_UNIVERSE_SIZE", 700),
            stale_stream_seconds=_env_int("STALE_STREAM_SECONDS", 180),
            commit_every_events=_env_int("COMMIT_EVERY_EVENTS", 500),
            commit_every_seconds=_env_int("COMMIT_EVERY_SECONDS", 1),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            volume_engine_enabled=volume_engine_enabled,
            live_state_enabled=live_state_enabled,
            volume_baseline_path=_service_path(
                baseline_raw
            ),
            market_v2_database_path=_service_path(
                market_raw
            ),
            ssi_history_path=_service_path(
                history_raw
            ),
            volume_shadow_symbols=_symbol_list(
                _env("VOLUME_SHADOW_SYMBOLS", "HPG,SHS,VGI")
            ),
        )
