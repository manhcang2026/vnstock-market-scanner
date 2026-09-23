from __future__ import annotations

import pytest

from app.access_control import (
    AuthenticationRequired,
    EntitlementServiceUnavailable,
    SupabaseEntitlementClient,
    extract_bearer_token,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object):
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


def allowed_payload(**overrides):
    payload = {
        "symbol": "HPG",
        "technical_allowed": True,
        "reason": "VIP_ACCESS",
        "plan_code": "FREE",
        "subscription_status": "ACTIVE",
        "effective_full_market_access": True,
        "vip_day_active": True,
        "vip_day_ends_at": "2026-09-30T16:59:59+00:00",
    }
    payload.update(overrides)
    return payload


def scope_payload(**overrides):
    payload = {
        "effective_full_market_access": False,
        "vip_day_active": False,
        "allowed_symbols": ["hpg", "FPT"],
        "plan_code": "PLUS",
        "subscription_status": "ACTIVE",
    }
    payload.update(overrides)
    return payload


def test_entitlement_allowed_consults_authority_each_time():
    session = FakeSession(
        [
            FakeResponse(200, allowed_payload()),
            FakeResponse(200, allowed_payload()),
        ]
    )
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
    )

    first = client.check(token="jwt-token", symbol="HPG")
    second = client.check(token="jwt-token", symbol="HPG")

    assert first.technical_allowed is True
    assert first.reason == "VIP_ACCESS"
    assert second == first
    assert len(session.calls) == 2
    assert session.calls[0]["json"] == {"p_symbol": "HPG"}
    assert session.calls[0]["headers"]["Authorization"] == "Bearer jwt-token"


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, AuthenticationRequired),
        (503, EntitlementServiceUnavailable),
    ],
)
def test_allowed_decision_is_not_reused_after_authority_failure(
    status_code, expected_error
):
    session = FakeSession(
        [
            FakeResponse(200, allowed_payload()),
            FakeResponse(status_code, {"message": "authority rejected request"}),
        ]
    )
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
    )

    assert client.check(token="jwt-token", symbol="HPG").technical_allowed is True
    with pytest.raises(expected_error):
        client.check(token="jwt-token", symbol="HPG")
    assert len(session.calls) == 2


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
    )

    with pytest.raises(AuthenticationRequired):
        client.check(token="expired", symbol="HPG")


def test_scope_resolves_watchlist_in_one_rpc_call():
    session = FakeSession([FakeResponse(200, scope_payload())])
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
    )

    scope = client.scope(token="jwt-token")

    assert scope.allowed_symbols == frozenset({"HPG", "FPT"})
    assert scope.effective_full_market_access is False
    assert len(session.calls) == 1
    assert session.calls[0]["url"].endswith("/rpc/get_my_technical_scope")
    assert session.calls[0]["json"] == {}


def test_entitlement_rejects_non_object_payload():
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([FakeResponse(200, [])]),
    )

    with pytest.raises(EntitlementServiceUnavailable, match="INVALID_ENTITLEMENT_RESPONSE"):
        client.check(token="jwt-token", symbol="HPG")


def test_scope_rejects_non_object_payload():
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([FakeResponse(200, [])]),
    )

    with pytest.raises(EntitlementServiceUnavailable, match="INVALID_SCOPE_RESPONSE"):
        client.scope(token="jwt-token")


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}])
def test_entitlement_rejects_non_boolean_technical_allowed(value):
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession(
            [FakeResponse(200, allowed_payload(technical_allowed=value))]
        ),
    )

    with pytest.raises(EntitlementServiceUnavailable, match="INVALID_ENTITLEMENT_RESPONSE"):
        client.check(token="jwt-token", symbol="HPG")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("effective_full_market_access", "false"),
        ("vip_day_active", "false"),
    ],
)
def test_entitlement_rejects_malformed_optional_security_booleans(field, value):
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([FakeResponse(200, allowed_payload(**{field: value}))]),
    )

    with pytest.raises(EntitlementServiceUnavailable, match="INVALID_ENTITLEMENT_RESPONSE"):
        client.check(token="jwt-token", symbol="HPG")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("effective_full_market_access", "false"),
        ("vip_day_active", "false"),
    ],
)
def test_scope_rejects_malformed_security_booleans(field, value):
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=FakeSession([FakeResponse(200, scope_payload(**{field: value}))]),
    )

    with pytest.raises(EntitlementServiceUnavailable, match="INVALID_SCOPE_RESPONSE"):
        client.scope(token="jwt-token")


def test_scope_consults_authority_again_and_fails_closed():
    session = FakeSession(
        [
            FakeResponse(200, scope_payload()),
            FakeResponse(503, {"message": "temporarily unavailable"}),
        ]
    )
    client = SupabaseEntitlementClient(
        supabase_url="https://example.supabase.co",
        supabase_key="publishable",
        session=session,
    )

    assert client.scope(token="jwt-token").effective_full_market_access is False
    with pytest.raises(EntitlementServiceUnavailable):
        client.scope(token="jwt-token")
    assert len(session.calls) == 2
