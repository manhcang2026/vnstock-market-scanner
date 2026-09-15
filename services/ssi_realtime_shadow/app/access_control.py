from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass

import requests


# Publishable project identity. This is intentionally not a service-role secret.
# Environment variables override these defaults when available.
DEFAULT_SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co"
DEFAULT_SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw"


class AuthenticationRequired(Exception):
    """Missing, invalid or expired end-user Supabase session."""


class EntitlementServiceUnavailable(Exception):
    """The entitlement authority could not be reached or returned invalid data."""


@dataclass(frozen=True)
class TechnicalAccessDecision:
    symbol: str
    technical_allowed: bool
    reason: str
    plan_code: str | None = None
    subscription_status: str | None = None
    effective_full_market_access: bool = False
    vip_day_active: bool = False
    vip_day_ends_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "TechnicalAccessDecision":
        return cls(
            symbol=str(payload.get("symbol") or "").upper(),
            technical_allowed=bool(payload.get("technical_allowed")),
            reason=str(payload.get("reason") or "UNKNOWN"),
            plan_code=payload.get("plan_code"),
            subscription_status=payload.get("subscription_status"),
            effective_full_market_access=bool(
                payload.get("effective_full_market_access", False)
            ),
            vip_day_active=bool(payload.get("vip_day_active", False)),
            vip_day_ends_at=payload.get("vip_day_ends_at"),
        )

    def to_public_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "technical_allowed": self.technical_allowed,
            "reason": self.reason,
            "plan_code": self.plan_code,
            "subscription_status": self.subscription_status,
            "effective_full_market_access": self.effective_full_market_access,
            "vip_day_active": self.vip_day_active,
            "vip_day_ends_at": self.vip_day_ends_at,
        }


def extract_bearer_token(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


class SupabaseEntitlementClient:
    """Server-side entitlement check using the authenticated user's JWT.

    Security properties:
    - Uses only the public/publishable Supabase key.
    - User identity comes from the end-user Bearer token.
    - PostgreSQL SECURITY DEFINER RPC is the authorization source of truth.
    - No service-role key is required or accepted here.
    - Technical access fails closed if Supabase is unavailable.
    """

    def __init__(
        self,
        *,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        timeout_seconds: float = 2.5,
        cache_ttl_seconds: float = 10.0,
        cache_max_entries: int = 2048,
        session: requests.Session | None = None,
    ) -> None:
        self.supabase_url = (
            supabase_url or os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL
        ).rstrip("/")
        self.supabase_key = (
            supabase_key or os.getenv("SUPABASE_KEY") or DEFAULT_SUPABASE_KEY
        )
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self.cache_max_entries = max(32, int(cache_max_entries))
        self.session = session or requests.Session()
        self._cache: dict[str, tuple[float, TechnicalAccessDecision]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _cache_key(token: str, symbol: str) -> str:
        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{token_digest}:{symbol.upper()}"

    def _get_cached(self, key: str) -> TechnicalAccessDecision | None:
        if self.cache_ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires_at, decision = item
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            return decision

    def _put_cached(self, key: str, decision: TechnicalAccessDecision) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        now = time.monotonic()
        with self._lock:
            if len(self._cache) >= self.cache_max_entries:
                expired = [
                    cache_key
                    for cache_key, (expires_at, _) in self._cache.items()
                    if expires_at <= now
                ]
                for cache_key in expired:
                    self._cache.pop(cache_key, None)
                if len(self._cache) >= self.cache_max_entries:
                    # Small bounded cache: simple full reset is safer than unbounded growth.
                    self._cache.clear()
            self._cache[key] = (now + self.cache_ttl_seconds, decision)

    def check(self, *, token: str | None, symbol: str) -> TechnicalAccessDecision:
        if not token:
            raise AuthenticationRequired("AUTH_REQUIRED")

        normalized_symbol = str(symbol or "").strip().upper()
        key = self._cache_key(token, normalized_symbol)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        endpoint = f"{self.supabase_url}/rest/v1/rpc/get_my_technical_access"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                endpoint,
                headers=headers,
                json={"p_symbol": normalized_symbol},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise EntitlementServiceUnavailable("SUPABASE_UNAVAILABLE") from exc

        if response.status_code in (401, 403):
            raise AuthenticationRequired("INVALID_OR_EXPIRED_SESSION")

        if response.status_code >= 400:
            raise EntitlementServiceUnavailable(
                f"ENTITLEMENT_RPC_HTTP_{response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EntitlementServiceUnavailable("INVALID_ENTITLEMENT_RESPONSE") from exc

        if not isinstance(payload, dict) or "technical_allowed" not in payload:
            raise EntitlementServiceUnavailable("INVALID_ENTITLEMENT_RESPONSE")

        decision = TechnicalAccessDecision.from_payload(payload)
        self._put_cached(key, decision)
        return decision
