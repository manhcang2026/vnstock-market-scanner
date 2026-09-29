"""Minimal environment configuration for canonical maintenance jobs."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalMetadataConfig:
    supabase_url: str
    supabase_key: str

    @classmethod
    def from_env(cls) -> "CanonicalMetadataConfig":
        return cls(
            supabase_url=_required_env("SUPABASE_URL"),
            supabase_key=_required_env("SUPABASE_KEY"),
        )


@dataclass(frozen=True, slots=True)
class CanonicalRestConfig:
    ssi_consumer_id: str
    ssi_consumer_secret: str
    ssi_auth_type: str
    ssi_url: str

    @classmethod
    def from_env(cls) -> "CanonicalRestConfig":
        return cls(
            ssi_consumer_id=_required_env("SSI_CONSUMER_ID"),
            ssi_consumer_secret=_required_env("SSI_CONSUMER_SECRET"),
            ssi_auth_type=str(os.getenv("SSI_AUTH_TYPE") or "Bearer").strip(),
            ssi_url=str(
                os.getenv("SSI_URL") or "https://fc-data.ssi.com.vn/"
            ).strip(),
        )
