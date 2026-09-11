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


@dataclass(frozen=True)
class Settings:
    ssi_consumer_id: str
    ssi_consumer_secret: str
    ssi_auth_type: str
    ssi_url: str
    ssi_stream_url: str
    ssi_channel: str
    database_path: Path
    universe_file: Path | None
    supabase_url: str
    supabase_key: str
    min_universe_size: int
    stale_stream_seconds: int
    commit_every_events: int
    commit_every_seconds: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        universe_raw = _env("UNIVERSE_FILE", "")
        universe_file = Path(universe_raw).expanduser() if universe_raw else None
        db_raw = _env("DATABASE_PATH", str(ROOT / "data" / "ssi_shadow.db"))
        return cls(
            ssi_consumer_id=_env("SSI_CONSUMER_ID", required=True),
            ssi_consumer_secret=_env("SSI_CONSUMER_SECRET", required=True),
            ssi_auth_type=_env("SSI_AUTH_TYPE", "Bearer"),
            ssi_url=_env("SSI_URL", "https://fc-data.ssi.com.vn/"),
            ssi_stream_url=_env("SSI_STREAM_URL", "https://fc-datahub.ssi.com.vn/"),
            ssi_channel=_env("SSI_CHANNEL", "X:ALL"),
            database_path=Path(db_raw).expanduser(),
            universe_file=universe_file,
            supabase_url=_env("SUPABASE_URL", ""),
            supabase_key=_env("SUPABASE_KEY", ""),
            min_universe_size=_env_int("MIN_UNIVERSE_SIZE", 700),
            stale_stream_seconds=_env_int("STALE_STREAM_SECONDS", 180),
            commit_every_events=_env_int("COMMIT_EVERY_EVENTS", 500),
            commit_every_seconds=_env_int("COMMIT_EVERY_SECONDS", 1),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
        )
