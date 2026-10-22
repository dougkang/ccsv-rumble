"""DraftScore: the projected grid run through all-play, then shrunk. PURE.

    DraftScore(i) = 0.5 + s * (AllPlay_proj(i) - 0.5)
    AllPlay_proj(i) = EMW_WEIGHT * EMW_proj(i) + CAW_WEIGHT * CAW_proj(i)

`emw` and `caw` are imported and used unchanged -- FR-019 forbids a second
scoring function, and `EMW_WEIGHT`/`CAW_WEIGHT` are REUSED rather than
redeclared, which is what keeps the two algorithms agreeing about what "good"
means in this format.

Why shrink at all: all-play over POINT projections is overconfident, for the
same threshold nonlinearity that motivates EMW in the first place. A team
projected to edge five categories by a hair wins every simulated matchup and
scores 1.000 -- a claim no honest forecast can make -- and because the
performance weight is zero at week 0, nothing else in the system damps it.

Why a constant rather than a simulation: the principled fix is Monte Carlo over
per-category weekly variance, and at week 0 there IS no variance to draw from.
Any coefficient invented in year one would be a fabricated constant that
immediately wants refitting. One declared shrink is the honest version of the
same correction, and `DRAFT_SHRINK` is the first refit target after a season.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..models import Movement, Ranking, RankingEntry, TeamId
from . import allplay
from .projected import TeamProjection


@dataclass(frozen=True)
class DraftScoreEntry:
    team_id: TeamId
    draft_score: float
    emw_proj: float
    caw_proj: float
    unprojected_count: int


def shrink(all_play: float, s: float = config.DRAFT_SHRINK) -> float:
    """Pull a projected all-play rate toward even odds."""
    return 0.5 + s * (all_play - 0.5)


def score(grid: dict[TeamId, TeamProjection]) -> dict[TeamId, DraftScoreEntry]:
    """Run the existing all-play grid over projections and shrink the result."""
    totals = {team_id: projection.line for team_id, projection in grid.items()}
    emw_proj = allplay.emw(totals)
    caw_proj = allplay.caw(totals)

    return {
        team_id: DraftScoreEntry(
            team_id=team_id,
            draft_score=shrink(
                config.EMW_WEIGHT * emw_proj[team_id]
                + config.CAW_WEIGHT * caw_proj[team_id]
            ),
            emw_proj=emw_proj[team_id],
            caw_proj=caw_proj[team_id],
            unprojected_count=grid[team_id].unprojected_count,
        )
        for team_id in sorted(grid)
    }


def ordered(entries: dict[TeamId, DraftScoreEntry]) -> list[DraftScoreEntry]:
    """Rank order: score descending, team_id ascending as the tiebreak.

    The same stable sort the in-season ranking uses, so identical inputs always
    yield identical ordering (FR-022).
    """
    return sorted(entries.values(), key=lambda e: (-e.draft_score, e.team_id))


def build_draft_ranking(
    entries: dict[TeamId, DraftScoreEntry], week: int = 0
) -> Ranking:
    """The week-0 ranking: ordered by DraftScore, with movement unavailable.

    Week 0 has no played results, so there is no history to rank over and
    `rank.score.build_ranking` has nothing to consume. This is the separate
    entry point for that state -- not a second scoring function, since the score
    itself came from the shared all-play grid.

    Movement is UNAVAILABLE rather than zero for every team (FR-006): no previous
    ranking exists, and zero would assert "unchanged", which is a different and
    false claim. `RankingEntry` enforces the pairing, so this cannot drift.
    """
    return Ranking(
        algorithm_version=config.ALGORITHM_VERSION,
        week=week,
        draft_algorithm_version=config.DRAFT_ALGORITHM_VERSION,
        entries=tuple(
            RankingEntry(
                team_id=entry.team_id,
                rank=position,
                previous_rank=None,
                rank_change=None,
                movement=Movement.UNAVAILABLE,
                roster_prior=entry.draft_score,
                draft_score=entry.draft_score,
                emw_proj=entry.emw_proj,
                caw_proj=entry.caw_proj,
                unprojected_count=entry.unprojected_count,
            )
            for position, entry in enumerate(ordered(entries), start=1)
        ),
    )


def as_prior(entries: dict[TeamId, DraftScoreEntry]) -> dict[TeamId, float]:
    """The same number in its in-season role.

    `RosterPrior` IS `DraftScore`, recomputed from the current roster -- no
    separate mapping step, and no second definition of roster strength anywhere
    in the codebase (design document §4, FR-036). Already in
    win-probability-against-a-random-opponent units, which is what makes the
    in-season blend add two quantities that mean the same thing.
    """
    return {team_id: entry.draft_score for team_id, entry in sorted(entries.items())}
