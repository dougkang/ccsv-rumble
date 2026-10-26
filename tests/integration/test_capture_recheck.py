"""The correction window over a capture (research R4, R5)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch.captured import CapturedProvider
from ccsv_rumble.fetch.provider import WeekNotCaptured
from ccsv_rumble.pipeline import capture_source, execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import (
    capture_rows_from_snapshot,
    make_snapshot,
    read_matchup_rows,
    write_matchups_csv,
    write_rosters_csv,
)

SEASON = "2026-27"
SEASON_START = date(2026, 10, 20)


def _week2_rows():
    return capture_rows_from_snapshot(
        make_snapshot(2),
        captured_at="2026-11-02T09:00:00-08:00",
        week_start="2026-10-26",
        week_end="2026-11-01",
    )


def _run(tmp_path: Path, plan: RunPlan, rows, *, roster_size: int = 10):
    matchups = write_matchups_csv(tmp_path / "matchups.csv", rows)
    rosters = write_rosters_csv(tmp_path / "rosters.csv", roster_size=roster_size)
    source = capture_source(CapturedProvider(matchups, rosters, season_start=SEASON_START))
    return execute(
        plan,
        source=source,
        store=ArchiveStore(tmp_path / "archive"),
        anthropic_client=None,
        generated_at="2026-11-03",
        projections_path=tmp_path / "no-projections.csv",
    )


def test_a_recheck_week_absent_from_the_capture_keeps_its_entry(
    tmp_path: Path, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="ccsv_rumble")
    _run(tmp_path, RunPlan(SEASON, (), (), 1), read_matchup_rows())

    # Week 2's capture no longer carries week 1; week 1 is re-checked anyway.
    result = _run(tmp_path, RunPlan(SEASON, (), (1,), 2), _week2_rows())

    assert result.weeks_published == [2]
    assert ArchiveStore(tmp_path / "archive").list_entry_ids(SEASON, 1) == ["entry-001"]
    assert "week 1 not re-checked" in caplog.text


def test_a_gap_week_absent_from_the_capture_fails(tmp_path: Path) -> None:
    """Nothing to fall back on: week 1 was never archived."""
    with pytest.raises(WeekNotCaptured, match="week 1"):
        _run(tmp_path, RunPlan(SEASON, (1,), (), 2), _week2_rows())


@pytest.mark.parametrize(
    "plan",
    [
        pytest.param(RunPlan(SEASON, (), (1,), 2), id="recheck"),
        # A same-week retry: week 1 is both re-checked and the publish target.
        pytest.param(RunPlan(SEASON, (), (1,), 1), id="retry-of-the-same-week"),
    ],
)
def test_changed_rosters_alone_are_not_a_correction(tmp_path: Path, plan: RunPlan) -> None:
    rows = read_matchup_rows() + _week2_rows()
    _run(tmp_path, RunPlan(SEASON, (), (), 1), rows, roster_size=10)

    # Waiver moves: every roster is now a player shorter. Totals unchanged.
    result = _run(tmp_path, plan, rows, roster_size=9)

    store = ArchiveStore(tmp_path / "archive")
    assert store.list_entry_ids(SEASON, 1) == ["entry-001"]
    assert not result.notification.corrections
    assert all(len(slots) == 10 for slots in store.latest_entry(SEASON, 1).rosters.values())
