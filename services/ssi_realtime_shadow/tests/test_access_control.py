from __future__ import annotations

import pytest

from app.access_control import (
    AuthenticationRequired,
    SupabaseEntitlementClient,
    extract_bearer_token,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return self.responses.pop(0)


def test_extract_bearer_token():
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("") is None
    assert extract_bearer_token("Basic abc") is None
    assert extract_bearer_token("Bearer abc.def") == "abc.def"
    assert extract_bearer_token("bearer   token123") == "token123"


def test_entitlement_allowed_and_cached():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "symbol": "HPG",
                    "technical_allowed": True,
                    "reason": "VIP_ACCESS",
                    "plan_code": "FREE",
                    "subscription_status": "ACTIVE",
                    "effective_full_market_access": True,
                    "vip_day_active": True,
                    "vip_day_ends_at": "2026-09-30T16:59:59+00:00",
                },
            )
        ]
    )
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
        cache_ttl_seconds=30,
    )

    first = client.check(token="jwt-token", symbol="HPG")
    second = client.check(token="jwt-token", symbol="HPG")

    assert first.technical_allowed is True
    assert first.reason == "VIP_ACCESS"
    assert second == first
    assert len(session.calls) == 1
    assert session.calls[0]["json"] == {"p_symbol": "HPG"}
    assert session.calls[0]["headers"]["Authorization"] == "Bearer jwt-token"


def test_entitlement_denied_is_a_valid_decision():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "symbol": "VIX",
                    "technical_allowed": False,
                    "reason": "OUTSIDE_ENTITLEMENT",
                    "plan_code": "FREE",
                    "subscription_status": "ACTIVE",
                    "effective_full_market_access": False,
                    "vip_day_active": False,
                    "vip_day_ends_at": None,
                },
            )
        ]
    )
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
        cache_ttl_seconds=0,
    )

    decision = client.check(token="jwt-token", symbol="VIX")

    assert decision.technical_allowed is False
    assert decision.reason == "OUTSIDE_ENTITLEMENT"


def test_missing_token_fails_closed():
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([]),
    )

    with pytest.raises(AuthenticationRequired):
        client.check(token=None, symbol="HPG")


def test_invalid_or_expired_jwt_is_authentication_error():
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([FakeResponse(401, {"message": "JWT expired"})]),
        cache_ttl_seconds=0,
    )

    with pytest.raises(AuthenticationRequired):
        client.check(token="expired", symbol="HPG")
