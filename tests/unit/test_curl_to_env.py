"""Parser tests for the browser-session capture helper.

A mis-parsed cookie does not fail loudly -- Yahoo answers a bad session with a
302 to the login page, which looks like a working request until something
downstream tries to read league data. These cases pin the parse instead.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "curl_to_env.py"
_spec = importlib.util.spec_from_file_location("curl_to_env", _TOOL)
assert _spec and _spec.loader
curl_to_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(curl_to_env)

CHROME = r"""curl 'https://basketball.fantasysports.yahoo.com/nba/194131/scoreboard?week=3' \
  -H 'accept: text/html' \
  -H 'cookie: B=abc; A1=d=AQABxyz&S=AQAAA; T=z=tok&sk=sig; _cb=analytics' \
  -H 'user-agent: Mozilla/5.0 (Macintosh) Chrome/141.0.0.0' \
  --compressed"""


def test_extracts_url_cookies_and_user_agent() -> None:
    url, cookies, agent = curl_to_env.parse_curl(CHROME)
    assert url.endswith("/scoreboard?week=3")
    assert agent == "Mozilla/5.0 (Macintosh) Chrome/141.0.0.0"
    assert set(cookies) == {"B", "A1", "T", "_cb"}


def test_cookie_values_containing_equals_and_ampersand_survive() -> None:
    """Yahoo's A1 and T cookies embed `k=v&k=v` inside the value itself.

    Splitting on every `=` instead of the first truncates them, which produces
    a syntactically valid cookie that does not authenticate.
    """
    _, cookies, _ = curl_to_env.parse_curl(CHROME)
    assert cookies["A1"] == "d=AQABxyz&S=AQAAA"
    assert cookies["T"] == "z=tok&sk=sig"


def test_short_form_cookie_flag_is_read() -> None:
    """Firefox and Safari emit -b rather than -H 'cookie: ...'."""
    _, cookies, _ = curl_to_env.parse_curl(
        "curl 'https://example.com/x' -b 'A1=one; T=two' -A 'UA/1.0'"
    )
    assert cookies == {"A1": "one", "T": "two"}


def test_minimal_filter_drops_analytics_cookies() -> None:
    _, cookies, _ = curl_to_env.parse_curl(CHROME)
    kept = {k: v for k, v in cookies.items() if k in curl_to_env.LIKELY_AUTH_COOKIES}
    assert "_cb" not in kept
    assert {"B", "A1", "T"} <= set(kept)


def test_rejects_input_that_is_not_curl() -> None:
    with pytest.raises(SystemExit, match="Copy as cURL"):
        curl_to_env.parse_curl("https://basketball.fantasysports.yahoo.com/nba/194131")


def test_rejects_a_request_that_carries_no_session() -> None:
    """A copied request to a static asset host has no Cookie header."""
    with pytest.raises(SystemExit, match="no Cookie header"):
        curl_to_env.parse_curl("curl 'https://s.yimg.com/app.js' -H 'accept: */*'")


# --- verification branches ----------------------------------------------------
# FR-019 requires that a credential failing verification is never stored, so a
# rejection path that silently passes is the one defect that stores a bad
# cookie over a working one. These drive `check` against stubbed responses.


class _Response:
    def __init__(self, status_code: int, text: str = "", location: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.headers = {"location": location} if location else {}
        self.url = "https://basketball.fantasysports.yahoo.com/nba/194131"


def _stub(monkeypatch: pytest.MonkeyPatch, response: object) -> None:
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: response)


def test_check_accepts_a_live_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, _Response(200, "<html>Week 3 scoreboard" + "x" * 3000))
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is True


def test_check_rejects_a_redirect_to_login(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dead session answers with a 302, not an error status.

    Asserts the diagnostic too, not just the rejection: a 302 would be refused
    by the non-200 branch anyway, so only the message proves the redirect was
    recognised as an auth failure rather than a generic bad status.
    """
    _stub(monkeypatch, _Response(302, location="https://login.yahoo.com/?done=..."))
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is False
    out = capsys.readouterr().out
    assert "login" in out and "did not authenticate" in out


def test_check_rejects_any_redirect_even_without_login_in_the_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, _Response(307, location="https://guce.yahoo.com/consent"))
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is False


def test_check_rejects_a_login_page_served_with_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subtlest failure: status says OK, body is a sign-in form."""
    _stub(monkeypatch, _Response(200, "<html><form id='signin'>Please sign in</form>"))
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is False


def test_check_rejects_an_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, _Response(500, "upstream exploded"))
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is False


def test_check_rejects_a_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def boom(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "get", boom)
    assert curl_to_env.check("https://example.com/x", "A1=one", "UA/1.0") is False
