"""Re-runs, corrections and replay for capture-sourced weeks (FR-015, FR-016)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from ccsv_rumble import cli
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.cli import _render_archived
from tests.conftest import read_matchup_rows, write_matchups_csv
from tests.integration.test_capture_no_credentials import dry_run, offline  # noqa: F401

SEASON = "2026-27"


def _copy_fixture(tmp_path: Path) -> Path:
    return write_matchups_csv(tmp_path / "matchups.csv", read_matchup_rows())


def test_an_unchanged_capture_creates_no_second_entry(tmp_path: Path, offline) -> None:
    matchups = _copy_fixture(tmp_path)
    assert dry_run(tmp_path, matchups=matchups) == cli.EXIT_OK
    first = (tmp_path / "site" / "week-01.html").read_text(encoding="utf-8")
    assert dry_run(tmp_path, matchups=matchups) == cli.EXIT_OK

    store = ArchiveStore(tmp_path / "archive")
    assert store.list_entry_ids(SEASON, 1) == ["entry-001"]
    assert (tmp_path / "site" / "week-01.html").read_text(encoding="utf-8") == first


def test_replay_needs_no_capture_files(tmp_path: Path, offline) -> None:
    matchups = _copy_fixture(tmp_path)
    assert dry_run(tmp_path, matchups=matchups) == cli.EXIT_OK
    published = (tmp_path / "site" / "week-01.html").read_text(encoding="utf-8")

    matchups.unlink()
    (tmp_path / "rosters.csv").unlink()
    shutil.rmtree(tmp_path / "site")

    # dry-run stamps today's date; replay must be told the same one.
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    replayed = _render_archived(ArchiveStore(tmp_path / "archive"), SEASON, 1, today, None)
    assert replayed.html == published


def test_a_changed_capture_is_archived_as_a_correction(tmp_path: Path, offline) -> None:
    matchups = _copy_fixture(tmp_path)
    assert dry_run(tmp_path, matchups=matchups) == cli.EXIT_OK

    # A stat correction that does not flip any category: t.01 scored 352
    # against t.03's 383, and 360 still loses points.
    rows = read_matchup_rows()
    for row in rows:
        if row["team_id"] == "t.01":
            row["pts"] = "360"
    write_matchups_csv(matchups, rows)
    # A retry, not a new week: the week is published again, so this exercises
    # the publish path re-acquiring an archived week.
    assert dry_run(tmp_path, matchups=matchups) == cli.EXIT_OK

    store = ArchiveStore(tmp_path / "archive")
    assert store.list_entry_ids(SEASON, 1) == ["entry-001", "entry-002"]
    second = json.loads(
        store.paths(SEASON, 1, "entry-002").snapshot.read_text(encoding="utf-8")
    )
    assert second["supersedes"] == "entry-001"
    assert second["category_totals"]["t.01"]["pts"] == 360
