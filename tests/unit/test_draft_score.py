"""DraftScore: all-play reuse plus shrink.

The headline test is the design document's own worked example, which turns
`DRAFT_SHRINK = 0.6` from an assertion in prose into something executable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ccsv_rumble import config
from ccsv_rumble.models import CategoryLine, TeamId
from ccsv_rumble.rank import draft_score
from ccsv_rumble.rank.projected import TeamProjection

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def _grid(lines: dict[TeamId, CategoryLine]) -> dict[TeamId, TeamProjection]:
    return {
        team_id: TeamProjection(
            team_id=team_id,
            line=line,
            filled_slots=config.ACTIVE_SLOT_COUNT,
            unprojected_count=0,
        )
        for team_id, line in lines.items()
    }


# --- The worked example -------------------------------------------------------


def test_shrink_reproduces_the_design_documents_worked_example() -> None:
    """A projection must not outrank observed dominance.

    Design document §4: a team whose POINT projections sweep five categories
    against all 17 opponents reaches AllPlay_proj ≈ .895 unshrunk, which would
    place it above a *proven* dominant team at a realized .804. With s = 0.6 it
    lands at .737 -- below the proven team, which is the correct ordering.
    """
    assert draft_score.shrink(0.895) == pytest.approx(0.737, abs=0.001)
    assert draft_score.shrink(0.895) < 0.804, (
        "an unproven projection outranks observed dominance: the shrink is not "
        "doing the one job it exists for"
    )


def test_a_proven_teams_roster_shrinks_to_the_documented_value() -> None:
    """Same example, the prior case: .804 realized shrinks to .683."""
    assert draft_score.shrink(0.804) == pytest.approx(0.683, abs=0.001)


def test_shrink_is_centred_on_even_odds() -> None:
    assert draft_score.shrink(0.5) == 0.5
    # Symmetric: equal distances from .500 shrink to equal distances.
    assert draft_score.shrink(0.9) - 0.5 == pytest.approx(0.5 - draft_score.shrink(0.1))


def test_a_perfect_projection_cannot_reach_certainty() -> None:
    """The specific overconfidence the constant exists to damp."""
    assert draft_score.shrink(1.0) == pytest.approx(0.8)
    assert draft_score.shrink(1.0) < 1.0


# --- Scoring over a grid ------------------------------------------------------


def _strong() -> CategoryLine:
    return CategoryLine(
        pts=600, reb=240, ast=160, stl=50, blk=40, tpm=80, to=40,
        fgm=200, fga=400, ftm=90, fta=100, games_played=36,
    )


def _weak() -> CategoryLine:
    return CategoryLine(
        pts=400, reb=150, ast=80, stl=20, blk=10, tpm=30, to=90,
        fgm=140, fga=400, ftm=50, fta=100, games_played=36,
    )


def test_a_stronger_projected_grid_scores_higher() -> None:
    grid = _grid({"t.01": _strong(), "t.02": _weak()})
    scored = draft_score.score(grid)
    assert scored["t.01"].draft_score > scored["t.02"].draft_score


def test_every_score_lies_inside_the_shrunk_band() -> None:
    """Scores stay in (0,1) and never reach the extremes."""
    grid = _grid({"t.01": _strong(), "t.02": _weak()})
    for entry in draft_score.score(grid).values():
        assert 0.0 < entry.draft_score < 1.0
        lower = draft_score.shrink(0.0)
        upper = draft_score.shrink(1.0)
        assert lower <= entry.draft_score <= upper


def test_identical_teams_tie_and_break_on_team_id() -> None:
    """FR-022: identical inputs must always yield identical ordering."""
    grid = _grid({"t.02": _strong(), "t.01": _strong(), "t.03": _strong()})
    scored = draft_score.score(grid)
    assert len({round(e.draft_score, 12) for e in scored.values()}) == 1
    assert [e.team_id for e in draft_score.ordered(scored)] == ["t.01", "t.02", "t.03"]


def test_ordering_is_stable_across_repeated_runs() -> None:
    grid = _grid({f"t.{i:02d}": _strong() if i % 2 else _weak() for i in range(1, 11)})
    first = [e.team_id for e in draft_score.ordered(draft_score.score(grid))]
    second = [e.team_id for e in draft_score.ordered(draft_score.score(grid))]
    assert first == second


def test_zero_attempts_routes_into_the_existing_rule() -> None:
    """FR-027: no new zero-attempt rule.

    A team with no attempts loses the category to any team with at least one,
    which is `allplay.compare_category`'s existing explicit branch -- reached
    here only because the grid produces a CategoryLine.
    """
    no_attempts = CategoryLine(
        pts=400, reb=150, ast=80, stl=20, blk=10, tpm=30, to=50,
        fgm=0, fga=0, ftm=0, fta=0, games_played=30,
    )
    grid = _grid({"t.01": _strong(), "t.02": no_attempts})
    scored = draft_score.score(grid)
    assert scored["t.01"].draft_score > scored["t.02"].draft_score


def test_incomplete_data_still_scores_without_raising() -> None:
    """Constitution: ranking logic must be tested on incomplete data."""
    thin = CategoryLine(games_played=0)
    grid = _grid({"t.01": _strong(), "t.02": thin})
    scored = draft_score.score(grid)
    assert set(scored) == {"t.01", "t.02"}


def test_the_prior_is_the_same_number() -> None:
    """FR-036: RosterPrior IS DraftScore -- no separate mapping step."""
    grid = _grid({"t.01": _strong(), "t.02": _weak()})
    scored = draft_score.score(grid)
    prior = draft_score.as_prior(scored)
    assert prior["t.01"] == scored["t.01"].draft_score
    assert prior["t.02"] == scored["t.02"].draft_score


def test_the_prior_is_in_win_probability_units_not_a_percentile_map() -> None:
    """The units problem §3 exists to avoid.

    A min-max normalization would put the best team at exactly 1.000 and the
    worst at 0.000. Real all-play does not, and blending a uniform 0-1 prior
    against a clustered EMW would exaggerate both extremes.
    """
    grid = _grid({"t.01": _strong(), "t.02": _weak(), "t.03": _weak()})
    prior = draft_score.as_prior(draft_score.score(grid))
    assert max(prior.values()) < 1.0
    assert min(prior.values()) > 0.0


def test_weights_are_reused_not_redeclared() -> None:
    """Reading the in-season constants is what keeps the algorithms agreeing."""
    assert pytest.approx(1.0) == config.EMW_WEIGHT + config.CAW_WEIGHT
    grid = _grid({"t.01": _strong(), "t.02": _weak()})
    entry = draft_score.score(grid)["t.01"]
    expected = draft_score.shrink(
        config.EMW_WEIGHT * entry.emw_proj + config.CAW_WEIGHT * entry.caw_proj
    )
    assert entry.draft_score == pytest.approx(expected)
