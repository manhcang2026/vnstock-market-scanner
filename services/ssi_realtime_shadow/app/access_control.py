from __future__ import annotations

import os
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


def _require_payload(payload: object, error_code: str) -> dict:
    if not isinstance(payload, dict):
        raise EntitlementServiceUnavailable(error_code)
    return payload


def _required_bool(payload: dict, key: str, error_code: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise EntitlementServiceUnavailable(error_code)
    return value


def _optional_bool(
    payload: dict,
    key: str,
    error_code: str,
    *,
    default: bool = False,
) -> bool:
    if key not in payload:
        return default
    return _required_bool(payload, key, error_code)


def _required_string(payload: dict, key: str, error_code: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EntitlementServiceUnavailable(error_code)
    return value


def _optional_string(payload: dict, key: str, error_code: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EntitlementServiceUnavailable(error_code)
    return value


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
    def from_payload(cls, payload: object) -> "TechnicalAccessDecision":
        data = _require_payload(payload, "INVALID_ENTITLEMENT_RESPONSE")
        return cls(
            symbol=_required_string(
                data, "symbol", "INVALID_ENTITLEMENT_RESPONSE"
            ).upper(),
            technical_allowed=_required_bool(
                data, "technical_allowed", "INVALID_ENTITLEMENT_RESPONSE"
            ),
            reason=_required_string(
                data, "reason", "INVALID_ENTITLEMENT_RESPONSE"
            ),
            plan_code=_optional_string(
                data, "plan_code", "INVALID_ENTITLEMENT_RESPONSE"
            ),
            subscription_status=_optional_string(
                data, "subscription_status", "INVALID_ENTITLEMENT_RESPONSE"
            ),
            effective_full_market_access=_optional_bool(
                data,
                "effective_full_market_access",
                "INVALID_ENTITLEMENT_RESPONSE",
            ),
            vip_day_active=_optional_bool(
                data, "vip_day_active", "INVALID_ENTITLEMENT_RESPONSE"
            ),
            vip_day_ends_at=_optional_string(
                data, "vip_day_ends_at", "INVALID_ENTITLEMENT_RESPONSE"
            ),
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


@dataclass(frozen=True)
class TechnicalAccessScope:
    effective_full_market_access: bool
    vip_day_active: bool
    allowed_symbols: frozenset[str]
    plan_code: str | None = None
    subscription_status: str | None = None
    vip_day_ends_at: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "TechnicalAccessScope":
        data = _require_payload(payload, "INVALID_SCOPE_RESPONSE")
        symbols = data.get("allowed_symbols")
        if not isinstance(symbols, list) or any(
            not isinstance(symbol, str) or not symbol.strip() for symbol in symbols
        ):
            raise EntitlementServiceUnavailable("INVALID_SCOPE_RESPONSE")
        return cls(
            effective_full_market_access=_required_bool(
                data,
                "effective_full_market_access",
                "INVALID_SCOPE_RESPONSE",
            ),
            vip_day_active=_required_bool(
                data, "vip_day_active", "INVALID_SCOPE_RESPONSE"
            ),
            allowed_symbols=frozenset(
                symbol.strip().upper() for symbol in symbols
            ),
            plan_code=_optional_string(
                data, "plan_code", "INVALID_SCOPE_RESPONSE"
            ),
            subscription_status=_optional_string(
                data, "subscription_status", "INVALID_SCOPE_RESPONSE"
            ),
            vip_day_ends_at=_optional_string(
                data, "vip_day_ends_at", "INVALID_SCOPE_RESPONSE"
            ),
        )


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
        session: requests.Session | None = None,
    ) -> None:
        self.supabase_url = (
            supabase_url or os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL
        ).rstrip("/")
        self.supabase_key = (
            supabase_key or os.getenv("SUPABASE_KEY") or DEFAULT_SUPABASE_KEY
        )
        self.timeout_seconds = float(timeout_seconds)
        self.session = session or requests.Session()

    def check(self, *, token: str | None, symbol: str) -> TechnicalAccessDecision:
        if not token:
            raise AuthenticationRequired("AUTH_REQUIRED")

        normalized_symbol = str(symbol or "").strip().upper()
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

        return TechnicalAccessDecision.from_payload(payload)

    def scope(self, *, token: str | None) -> TechnicalAccessScope:
        """Resolve full-market or active Watchlist scope in one server call."""
        if not token:
            raise AuthenticationRequired("AUTH_REQUIRED")

        endpoint = f"{self.supabase_url}/rest/v1/rpc/get_my_technical_scope"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            response = self.session.post(
                endpoint,
                headers=headers,
                json={},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise EntitlementServiceUnavailable("SUPABASE_UNAVAILABLE") from exc

        if response.status_code in (401, 403):
            raise AuthenticationRequired("INVALID_OR_EXPIRED_SESSION")
        if response.status_code >= 400:
            raise EntitlementServiceUnavailable(
                f"TECHNICAL_SCOPE_RPC_HTTP_{response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EntitlementServiceUnavailable("INVALID_SCOPE_RESPONSE") from exc
        return TechnicalAccessScope.from_payload(payload)
