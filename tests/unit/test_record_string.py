"""The published record accumulates CATEGORY results, not matchup results."""

from __future__ import annotations

from dataclasses import replace

from ccsv_rumble.models import CategoryLine, Matchup
from ccsv_rumble.rank.score import record_string
from tests.conftest import make_snapshot


def _week(week: int, a: CategoryLine, b: CategoryLine):
    snapshot = make_snapshot(week)
    return replace(
        snapshot,
        matchups=(Matchup(week=week, home_team_id="t.01", away_team_id="t.02"),),
        category_totals={**snapshot.category_totals, "t.01": a, "t.02": b},
    )


# t.01 wins pts, reb, ast, fg%, ft%; loses stl, blk, tpm; ties to -> 5-3-1.
A = CategoryLine(pts=100, reb=50, ast=30, stl=5, blk=3, tpm=10, to=12,
                 fgm=40, fga=80, ftm=18, fta=20)
B = CategoryLine(pts=90, reb=40, ast=20, stl=8, blk=6, tpm=15, to=12,
                 fgm=35, fga=80, ftm=15, fta=20)


def test_one_week_counts_each_category() -> None:
    assert record_string([_week(1, A, B)], "t.01") == "5-3-1"
    assert record_string([_week(1, A, B)], "t.02") == "3-5-1"


def test_weeks_accumulate() -> None:
    history = [_week(1, A, B), _week(2, B, A)]
    assert record_string(history, "t.01") == "8-8-2"


def test_ties_are_shown_even_at_zero() -> None:
    no_tie = replace(A, to=11)
    assert record_string([_week(1, no_tie, B)], "t.01") == "6-3-0"
