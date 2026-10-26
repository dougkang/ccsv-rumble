"""`dry-run --allow-in-progress`: preview a week that has not ended.

Preview only. A published in-progress week would be superseded by the final
capture as a correction, and corrections are never republished, so the partial
page would stay up for good. The flag therefore never touches the real archive
and is not accepted by `run` at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble import cli
from tests.conftest import read_matchup_rows, write_matchups_csv
from tests.integration.test_capture_no_credentials import dry_run, offline  # noqa: F401

MID_WEEK = "2026-10-24T09:00:00-07:00"


def _mid_week(tmp_path: Path) -> Path:
    return write_matchups_csv(tmp_path / "matchups.csv", read_matchup_rows(), captured_at=MID_WEEK)


def test_a_mid_week_snapshot_previews_with_the_flag(tmp_path: Path, offline, caplog) -> None:
    code = dry_run(tmp_path, "--allow-in-progress", matchups=_mid_week(tmp_path))

    assert code == cli.EXIT_OK
    assert (tmp_path / "site" / "week-01.html").is_file()
    assert "IN PROGRESS" in caplog.text
    assert not (tmp_path / "archive").exists(), "a preview must not write the real archive"


def test_without_the_flag_it_is_still_refused(tmp_path: Path, offline, caplog) -> None:
    assert dry_run(tmp_path, matchups=_mid_week(tmp_path)) == cli.EXIT_ACQUIRE
    assert "before it ended" in caplog.text


def test_the_flag_still_applies_every_other_check(tmp_path: Path, offline, caplog) -> None:
    rows = [r for r in read_matchup_rows() if r["team_id"] != "t.07"]
    matchups = write_matchups_csv(tmp_path / "matchups.csv", rows, captured_at=MID_WEEK)
    assert dry_run(tmp_path, "--allow-in-progress", matchups=matchups) == cli.EXIT_ACQUIRE
    assert "t.07" in caplog.text


def test_the_flag_needs_a_named_week(tmp_path: Path, offline) -> None:
    code = cli.main(["dry-run", "--allow-in-progress", "--archive", str(tmp_path / "a")])
    assert code == cli.EXIT_ACQUIRE


def test_run_does_not_accept_the_flag() -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--week", "1", "--allow-in-progress"])
