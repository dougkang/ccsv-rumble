"""User Story 3: `--source yahoo` still works; the default never touches it."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble import cli
from tests.conftest import MATCHUPS_WEEK1, write_rosters_csv
from tests.integration.conftest import FakeProvider
from tests.integration.test_capture_no_credentials import YAHOO_VARS


def _dry_run(tmp_path: Path, *extra: str, week: str = "1") -> int:
    write_rosters_csv(tmp_path / "rosters.csv")
    return cli.main(
        [
            "dry-run", "--week", week, "--no-article",
            "--matchups", str(MATCHUPS_WEEK1),
            "--rosters", str(tmp_path / "rosters.csv"),
            "--projections", str(tmp_path / "no-projections.csv"),
            "--archive", str(tmp_path / "archive"),
            "--out", str(tmp_path / "site"),
            *extra,
        ]
    )


@pytest.fixture
def no_yahoo_env(monkeypatch):
    for name in YAHOO_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "_notifier", lambda: type("N", (), {"send": lambda s, n: None})())


def test_yahoo_without_credentials_fails_as_it_always_has(
    tmp_path: Path, no_yahoo_env, caplog
) -> None:
    assert _dry_run(tmp_path, "--source", "yahoo") == cli.EXIT_ACQUIRE
    assert "missing required environment variables" in caplog.text


def test_yahoo_with_a_provider_publishes_through_the_yahoo_builder(
    tmp_path: Path, no_yahoo_env, monkeypatch, fake_snapshot_builder
) -> None:
    monkeypatch.setattr(cli, "_provider_from_env", FakeProvider)
    assert _dry_run(tmp_path, "--source", "yahoo") == cli.EXIT_OK
    entry = tmp_path / "archive" / "2026-27" / "week-01" / "entry-001"
    assert (entry / "raw-yahoo.json").is_file()
    assert not (entry / "raw-matchups.csv").exists()


def test_the_default_source_never_builds_the_yahoo_provider(
    tmp_path: Path, no_yahoo_env, monkeypatch
) -> None:
    def _forbidden():
        raise AssertionError("the default source reached _provider_from_env")

    monkeypatch.setattr(cli, "_provider_from_env", _forbidden)
    assert _dry_run(tmp_path) == cli.EXIT_OK


def test_week_zero_builds_no_source(tmp_path: Path, no_yahoo_env, monkeypatch) -> None:
    def _forbidden(args):
        raise AssertionError("week 0 constructed a league source")

    monkeypatch.setattr(cli, "_league_source", _forbidden)
    # Projections are needed to rank week 0.
    code = _dry_run(
        tmp_path, "--projections", "tests/fixtures/projections-valid.csv", week="0"
    )
    assert code == cli.EXIT_OK
