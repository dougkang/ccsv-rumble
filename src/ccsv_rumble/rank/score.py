"""PowerScore composition and deterministic ordering. PURE.

    PowerScore = w * Performance + (1 - w) * RosterPrior
    Performance = EMW_WEIGHT * emw_rw + CAW_WEIGHT * caw_rw
    w           = n / (n + SHRINKAGE_K)
    week weight = 0.5 ** ((n - w) / RECENCY_HALF_LIFE_WEEKS)

Everything stays in win-probability-against-a-random-opponent units, so the score
is directly interpretable rather than an arbitrary index. The score is never
published -- it lives in the archived internal report (FR-032).
"""

from __future__ import annotations

from collections.abc import Sequence

from .. import config
from ..models import (
    CategoryLine,
    LuckBand,
    Ranking,
    RankingEntry,
    Snapshot,
    TeamId,
)
from . import allplay
from .significance import classify_movement


def recency_weights(weeks: Sequence[int]) -> dict[int, float]:
    """Half-life decay over the weeks present, newest weighted 1.0."""
    if not weeks:
        return {}
    newest = max(weeks)
    return {
        week: 0.5 ** ((newest - week) / config.RECENCY_HALF_LIFE_WEEKS)
        for week in weeks
    }


def performance_weight(completed_weeks: int) -> float:
    """w = n / (n + k). Ramps from pure projection to ~87% realized by week 20."""
    if completed_weeks <= 0:
        return 0.0
    return completed_weeks / (completed_weeks + config.SHRINKAGE_K)


def _weighted_metric(
    history: Sequence[Snapshot],
    metric,
    team_ids: Sequence[TeamId],
) -> dict[TeamId, float]:
    weights = recency_weights([s.week for s in history])
    totals_weight = sum(weights.values()) or 1.0
    accumulated: dict[TeamId, float] = dict.fromkeys(team_ids, 0.0)
    for snapshot in history:
        week_values = metric(snapshot.category_totals)
        weight = weights[snapshot.week]
        for team_id in team_ids:
            accumulated[team_id] += week_values.get(team_id, 0.0) * weight
    return {team_id: value / totals_weight for team_id, value in accumulated.items()}


def actual_win_pct(history: Sequence[Snapshot]) -> dict[TeamId, float]:
    """Real head-to-head record from the schedule actually played."""
    wins: dict[TeamId, float] = {}
    played: dict[TeamId, int] = {}
    for snapshot in history:
        totals = snapshot.category_totals
        for matchup in snapshot.matchups:
            home, away = matchup.home_team_id, matchup.away_team_id
            if home not in totals or away not in totals:
                continue
            result = allplay.beats(totals[home], totals[away])
            wins[home] = wins.get(home, 0.0) + result
            wins[away] = wins.get(away, 0.0) + (1.0 - result)
            played[home] = played.get(home, 0) + 1
            played[away] = played.get(away, 0) + 1
    return {
        team_id: wins[team_id] / played[team_id]
        for team_id in wins
        if played.get(team_id)
    }


def record_string(history: Sequence[Snapshot], team_id: TeamId) -> str:
    """Category record as "W-L-T", e.g. "14-12-1". A league fact, not a ranking output.

    Accumulated per CATEGORY, not per matchup: each matchup played adds nine
    results, one for each category won, lost, or tied. Ties are always shown,
    even at zero, so every record reads the same way.
    """
    won = lost = tied = 0
    for snapshot in history:
        totals = snapshot.category_totals
        for matchup in snapshot.matchups:
            if team_id not in (matchup.home_team_id, matchup.away_team_id):
                continue
            opponent = (
                matchup.away_team_id
                if matchup.home_team_id == team_id
                else matchup.home_team_id
            )
            if team_id not in totals or opponent not in totals:
                continue
            for category in config.CATEGORIES:
                result = allplay.compare_category(
                    totals[team_id], totals[opponent], category
                )
                if result == 1.0:
                    won += 1
                elif result == 0.0:
                    lost += 1
                else:
                    tied += 1
    return f"{won}-{lost}-{tied}"


def luck_band(schedule_luck: float | None) -> LuckBand | None:
    """Map the numeric luck figure to the only form that may be published."""
    if schedule_luck is None:
        return None
    for threshold, name in config.LUCK_BAND_THRESHOLDS:
        if schedule_luck >= threshold:
            return LuckBand(name)
    return LuckBand(config.LUCK_BAND_FLOOR)


def build_ranking(
    history: Sequence[Snapshot],
    *,
    previous_ranks: dict[TeamId, int] | None = None,
    roster_prior: dict[TeamId, float] | None = None,
) -> Ranking:
    """Compose the ranking from a week-ascending history.

    `history` must end with the week being ranked. Each snapshot should be the
    LATEST archived entry for its week, so corrections feed forward (FR-047).
    """
    if not history:
        raise ValueError("cannot rank an empty history")

    current = history[-1]
    team_ids = sorted(current.category_totals)
    completed = len(history)

    emw_rw = _weighted_metric(history, allplay.emw, team_ids)
    caw_rw = _weighted_metric(history, allplay.caw, team_ids)
    profiles = allplay.category_profile(current.category_totals)
    actual = actual_win_pct(history)

    w = performance_weight(completed)
    prior = roster_prior or {}

    scored: list[tuple[TeamId, float, float, float, float | None]] = []
    for team_id in team_ids:
        performance = (
            config.EMW_WEIGHT * emw_rw[team_id] + config.CAW_WEIGHT * caw_rw[team_id]
        )
        team_prior = prior.get(team_id)
        # No projections available: performance carries the full weight rather
        # than silently substituting a 0.0 prior, which would penalize every
        # team identically but still distort the shrinkage ramp.
        score = (
            performance
            if team_prior is None
            else w * performance + (1.0 - w) * team_prior
        )
        scored.append((team_id, score, emw_rw[team_id], caw_rw[team_id], team_prior))

    # Stable sort by (-power_score, team_id). Never dict insertion order.
    scored.sort(key=lambda row: (-row[1], row[0]))

    entries: list[RankingEntry] = []
    for position, (team_id, score, emw_value, caw_value, team_prior) in enumerate(
        scored, start=1
    ):
        previous = (previous_ranks or {}).get(team_id)
        change = None if previous is None else previous - position
        luck = None
        if team_id in actual:
            luck = actual[team_id] - emw_value
        entries.append(
            RankingEntry(
                team_id=team_id,
                rank=position,
                previous_rank=previous,
                rank_change=change,
                movement=classify_movement(change),
                power_score=score,
                emw=emw_value,
                caw=caw_value,
                roster_prior=team_prior,
                performance_weight=w,
                category_profile=profiles.get(team_id, {}),
                actual_win_pct=actual.get(team_id),
                schedule_luck=luck,
                luck_band=luck_band(luck),
            )
        )

    return Ranking(
        algorithm_version=config.ALGORITHM_VERSION,
        week=current.week,
        entries=tuple(entries),
    )


def category_notes(profile: dict[str, float]) -> tuple[str, ...]:
    """Qualitative phrases derived from the category profile.

    The profile is internal; these phrases are the only form that reaches the
    page (FR-033). Deliberately returns words, never figures.
    """
    labels = {
        "pts": "scoring",
        "reb": "rebounding",
        "ast": "assists",
        "stl": "steals",
        "blk": "blocks",
        "tpm": "three-pointers",
        "to": "ball security",
        "fg_pct": "field-goal efficiency",
        "ft_pct": "free-throw shooting",
    }
    notes: list[str] = []
    ordered = sorted(profile.items(), key=lambda kv: (-kv[1], kv[0]))
    for category, rate in ordered[:2]:
        if rate >= 0.70:
            notes.append(f"among the league's best at {labels.get(category, category)}")
    for category, rate in reversed(ordered[-2:]):
        if rate <= 0.30:
            notes.append(f"giving away {labels.get(category, category)} most weeks")
    return tuple(notes)


def totals_for(snapshot: Snapshot, team_id: TeamId) -> CategoryLine:
    return snapshot.category_totals[team_id]
