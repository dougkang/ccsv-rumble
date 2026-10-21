"""Retry policy: transient faults retry, permission states do not.

The constitution forbids retrying indefinitely, but an equally real failure is
retrying something that cannot succeed. A 403 is a permission state -- it will
not change between attempts within a run -- so retrying it burns token refreshes
and buries Yahoo's actual message under identical log lines.
"""

from __future__ import annotations

import httpx
import pytest

from ccsv_rumble import config
from ccsv_rumble.fetch.provider import ProviderError
from ccsv_rumble.fetch.yahoo import YahooProvider

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def make_provider(handler) -> YahooProvider:
    transport = httpx.MockTransport(handler)
    return YahooProvider(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        league_key="466.l.1",
        client=httpx.Client(transport=transport),
    )


def test_403_is_not_retried(monkeypatch) -> None:
    monkeypatch.setattr(config, "HTTP_PACING_SECONDS", 0.0)
    calls = {"token": 0, "api": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URL):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "t"})
        calls["api"] += 1
        return httpx.Response(
            403,
            json={"error": {"description": "This application is not authorized."}},
        )

    with pytest.raises(ProviderError) as excinfo:
        make_provider(handler).fetch_week("2026-27", 1)

    assert calls["api"] == 1, f"403 was retried {calls['api']} times"
    assert calls["token"] == 1, "a permanent 403 must not trigger token refreshes"

    message = str(excinfo.value).lower()
    assert "fantasy sports" in message, "the message must say what to actually do"
    assert "consent flow" in message, "and that permissions alone are not enough"


def test_401_is_retried_once_with_a_fresh_token(monkeypatch) -> None:
    """An access token really can expire mid-run; that one is worth a retry."""
    monkeypatch.setattr(config, "HTTP_PACING_SECONDS", 0.0)
    calls = {"token": 0, "api": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URL):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"t{calls['token']}"})
        calls["api"] += 1
        if calls["api"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"ok": True})

    result = make_provider(handler).fetch_week("2026-27", 1)

    assert result == {"ok": True}
    assert calls["api"] == 2
    assert calls["token"] == 2, "the retry must use a freshly refreshed token"


def test_500_retries_then_gives_up_bounded(monkeypatch) -> None:
    """Bounded, per the constitution -- never an indefinite loop."""
    monkeypatch.setattr(config, "HTTP_PACING_SECONDS", 0.0)
    calls = {"api": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "t"})
        calls["api"] += 1
        return httpx.Response(503, json={})

    with pytest.raises(ProviderError, match="after 3 attempts"):
        make_provider(handler).fetch_week("2026-27", 1)

    assert calls["api"] == config.HTTP_MAX_RETRIES


def test_404_fails_immediately(monkeypatch) -> None:
    monkeypatch.setattr(config, "HTTP_PACING_SECONDS", 0.0)
    calls = {"api": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "t"})
        calls["api"] += 1
        return httpx.Response(404, json={})

    with pytest.raises(ProviderError):
        make_provider(handler).fetch_week("2026-27", 1)

    assert calls["api"] == 1
