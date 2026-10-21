"""Credential scrubbing happens on the archive WRITE PATH.

Principle V: "Logs and archived snapshots MUST be scrubbed of credentials before
being written." A per-call-site discipline is one forgotten call away from a
token committed to a public repository, so the store does it itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ccsv_rumble.archive.scrub import REDACTED, scrub
from ccsv_rumble.archive.store import ArchiveStore

SECRETS = [
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "Bearer eyJhbGciOiJIUzI1NiJ9abcdefghij",
]


@pytest.mark.parametrize("secret", SECRETS)
def test_credential_shaped_strings_are_redacted(secret: str) -> None:
    assert secret not in scrub(f"authorization header was {secret} here")


def test_secret_bearing_keys_are_replaced_wholesale() -> None:
    payload = {
        "access_token": "anything-at-all",
        "refresh_token": "also-secret",
        "client_secret": "shh",
        "team_name": "Team 01",
    }
    cleaned = scrub(payload)
    assert cleaned["access_token"] == REDACTED
    assert cleaned["refresh_token"] == REDACTED
    assert cleaned["client_secret"] == REDACTED
    # Non-secret data must survive untouched.
    assert cleaned["team_name"] == "Team 01"


def test_scrubbing_recurses_through_nested_structures() -> None:
    payload = {"a": [{"b": {"api_key": "x"}}, "ghp_abcdefghijklmnopqrstuvwxyz01234"]}
    cleaned = scrub(payload)
    assert cleaned["a"][0]["b"]["api_key"] == REDACTED
    assert REDACTED in cleaned["a"][1]


def test_store_scrubs_without_the_caller_asking(tmp_path: Path, snapshot) -> None:
    """The write path does it. No call site can skip it."""
    store = ArchiveStore(tmp_path)
    paths = store.create_entry("2026-27", 1, "entry-001")
    store.write_raw(paths, {"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"})
    store.write_snapshot(paths, snapshot)

    written = paths.raw.read_text(encoding="utf-8")
    assert "ghp_" not in written
    assert REDACTED in written


def test_no_secret_patterns_anywhere_in_the_archive(tmp_path: Path, snapshot) -> None:
    """The grep from quickstart Scenario 10, as an assertion."""
    store = ArchiveStore(tmp_path)
    paths = store.create_entry("2026-27", 1, "entry-001")
    store.write_raw(paths, {"authorization": SECRETS[0], "nested": {"x": SECRETS[1]}})
    store.write_snapshot(paths, snapshot)

    pattern = re.compile(r"sk-ant-|ghp_|github_pat_")
    for path in tmp_path.rglob("*.json"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path
