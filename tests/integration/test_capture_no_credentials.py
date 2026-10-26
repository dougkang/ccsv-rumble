"""User Story 1: week 1 publishes from the committed capture, with no Yahoo
credentials and no network (FR-001, FR-004, FR-014)."""

from __future__ import annotations

import logging
import socket
from pathlib import Path

import pytest

from ccsv_rumble import cli
from tests.conftest import MATCHUPS_WEEK1, write_rosters_csv

YAHOO_VARS = ("YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET", "YAHOO_REFRESH_TOKEN", "YAHOO_LEAGUE_KEY")


@pytest.fixture
def offline(monkeypatch):
    for name in YAHOO_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _forbidden(*args, **kwargs):
        raise AssertionError("the capture path opened a network connection")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)


def dry_run(tmp_path: Path, *extra: str, matchups: Path = MATCHUPS_WEEK1) -> int:
    rosters = tmp_path / "rosters.csv"
    if not rosters.exists():
        write_rosters_csv(rosters)
    return cli.main(
        [
            "dry-run", "--week", "1", "--no-article",
            "--matchups", str(matchups),
            "--rosters", str(rosters),
            "--projections", str(tmp_path / "no-projections.csv"),
            "--archive", str(tmp_path / "archive"),
            "--out", str(tmp_path / "site"),
            *extra,
        ]
    )


def test_week1_publishes_from_the_capture_with_no_credentials(
    tmp_path: Path, offline, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="ccsv_rumble")

    assert dry_run(tmp_path) == cli.EXIT_OK

    page = (tmp_path / "site" / "week-01.html").read_text(encoding="utf-8")
    assert page.count("Team ") >= 18
    assert "league source: capture" in caplog.text
    assert "weeks [1]" in caplog.text


def test_the_archived_raw_input_is_the_weeks_rows_verbatim(tmp_path: Path, offline) -> None:
    assert dry_run(tmp_path) == cli.EXIT_OK

    entry = tmp_path / "archive" / "2026-27" / "week-01" / "entry-001"
    assert (entry / "raw-matchups.csv").read_text(encoding="utf-8") == MATCHUPS_WEEK1.read_text(
        encoding="utf-8"
    )
    assert not (entry / "raw-yahoo.json").exists()
    assert '"raw_source": "matchups.csv"' in (entry / "snapshot.json").read_text(encoding="utf-8")
