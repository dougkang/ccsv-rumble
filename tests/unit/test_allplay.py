"""All-play math, anchored to the worked example in docs/rankings-algorithm-v1.md s2.

That example has hand-computed expected values. If this test and the doc ever
disagree, one of them is wrong -- fix both together.
"""

from __future__ import annotations

import pytest

from ccsv_rumble.models import CategoryLine
from ccsv_rumble.rank import allplay

# The doc's 4-team, 3-category table. TO is inverted (lower wins).
THREE_CATS = ("pts", "reb", "to")

WORKED_EXAMPLE = {
    "A": CategoryLine(pts=500, reb=200, to=60),
    "B": CategoryLine(pts=480, reb=190, to=50),
    "C": CategoryLine(pts=520, reb=150, to=70),
    "D": CategoryLine(pts=400, reb=210, to=45),
}


@pytest.mark.parametrize(
    ("team", "expected"),
    [("A", 5 / 9), ("B", 4 / 9), ("C", 3 / 9), ("D", 6 / 9)],
)
def test_caw_matches_the_documented_worked_example(team: str, expected: float) -> None:
    result = allplay.caw(WORKED_EXAMPLE, THREE_CATS)
    assert result[team] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("team", "expected"),
    [("A", 2 / 3), ("B", 1 / 3), ("C", 0.0), ("D", 1.0)],
)
def test_emw_matches_the_documented_worked_example(team: str, expected: float) -> None:
    result = allplay.emw(WORKED_EXAMPLE, THREE_CATS)
    assert result[team] == pytest.approx(expected)


def test_caw_totals_conserve() -> None:
    """Every comparison awards exactly 1.0 across the two sides, so the mean is .5."""
    result = allplay.caw(WORKED_EXAMPLE, THREE_CATS)
    assert sum(result.values()) == pytest.approx(len(WORKED_EXAMPLE) / 2)


def test_emw_totals_conserve() -> None:
    result = allplay.emw(WORKED_EXAMPLE, THREE_CATS)
    assert sum(result.values()) == pytest.approx(len(WORKED_EXAMPLE) / 2)


def test_c_is_best_at_points_and_still_last_overall() -> None:
    """The doc calls this out: leading one category does not carry a team."""
    emw = allplay.emw(WORKED_EXAMPLE, THREE_CATS)
    assert WORKED_EXAMPLE["C"].pts == max(line.pts for line in WORKED_EXAMPLE.values())
    assert emw["C"] == min(emw.values())


# --- Category comparison rules ------------------------------------------------


def test_turnovers_are_inverted() -> None:
    fewer = CategoryLine(to=40)
    more = CategoryLine(to=90)
    assert allplay.compare_category(fewer, more, "to") == 1.0
    assert allplay.compare_category(more, fewer, "to") == 0.0


def test_counting_category_tie_splits_the_point() -> None:
    a = CategoryLine(pts=500)
    b = CategoryLine(pts=500)
    assert allplay.compare_category(a, b, "pts") == 0.5


def test_ratio_category_compares_the_rate_not_the_makes() -> None:
    """Fewer makes on far fewer attempts still wins the percentage."""
    efficient = CategoryLine(fgm=50, fga=100)   # .500
    voluminous = CategoryLine(fgm=90, fga=200)  # .450
    assert allplay.compare_category(efficient, voluminous, "fg_pct") == 1.0


def test_zero_attempts_loses_to_any_team_with_attempts() -> None:
    none = CategoryLine(ftm=0, fta=0)
    some = CategoryLine(ftm=1, fta=10)  # .100 -- still beats "did not attempt"
    assert allplay.compare_category(none, some, "ft_pct") == 0.0
    assert allplay.compare_category(some, none, "ft_pct") == 1.0


def test_both_zero_attempts_is_a_tie() -> None:
    a = CategoryLine(ftm=0, fta=0)
    b = CategoryLine(ftm=0, fta=0)
    assert allplay.compare_category(a, b, "ft_pct") == 0.5


def test_a_perfect_split_of_nine_categories_cannot_happen_but_ties_can() -> None:
    """4.5-4.5 across nine categories is a matchup tie, not a win."""
    a = CategoryLine(pts=100, reb=100, ast=100, stl=1, blk=1, tpm=1, to=5,
                     fgm=5, fga=10, ftm=5, fta=10)
    assert allplay.beats(a, a) == 0.5


def test_results_are_order_independent() -> None:
    """Ties must never depend on dict insertion order."""
    forward = allplay.emw(WORKED_EXAMPLE, THREE_CATS)
    reversed_input = dict(reversed(list(WORKED_EXAMPLE.items())))
    assert allplay.emw(reversed_input, THREE_CATS) == forward
