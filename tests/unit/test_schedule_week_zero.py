"""`build_plan` must be able to target week 0, or the page is unreachable.

Before this, `current = completed if completed >= 1 else 1` meant the scheduled
job could never produce week 0 -- only an explicit `--week 0` reached it, so
SC-001 ("on the first run after the draft completes, the page shows all 18
teams") could not hold through the weekly run.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.schedule import build_plan, week_for_date

SEASON = "2026-27"
SEASON_START = date(2026, 10, 20)


def _plan(tmp_path: Path, when: date, **kwargs):
    return build_plan(
        ArchiveStore(tmp_path / "archive"),
        SEASON,
        SEASON_START,
        clock=datetime(when.year, when.month, when.day, 9, 0, tzinfo=UTC),
        **kwargs,
    )


def test_before_any_week_completes_the_plan_targets_week_zero(tmp_path: Path) -> None:
    """The post-draft projection page is the right target before any results."""
    plan = _plan(tmp_path, date(2026, 10, 22))
    assert plan.current_week == 0
    assert plan.weeks_to_publish == (0,)


def test_on_the_season_start_date_the_plan_targets_week_zero(tmp_path: Path) -> None:
    plan = _plan(tmp_path, SEASON_START)
    assert plan.current_week == 0


def test_before_the_season_starts_the_plan_targets_week_zero(tmp_path: Path) -> None:
    plan = _plan(tmp_path, date(2026, 10, 10))
    assert week_for_date(SEASON_START, date(2026, 10, 10)) == 0
    assert plan.current_week == 0


def test_once_a_week_completes_the_plan_targets_that_week(tmp_path: Path) -> None:
    """In-season behaviour is unchanged -- the fix must not shift it."""
    plan = _plan(tmp_path, date(2026, 10, 28))  # week 1 has finished
    assert plan.current_week == 1
    assert 0 not in plan.weeks_to_publish


def test_mid_season_is_unchanged(tmp_path: Path) -> None:
    plan = _plan(tmp_path, date(2026, 12, 1))
    assert plan.current_week >= 5
    assert 0 not in plan.weeks_to_publish


def test_an_explicit_week_still_wins(tmp_path: Path) -> None:
    """`--week` is the deliberate escape hatch and must keep bypassing this."""
    plan = _plan(tmp_path, date(2026, 12, 1), explicit_week=3)
    assert plan.current_week == 3


def test_week_zero_is_not_treated_as_a_gap(tmp_path: Path) -> None:
    """Gap detection starts at week 1; week 0 has no results to backfill."""
    plan = _plan(tmp_path, date(2026, 11, 10))
    assert 0 not in plan.gap_weeks
