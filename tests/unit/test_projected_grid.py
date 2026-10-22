"""Assembling the projected grid: slot filling, exclusions, and coverage."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ccsv_rumble import config
from ccsv_rumble.models import (
    PerGameLine,
    PlayerProjection,
    PlayerSlot,
    ProjectionSnapshot,
)
from ccsv_rumble.rank import projected

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def _slot(pid: str, positions: tuple[str, ...]) -> PlayerSlot:
    return PlayerSlot(player_id=pid, name=pid, team_id="t.01", positions=positions)


def _proj(pid: str, pts: float, games: int = 4) -> PlayerProjection:
    return PlayerProjection(
        pid, pid, PerGameLine(pts=pts, reb=5.0, ast=3.0, fgm=4.0, fga=9.0, ftm=2.0, fta=2.5), games
    )


def _snapshot(projections: list[PlayerProjection]) -> ProjectionSnapshot:
    return ProjectionSnapshot("src", NOW, 0, tuple(projections))


# --- Eligibility --------------------------------------------------------------


@pytest.mark.parametrize(
    ("slot", "positions", "expected"),
    [
        ("G", ("PG",), True),
        ("G", ("SG",), True),
        ("G", ("SF",), False),
        ("G", ("C",), False),
        ("FC", ("SF",), True),
        ("FC", ("PF",), True),
        ("FC", ("C",), True),
        ("FC", ("PG",), False),
        ("UTIL", ("PG",), True),
        ("UTIL", ("C",), True),
        ("UTIL", (), True),
        ("G", (), False),
        ("FC", (), False),
        ("G", ("sg",), True),
    ],
)
def test_eligibility_collapses_to_three_slot_classes(
    slot: str, positions: tuple[str, ...], expected: bool
) -> None:
    assert projected.eligible_for(slot, positions) is expected


def test_a_player_with_no_positions_fills_util_only() -> None:
    """Fails loudly through the coverage floor rather than mis-ranking quietly."""
    roster = tuple(_slot(f"p{i}", ()) for i in range(10))
    snap = _snapshot([_proj(f"p{i}", 20.0 - i) for i in range(10)])
    contributors, unprojected = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    assert len(contributors) == 1, "only UTIL should be fillable"
    assert unprojected == 0


# --- Slot filling -------------------------------------------------------------


def _balanced_roster() -> tuple[PlayerSlot, ...]:
    return (
        _slot("g1", ("PG",)), _slot("g2", ("SG",)), _slot("g3", ("PG",)),
        _slot("f1", ("SF",)), _slot("f2", ("PF",)), _slot("f3", ("C",)),
        _slot("f4", ("C",)),
    )


def test_slot_filling_respects_the_declared_layout() -> None:
    roster = _balanced_roster()
    snap = _snapshot([_proj(s.player_id, 20.0) for s in roster])
    contributors, _ = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    assert len(contributors) == config.ACTIVE_SLOT_COUNT == 6
    ids = [s.player_id for s in contributors]
    # Two guards and three forward/centres are mandatory; the sixth is UTIL.
    assert sum(1 for i in ids if i.startswith("g")) >= 2
    assert sum(1 for i in ids if i.startswith("f")) >= 3


def test_no_player_fills_two_slots() -> None:
    roster = _balanced_roster()
    snap = _snapshot([_proj(s.player_id, 20.0) for s in roster])
    contributors, _ = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    ids = [s.player_id for s in contributors]
    assert len(ids) == len(set(ids))


def test_narrow_slots_are_filled_before_util() -> None:
    """Order matters: UTIL first could consume the only eligible guard.

    This roster has exactly two guards. If UTIL were filled first and took the
    best guard, a G slot would be left unfillable while a forward sat on the
    bench. Filling G and FC first means all six slots fill.
    """
    roster = (
        _slot("g1", ("PG",)), _slot("g2", ("SG",)),
        _slot("f1", ("SF",)), _slot("f2", ("PF",)),
        _slot("f3", ("C",)), _slot("f4", ("C",)),
    )
    # Make a guard the most valuable player, so a UTIL-first rule would take him.
    snap = _snapshot(
        [_proj("g1", 40.0)] + [_proj(s.player_id, 10.0) for s in roster[1:]]
    )
    contributors, _ = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    assert len(contributors) == 6, "a narrow slot was left unfillable"


def test_ties_break_on_player_id() -> None:
    roster = tuple(_slot(f"p{i}", ("PG", "SF")) for i in range(6))
    snap = _snapshot([_proj(f"p{i}", 20.0) for i in range(6)])
    first = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )[0]
    second = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )[0]
    assert [s.player_id for s in first] == [s.player_id for s in second]


# --- Exclusions and counts ----------------------------------------------------


def test_zero_game_players_are_excluded_not_zeroed() -> None:
    """FR-023: a bye-week player contributing zeros drags ratios to a false floor."""
    roster = _balanced_roster()
    projections = [_proj(s.player_id, 20.0) for s in roster]
    snap_all = _snapshot(projections)

    # Same roster, but every forward is on a bye.
    zeroed = [
        _proj(s.player_id, 20.0, games=0 if s.player_id.startswith("f") else 4)
        for s in roster
    ]
    snap_bye = _snapshot(zeroed)

    full = projected.project_team(
        roster, snap_all.by_player(), projected.player_values(snap_all), "t.01"
    )
    partial = projected.project_team(
        roster, snap_bye.by_player(), projected.player_values(snap_bye), "t.01"
    )
    assert full.filled_slots == 6
    # Only the guards remain eligible to contribute.
    assert partial.filled_slots < full.filled_slots
    assert partial.line.fga > 0, "a zero-game player must not zero the attempts"


def test_unfilled_slots_contribute_nothing() -> None:
    """FR-024: never imputed from a league average or replacement level.

    One player fills ONE slot -- he takes G and is then unavailable for UTIL --
    so five of six slots stay empty and contribute exactly zero. The team's
    totals are that single player's, not a roster-average extrapolation.
    """
    roster = (_slot("g1", ("PG",)),)
    snap = _snapshot([_proj("g1", 20.0)])
    team = projected.project_team(
        roster, snap.by_player(), projected.player_values(snap), "t.01"
    )
    assert team.filled_slots == 1
    assert team.contributors == ("g1",)
    assert team.line.pts == round(20.0 * 4)
    assert team.coverage == pytest.approx(1 / 6)


def test_two_players_can_fill_two_slots_including_util() -> None:
    """The counterpart: UTIL is filled by whoever is left, of either class."""
    roster = (_slot("g1", ("PG",)), _slot("g2", ("SG",)), _slot("f1", ("C",)))
    snap = _snapshot([_proj(s.player_id, 20.0) for s in roster])
    team = projected.project_team(
        roster, snap.by_player(), projected.player_values(snap), "t.01"
    )
    # Two G slots and one FC fill; the remaining FC slots have no one; UTIL has
    # no unassigned player left either.
    assert team.filled_slots == 3
    assert set(team.contributors) == {"g1", "g2", "f1"}


def test_unprojected_players_are_counted_not_dropped() -> None:
    """FR-025, and it is NOT the same quantity as slot coverage."""
    roster = _balanced_roster() + (_slot("x1", ("PG",)), _slot("x2", ("C",)))
    snap = _snapshot([_proj(s.player_id, 20.0) for s in _balanced_roster()])
    team = projected.project_team(
        roster, snap.by_player(), projected.player_values(snap), "t.01"
    )
    assert team.unprojected_count == 2
    # Full coverage despite two unprojected players: six slots still filled.
    assert team.filled_slots == 6
    assert team.coverage == 1.0


def test_totals_are_rounded_once_at_the_end() -> None:
    """Rounding per player biases every total in a consistent direction.

    Six contributors at 2.4 points over one game is 14.4 -> 14. Rounded per
    player it would be 2 each, totalling 12 -- a 17% error, always downward.
    """
    roster = tuple(_slot(f"p{i}", ("PG", "SF")) for i in range(6))
    snap = _snapshot(
        [
            PlayerProjection(f"p{i}", f"p{i}", PerGameLine(pts=2.4, fgm=1.0, fga=2.0), 1)
            for i in range(6)
        ]
    )
    team = projected.project_team(
        roster, snap.by_player(), projected.player_values(snap), "t.01"
    )
    assert team.line.pts == 14, f"expected 14 from 6 x 2.4, got {team.line.pts}"


def test_makes_never_exceed_attempts_after_rounding() -> None:
    """Independent rounding can push makes past attempts when they are close."""
    roster = tuple(_slot(f"p{i}", ("PG", "SF")) for i in range(6))
    snap = _snapshot(
        [
            PlayerProjection(f"p{i}", f"p{i}", PerGameLine(fgm=1.49, fga=1.5), 1)
            for i in range(6)
        ]
    )
    team = projected.project_team(
        roster, snap.by_player(), projected.player_values(snap), "t.01"
    )
    assert team.line.fgm <= team.line.fga


# --- Coverage gates -----------------------------------------------------------


def _grid_with(coverages: list[int]) -> dict[str, projected.TeamProjection]:
    from ccsv_rumble.models import CategoryLine

    return {
        f"t.{i:02d}": projected.TeamProjection(
            team_id=f"t.{i:02d}",
            line=CategoryLine(),
            filled_slots=filled,
            unprojected_count=0,
        )
        for i, filled in enumerate(coverages, start=1)
    }


def test_full_coverage_passes() -> None:
    verdict = projected.check_coverage(_grid_with([6] * 18))
    assert verdict.ok, verdict.reason
    assert verdict.league_coverage == 1.0


def test_one_team_at_five_of_six_passes_the_boundary() -> None:
    """0.80 of six slots permits exactly one unfillable slot: 5/6 = .833."""
    verdict = projected.check_coverage(_grid_with([5] + [6] * 17))
    assert verdict.ok, verdict.reason


def test_one_team_at_four_of_six_fails_the_per_team_floor() -> None:
    verdict = projected.check_coverage(_grid_with([4] + [6] * 17))
    assert not verdict.ok
    assert "active slots" in verdict.reason
    assert verdict.worst_team == "t.01"


def test_every_team_at_five_of_six_fails_the_league_floor() -> None:
    """The case each floor alone would miss.

    0.833 passes every per-team check at 0.80, and fails league-wide at 0.95.
    A gap on all eighteen teams is a source problem, not eighteen coincidences.
    """
    verdict = projected.check_coverage(_grid_with([5] * 18))
    assert not verdict.ok
    assert "league-wide" in verdict.reason


def test_the_two_floors_catch_different_failures() -> None:
    concentrated = projected.check_coverage(_grid_with([4] + [6] * 17))
    diffuse = projected.check_coverage(_grid_with([5] * 18))
    assert not concentrated.ok and not diffuse.ok
    assert "active slots" in concentrated.reason
    assert "league-wide" in diffuse.reason
    # Neither would be caught by the other's threshold alone.
    assert diffuse.worst_coverage is not None
    assert diffuse.worst_coverage > config.DRAFT_MIN_TEAM_COVERAGE


# --- Learned from a real roster page ------------------------------------------


@pytest.mark.parametrize(
    ("slot", "positions", "expected"),
    [
        # Yahoo renders eligibility in THIS league's slot classes, not the usual
        # nine-slot vocabulary: "PHX - G", "MIA - FC", "ORL - G,FC".
        ("G", ("G",), True),
        ("FC", ("FC",), True),
        ("G", ("G", "FC"), True),
        ("FC", ("G", "FC"), True),
        ("FC", ("G",), False),
        ("G", ("FC",), False),
    ],
)
def test_collapsed_eligibility_tokens_are_accepted(
    slot: str, positions: tuple[str, ...], expected: bool
) -> None:
    """Regression: `FC` satisfied no slot, so nothing could ever publish.

    Three of six active slots were unfillable for every team, putting coverage
    at 0.5 against a 0.80 floor -- the run would have refused to publish, for
    every team, forever.
    """
    assert projected.eligible_for(slot, positions) is expected


def test_the_real_roster_fills_every_active_slot() -> None:
    """The observed roster, with the lineup Yahoo itself shows."""
    roster = (
        _slot("booker", ("G",)), _slot("coward", ("G", "FC")),
        _slot("giannis", ("FC",)), _slot("kessler", ("FC",)),
        _slot("sarr", ("FC",)), _slot("wiggins", ("G", "FC")),
        _slot("nembhard", ("G",)), _slot("vanvleet", ("G",)),
        _slot("laravia", ("FC",)),
    )
    snap = _snapshot([_proj(s.player_id, 30.0 - i) for i, s in enumerate(roster)])
    contributors, _ = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    assert len(contributors) == config.ACTIVE_SLOT_COUNT


def test_an_injured_list_player_cannot_fill_an_active_slot() -> None:
    """Rostered, but the format cannot deploy him this week.

    Observed on a real roster: ten players with one on IL. Crediting his
    production would inflate the team by a player who cannot play.
    """
    il = PlayerSlot(
        player_id="black", name="black", team_id="t.01",
        positions=("G", "FC"), status="IL",
    )
    roster = (
        _slot("booker", ("G",)), _slot("coward", ("G", "FC")),
        _slot("giannis", ("FC",)), _slot("kessler", ("FC",)),
        _slot("sarr", ("FC",)), _slot("wiggins", ("G", "FC")), il,
    )
    snap = _snapshot([_proj(s.player_id, 20.0) for s in roster])
    # Make the IL player by far the most valuable, so only the status excludes him.
    values = dict.fromkeys((s.player_id for s in roster), 1.0)
    values["black"] = 999.0

    contributors, unprojected = projected.fill_active_slots(
        roster, snap.by_player(), values
    )
    assert "black" not in {s.player_id for s in contributors}
    assert len(contributors) == config.ACTIVE_SLOT_COUNT
    # Still rostered: he counts toward completeness, just not toward the lineup.
    assert unprojected == 0


def test_a_day_to_day_player_is_still_deployable() -> None:
    """Only the IL SLOT bars a player, not every injury designation.

    Excluding a questionable player would shrink the team over a designation
    the manager has not acted on.
    """
    questionable = PlayerSlot(
        player_id="q", name="q", team_id="t.01", positions=("G",), status="Q"
    )
    roster = (questionable, _slot("f1", ("FC",)))
    snap = _snapshot([_proj(s.player_id, 20.0) for s in roster])
    contributors, _ = projected.fill_active_slots(
        roster, snap.by_player(), projected.player_values(snap)
    )
    assert "q" in {s.player_id for s in contributors}
