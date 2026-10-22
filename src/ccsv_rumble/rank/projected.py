"""Assemble each team's PROJECTED nine-category week. PURE.

The output is a `dict[TeamId, CategoryLine]` -- deliberately the same shape an
observed week produces, which is what lets `allplay.emw`/`allplay.caw` run over
it completely unchanged. FR-019 forbids a second scoring function, and reusing
the type rather than inventing a parallel one is how that is enforced
structurally instead of by discipline.

Three rules here are load-bearing and each has a failure mode if dropped:

* **Zero-game players are excluded, not zeroed** (FR-023). A player on a bye who
  contributed zeros would drag the team's ratio categories toward a false floor.
* **Only active slots count** (FR-018). Summing the whole roster credits bench
  depth the format cannot deploy in a week -- and the previous roster-prior
  implementation did exactly that.
* **Accumulate in floats, round ONCE at the end.** Rounding per player biases
  every total by up to half a unit per contributor, in a consistent direction.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .. import config
from ..models import CategoryLine, PlayerProjection, PlayerSlot, ProjectionSnapshot, TeamId

#: Quantities the slot-selection scalar is built from. Counting categories plus
#: shooting MAKES -- attempts are deliberately excluded, since a high-volume
#: inefficient shooter should not be promoted for missing more shots.
_VALUE_CATEGORIES: tuple[str, ...] = (
    "pts", "reb", "ast", "stl", "blk", "tpm", "fgm", "ftm",
)


@dataclass(frozen=True)
class TeamProjection:
    """One team's projected week, plus the coverage facts behind it."""

    team_id: TeamId
    line: CategoryLine
    #: Active slots a projected player could be found for, of ACTIVE_SLOT_COUNT.
    filled_slots: int
    #: Rostered players with no projection at all (FR-025). NOT the same as
    #: unfilled slots: a team can have four unprojected bench players and still
    #: field a complete projected lineup.
    unprojected_count: int
    contributors: tuple[str, ...] = ()

    @property
    def coverage(self) -> float:
        return self.filled_slots / config.ACTIVE_SLOT_COUNT


def player_values(snapshot: ProjectionSnapshot) -> dict[str, float]:
    """A per-player scalar used ONLY to choose contributors.

    §3 of the design document argues at length against a scalar prior, and this
    does not contradict it: the scalar decides *who plays*, never *who is
    better*. Team strength stays category-wise, through the all-play grid.

    The rule is declared rather than tuned -- per-category z-scores over the
    projection set, summed, with turnovers subtracted. It needs no external data,
    so it is reproducible from the archived snapshot alone.
    """
    projections = snapshot.projections
    if not projections:
        return {}

    totals: dict[str, list[float]] = {}
    for category in (*_VALUE_CATEGORIES, "to"):
        totals[category] = [
            getattr(p.per_game, category) * p.projected_games for p in projections
        ]

    stats: dict[str, tuple[float, float]] = {}
    for category, values in totals.items():
        mean = statistics.fmean(values)
        # A zero spread means the category cannot discriminate; z collapses to 0
        # rather than raising or dividing by zero.
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        stats[category] = (mean, stdev)

    def z(category: str, value: float) -> float:
        mean, stdev = stats[category]
        return 0.0 if stdev == 0.0 else (value - mean) / stdev

    values: dict[str, float] = {}
    for p in projections:
        score = sum(
            z(category, getattr(p.per_game, category) * p.projected_games)
            for category in _VALUE_CATEGORIES
        )
        # Turnovers are the one inverted category: fewer is better.
        score -= z("to", p.per_game.to * p.projected_games)
        values[p.player_id] = score
    return values


def eligible_for(slot: str, positions: tuple[str, ...]) -> bool:
    """Does a player's raw eligibility satisfy this slot?

    An empty `positions` tuple is eligible for UTIL only. That is deliberate: a
    roster with no position data then fills one slot and leaves five unfillable,
    tripping the coverage floor loudly rather than silently ranking a team by
    "best six players regardless of position".
    """
    allowed = config.SLOT_ELIGIBILITY.get(slot)
    if allowed is None:  # UTIL, or any future open slot
        return True
    return bool(allowed & {p.upper() for p in positions})


def fill_active_slots(
    roster: tuple[PlayerSlot, ...],
    projections: dict[str, PlayerProjection],
    values: dict[str, float],
) -> tuple[tuple[PlayerSlot, ...], int]:
    """Choose contributors for one team. Returns (contributors, unprojected).

    Slots are filled in `config.ACTIVE_SLOTS` order -- narrowest eligibility
    first -- and each slot takes the best ELIGIBLE player not yet assigned.
    Filling UTIL first would be strictly worse: it could consume the best guard
    and leave a G slot unfillable while an eligible forward sat on the bench.

    Ties break on `(value desc, player_id asc)` so the result is reproducible
    from the declared order alone (FR-022).
    """
    unprojected = sum(1 for slot in roster if slot.player_id not in projections)

    # FR-023: zero projected games means excluded entirely, not zero-valued.
    candidates = [
        slot
        for slot in roster
        if slot.player_id in projections
        and projections[slot.player_id].projected_games > 0
    ]
    candidates.sort(key=lambda s: (-values.get(s.player_id, 0.0), s.player_id))

    chosen: list[PlayerSlot] = []
    taken: set[str] = set()
    for slot_name in config.ACTIVE_SLOTS:
        for candidate in candidates:
            if candidate.player_id in taken:
                continue
            if eligible_for(slot_name, candidate.positions):
                chosen.append(candidate)
                taken.add(candidate.player_id)
                break
        # No eligible player left: the slot stays unfilled and contributes
        # nothing (FR-024). Never imputed from a league average.
    return tuple(chosen), unprojected


def project_team(
    roster: tuple[PlayerSlot, ...],
    projections: dict[str, PlayerProjection],
    values: dict[str, float],
    team_id: TeamId,
) -> TeamProjection:
    """One team's projected nine-category week."""
    contributors, unprojected = fill_active_slots(roster, projections, values)

    acc: dict[str, float] = dict.fromkeys(
        ("pts", "reb", "ast", "stl", "blk", "tpm", "to", "fgm", "fga", "ftm", "fta"), 0.0
    )
    games = 0.0
    for slot in contributors:
        projection = projections[slot.player_id]
        for key in acc:
            acc[key] += getattr(projection.per_game, key) * projection.projected_games
        games += projection.projected_games

    # Round ONCE, here, after all accumulation.
    line = CategoryLine(
        **{key: int(round(value)) for key, value in acc.items()},
        games_played=int(round(games)),
    )
    # Rounding independently can push makes above attempts when the two are
    # close; clamp rather than raise, since the cause is representation, not data.
    if line.fgm > line.fga or line.ftm > line.fta:
        line = CategoryLine(
            **{k: getattr(line, k) for k in acc if k not in ("fgm", "ftm")},
            fgm=min(line.fgm, line.fga),
            ftm=min(line.ftm, line.fta),
            games_played=line.games_played,
        )

    return TeamProjection(
        team_id=team_id,
        line=line,
        filled_slots=len(contributors),
        unprojected_count=unprojected,
        contributors=tuple(slot.player_id for slot in contributors),
    )


def build_projected_grid(
    rosters: dict[TeamId, tuple[PlayerSlot, ...]], snapshot: ProjectionSnapshot
) -> dict[TeamId, TeamProjection]:
    """The projected 18 x 9 grid, keyed by team."""
    projections = snapshot.by_player()
    values = player_values(snapshot)
    return {
        team_id: project_team(roster, projections, values, team_id)
        for team_id, roster in sorted(rosters.items())
    }


# --- Coverage gates -----------------------------------------------------------


@dataclass(frozen=True)
class CoverageVerdict:
    ok: bool
    reason: str
    league_coverage: float
    worst_team: TeamId | None = None
    worst_coverage: float | None = None


def check_coverage(grid: dict[TeamId, TeamProjection]) -> CoverageVerdict:
    """Both floors from `config`, checked separately (FR-026).

    They catch different failures. The per-team floor catches one unrankable
    team among seventeen fine ones. The league-wide floor catches a systemic
    source problem spread thinly enough to clear every per-team check --
    eighteen teams each missing one slot passes per-team at 0.833 and is
    refused here.
    """
    if not grid:
        return CoverageVerdict(False, "no teams in the projected grid", 0.0)

    filled = sum(t.filled_slots for t in grid.values())
    possible = len(grid) * config.ACTIVE_SLOT_COUNT
    league = filled / possible if possible else 0.0

    worst_id, worst = min(
        ((t.team_id, t.coverage) for t in grid.values()), key=lambda pair: (pair[1], pair[0])
    )

    if worst < config.DRAFT_MIN_TEAM_COVERAGE:
        return CoverageVerdict(
            False,
            f"team {worst_id} can fill only "
            f"{round(worst * config.ACTIVE_SLOT_COUNT)} of "
            f"{config.ACTIVE_SLOT_COUNT} active slots "
            f"({worst:.3f} < {config.DRAFT_MIN_TEAM_COVERAGE})",
            league,
            worst_id,
            worst,
        )
    if league < config.DRAFT_MIN_LEAGUE_COVERAGE:
        return CoverageVerdict(
            False,
            f"league-wide projection coverage {league:.3f} is below "
            f"{config.DRAFT_MIN_LEAGUE_COVERAGE} ({filled} of {possible} active "
            "slots fillable); a gap on this many teams is a source problem",
            league,
            worst_id,
            worst,
        )
    return CoverageVerdict(
        True, f"coverage {league:.3f}; worst team {worst_id} at {worst:.3f}", league,
        worst_id, worst,
    )
