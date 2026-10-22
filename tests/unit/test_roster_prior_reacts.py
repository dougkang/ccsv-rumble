"""User Story 3: the prior is the only forward-looking term, so it must move.

Without this the in-season ranking is purely backward-looking and cannot respond
to an injury or a lopsided trade for weeks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ccsv_rumble.models import (
    PerGameLine,
    PlayerProjection,
    PlayerSlot,
    ProjectionSnapshot,
)
from ccsv_rumble.rank import draft_score, projected

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def _slot(pid: str, positions: tuple[str, ...]) -> PlayerSlot:
    return PlayerSlot(player_id=pid, name=pid, team_id="t.01", positions=positions)


def _proj(pid: str, scale: float) -> PlayerProjection:
    return PlayerProjection(
        pid,
        pid,
        PerGameLine(
            pts=scale, reb=scale / 3, ast=scale / 4, stl=scale / 20, blk=scale / 25,
            tpm=scale / 10, to=1.0, fgm=scale / 3, fga=scale / 1.4,
            ftm=scale / 6, fta=scale / 5,
        ),
        4,
    )


def _roster(team: str, star: bool) -> tuple[PlayerSlot, ...]:
    """Six eligible players; the first is a star only when `star` is set."""
    base = [
        _slot(f"{team}.g1", ("PG",)), _slot(f"{team}.g2", ("SG",)),
        _slot(f"{team}.f1", ("SF",)), _slot(f"{team}.f2", ("PF",)),
        _slot(f"{team}.f3", ("C",)), _slot(f"{team}.g3", ("SG",)),
    ]
    if not star:
        # The star is replaced by a replacement-level player at the same slot.
        base[0] = _slot(f"{team}.g1x", ("PG",))
    return tuple(base)


def _league(star_for_team_one: bool) -> tuple[dict, ProjectionSnapshot]:
    rosters = {f"t.{i:02d}": _roster(f"t.{i:02d}", True) for i in range(2, 11)}
    rosters["t.01"] = _roster("t.01", star_for_team_one)

    projections = []
    for team, slots in rosters.items():
        for slot in slots:
            # The star projects far above everyone; its stand-in far below.
            if slot.player_id.endswith("g1") and team == "t.01":
                scale = 34.0
            elif slot.player_id.endswith("g1x"):
                scale = 4.0
            elif slot.player_id.endswith("g1"):
                scale = 34.0
            else:
                scale = 14.0
            projections.append(_proj(slot.player_id, scale))
    return rosters, ProjectionSnapshot("src", NOW, 1, tuple(projections))


def _rank_of(team: str, star: bool) -> tuple[int, float]:
    rosters, projections = _league(star)
    grid = projected.build_projected_grid(rosters, projections)
    entries = draft_score.score(grid)
    order = draft_score.ordered(entries)
    rank = next(i for i, e in enumerate(order, start=1) if e.team_id == team)
    return rank, entries[team].draft_score


def test_losing_the_best_player_does_not_improve_a_teams_rank() -> None:
    """US3 acceptance 1: it ranks no higher after losing its top player."""
    with_star, score_with = _rank_of("t.01", star=True)
    without_star, score_without = _rank_of("t.01", star=False)

    assert without_star >= with_star, (
        f"team ranked {without_star} without its star and {with_star} with it -- "
        "the prior did not respond to the roster change"
    )
    assert score_without < score_with


def test_the_change_is_actually_visible_not_merely_non_increasing() -> None:
    """A frozen prior would satisfy `>=` trivially, so assert it MOVED."""
    with_star, _ = _rank_of("t.01", star=True)
    without_star, _ = _rank_of("t.01", star=False)
    assert without_star != with_star, (
        "rank is identical with and without the star: the test would pass even "
        "if the prior were ignored entirely"
    )


def test_no_other_team_moved_for_any_other_reason() -> None:
    """Only one input changed, so only its consequences may appear."""
    rosters_a, proj_a = _league(True)
    rosters_b, proj_b = _league(False)
    grid_a = projected.build_projected_grid(rosters_a, proj_a)
    grid_b = projected.build_projected_grid(rosters_b, proj_b)

    # Every team except t.01 has an identical roster in both leagues.
    for team in rosters_a:
        if team == "t.01":
            continue
        assert rosters_a[team] == rosters_b[team]
        assert grid_a[team].line == grid_b[team].line, (
            f"{team}'s projected week changed although its roster did not"
        )


def test_the_prior_is_recomputed_from_the_roster_it_is_given() -> None:
    """FR-035: recomputed from CURRENT rosters, never reused from the draft.

    Demonstrated structurally: the same projection snapshot with two different
    roster sets yields two different priors, so the roster is genuinely an input
    rather than something read once at draft time.
    """
    rosters_a, projections = _league(True)
    rosters_b, _ = _league(False)

    prior_a = draft_score.as_prior(
        draft_score.score(projected.build_projected_grid(rosters_a, projections))
    )
    prior_b = draft_score.as_prior(
        draft_score.score(projected.build_projected_grid(rosters_b, projections))
    )
    assert prior_a["t.01"] != prior_b["t.01"]
