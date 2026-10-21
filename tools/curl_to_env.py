#!/usr/bin/env python3
"""Turn a browser's "Copy as cURL" into a stored web-session credential.

Yahoo's auth cookies are HttpOnly, so no console snippet can read them. The
reliable capture is DevTools -> Network -> right-click the league request ->
Copy as cURL, which includes the full Cookie header.

    pbpaste | uv run python tools/curl_to_env.py --check
    uv run python tools/curl_to_env.py --from-file capture.txt --minimal

Writes `credentials.local.sh` (matched by the repo's `credentials*.sh` ignore
rule, mode 600). Cookie VALUES are never printed -- only names and lengths --
so this is safe to run with the output visible.

Per constitution Principle V, cookies are a legitimate runtime secret supplied
by the environment or a secret store; they must never enter the repository,
archived data, or generated HTML.
"""

from __future__ import annotations

import argparse
import os
import shlex
import stat
import sys
from pathlib import Path

#: Yahoo session cookies, best-effort. Used only by --minimal, which is an
#: experiment: a narrower secret is better, but a cookie set that is too narrow
#: fails as a 302 to the login page rather than loudly, so --check it.
LIKELY_AUTH_COOKIES = frozenset(
    {"T", "Y", "SSID", "A1", "A1S", "A3", "B", "F", "GUC", "PH", "SID", "TBLA_CA"}
)

OUTPUT = Path("credentials.local.sh")


def parse_curl(text: str) -> tuple[str, dict[str, str], str]:
    """Extract (url, cookies, user_agent) from a Copy-as-cURL command."""
    cleaned = text.replace("\\\n", " ").replace("^\n", " ").strip()
    if not cleaned.startswith("curl"):
        raise SystemExit(
            "input does not look like a cURL command. Use DevTools -> Network "
            "-> right-click the request -> Copy -> Copy as cURL."
        )

    try:
        tokens = shlex.split(cleaned)
    except ValueError as exc:
        raise SystemExit(f"could not parse the cURL command: {exc}") from exc

    url = ""
    cookie_header = ""
    user_agent = ""

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-H", "--header"} and index + 1 < len(tokens):
            header = tokens[index + 1]
            name, _, value = header.partition(":")
            key = name.strip().lower()
            if key == "cookie":
                cookie_header = value.strip()
            elif key == "user-agent":
                user_agent = value.strip()
            index += 2
            continue
        if token in {"-b", "--cookie"} and index + 1 < len(tokens):
            cookie_header = tokens[index + 1]
            index += 2
            continue
        if token in {"-A", "--user-agent"} and index + 1 < len(tokens):
            user_agent = tokens[index + 1]
            index += 2
            continue
        if not token.startswith("-") and not url:
            url = token
        index += 1

    cookies: dict[str, str] = {}
    for pair in cookie_header.split(";"):
        name, sep, value = pair.strip().partition("=")
        if sep and name.strip():
            cookies[name.strip()] = value.strip()

    if not cookies:
        raise SystemExit(
            "no Cookie header found. Copy a request made to "
            "basketball.fantasysports.yahoo.com while logged in -- a request to "
            "a static asset host will not carry the session."
        )
    return url, cookies, user_agent


def check(url: str, cookie_header: str, user_agent: str) -> bool:
    """Confirm the captured session authenticates from outside the browser.

    This is the gate for the whole approach. A session that only works inside
    the browser means the cookie is not sufficient and the design needs a
    different surface.
    """
    try:
        import httpx
    except ImportError:
        print("  --check needs httpx; run via `uv run`", file=sys.stderr)
        return False

    headers = {"Cookie": cookie_header}
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        response = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        print(f"  check FAILED: transport error: {exc}")
        return False

    # A bounced session is a redirect to login, not an error status -- which is
    # exactly how this fails silently if nobody looks for it.
    location = response.headers.get("location", "")
    if response.status_code in {301, 302, 303, 307, 308}:
        destination = "login" if "login" in location.lower() else location[:80]
        print(f"  check FAILED: {response.status_code} redirect to {destination}")
        print("  The cookie did not authenticate. Re-copy from a logged-in request.")
        return False
    if response.status_code != 200:
        print(f"  check FAILED: {response.status_code}")
        return False
    if "login" in str(response.url).lower() or "signin" in response.text[:2000].lower():
        print("  check FAILED: served a login page with status 200")
        return False

    print(f"  check OK: {response.status_code}, {len(response.text):,} bytes")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", type=Path, help="read the cURL from a file")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="keep only likely auth cookies, for a smaller stored secret",
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the session works outside the browser"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    raw = args.from_file.read_text() if args.from_file else sys.stdin.read()
    url, cookies, user_agent = parse_curl(raw)

    kept = cookies
    if args.minimal:
        kept = {k: v for k, v in cookies.items() if k in LIKELY_AUTH_COOKIES}
        if not kept:
            raise SystemExit(
                "--minimal matched no known auth cookie names. Yahoo may have "
                "changed them; re-run without --minimal."
            )

    cookie_header = "; ".join(f"{k}={v}" for k, v in kept.items())

    print(f"url:        {url[:100]}")
    print(f"cookies:    {len(kept)} kept of {len(cookies)} captured")
    print(f"  names:    {', '.join(sorted(kept))}")
    print(f"  size:     {len(cookie_header):,} bytes (values not shown)")
    print(f"user-agent: {'captured' if user_agent else 'MISSING -- re-copy the request'}")

    if args.check and not check(url, cookie_header, user_agent):
        return 1

    body = (
        "# Yahoo web session, captured from a browser. DO NOT COMMIT.\n"
        "# Expires on a timescale of days-to-weeks; re-mint by re-copying a\n"
        "# logged-in request as cURL and re-running tools/curl_to_env.py.\n"
        f"export YAHOO_WEB_COOKIE={shlex.quote(cookie_header)}\n"
        f"export YAHOO_WEB_UA={shlex.quote(user_agent)}\n"
    )
    args.output.write_text(body)
    os.chmod(args.output, stat.S_IRUSR | stat.S_IWUSR)
    print(f"\nwrote {args.output} (mode 600) -- `source {args.output}` before a run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
