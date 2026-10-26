"""The league's real week shape: a short Tue-Sun week 1, then Mon-Sun weeks.

The old formula counted seven-day weeks from opening day, putting every boundary
on a Monday. The Tuesday cron landed on the right week only by coincidence; a
Monday run targeted week 0 the day after week 1 ended (research R10).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.schedule import build_plan, week_for_date, week_range

SEASON = "2026-27"
SEASON_START = date(2026, 10, 20)  # a Tuesday


@pytest.mark.parametrize("day", range(20, 26))
def test_week_one_runs_tuesday_through_sunday(day: int) -> None:
    assert week_for_date(SEASON_START, date(2026, 10, day)) == 1


@pytest.mark.parametrize("offset", range(7))
def test_week_two_runs_monday_through_sunday(offset: int) -> None:
    assert week_for_date(SEASON_START, date(2026, 10, 26) + timedelta(days=offset)) == 2


def test_week_three_starts_on_the_following_monday() -> None:
    assert week_for_date(SEASON_START, date(2026, 11, 2)) == 3


def test_before_opening_day_is_week_zero() -> None:
    assert week_for_date(SEASON_START, date(2026, 10, 19)) == 0


def test_week_range_is_the_inverse() -> None:
    assert week_range(SEASON_START, 1) == (date(2026, 10, 20), date(2026, 10, 25))
    assert week_range(SEASON_START, 2) == (date(2026, 10, 26), date(2026, 11, 1))
    for week in range(1, 25):
        start, end = week_range(SEASON_START, week)
        assert week_for_date(SEASON_START, start) == week
        assert week_for_date(SEASON_START, end) == week
        assert end.weekday() == 6  # every week ends on a Sunday


def test_season_starting_on_a_monday_has_a_full_week_one() -> None:
    monday = date(2026, 10, 19)
    assert week_range(monday, 1) == (monday, date(2026, 10, 25))


def test_monday_after_week_one_targets_week_one(tmp_path: Path) -> None:
    """The bug: 2026-10-26 used to plan week 0."""
    plan = build_plan(
        ArchiveStore(tmp_path / "archive"),
        SEASON,
        SEASON_START,
        # 09:00 PT on Monday 2026-10-26.
        clock=datetime(2026, 10, 26, 16, 0, tzinfo=UTC),
    )
    assert plan.current_week == 1
