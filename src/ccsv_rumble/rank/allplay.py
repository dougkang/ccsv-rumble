"""All-play: compare every team against every other team, every week.

PURE. This module imports nothing from fetch/, archive/, or publish -- that import
rule is what makes "pure function of the snapshot" an architectural property
rather than a convention, and it is asserted by a test.

Two metrics, and the difference between them is the whole design:

  EMW  Expected Matchup Win% -- replay against all 17 opponents, >=5 of 9 wins.
       This is the objective. It is a THRESHOLD function, which is why a punt
       build that is 2nd in six categories and last in three rates as dominant
       while a team that is 1st in four and 17th in five rates near zero.

  CAW  Category All-Play Win% -- score all 9 x 17 = 153 comparisons individually.
       ~18x the sample, far lower variance, but it measures average category
       strength, which is NOT the objective. It enters only as a variance reducer.
"""

from __future__ import annotations

from collections.abc import Sequence

from .. import config
from ..models import CategoryLine, TeamId

#: A tie scores half to each side, in both metrics. Never host-order dependent.
TIE = 0.5


def _ratio(line: CategoryLine, category: str) -> tuple[int, int]:
    made_field, att_field = config.RATIO_FIELDS[category]
    return getattr(line, made_field), getattr(line, att_field)


def compare_category(a: CategoryLine, b: CategoryLine, category: str) -> float:
    """Score one category comparison from a's perspective: 1.0, 0.5, or 0.0.

    Ratio categories compare made/attempted. Zero attempts is an explicit branch,
    not a division-by-zero guard: a team with no attempts LOSES to any team with
    at least one, and TIES another team with none (data-model.md s2).
    """
    if category in config.RATIO_CATEGORIES:
        a_made, a_att = _ratio(a, category)
        b_made, b_att = _ratio(b, category)
        if a_att == 0 and b_att == 0:
            return TIE
        if a_att == 0:
            return 0.0
        if b_att == 0:
            return 1.0
        a_value = a_made / a_att
        b_value = b_made / b_att
    else:
        a_value = float(getattr(a, category))
        b_value = float(getattr(b, category))
        if category in config.INVERTED_CATEGORIES:
            # Lower wins. Flip the sign rather than branching below.
            a_value, b_value = -a_value, -b_value

    if a_value > b_value:
        return 1.0
    if a_value < b_value:
        return 0.0
    return TIE


def category_wins(
    a: CategoryLine, b: CategoryLine, categories: Sequence[str] = config.CATEGORIES
) -> float:
    """Total categories a takes against b, ties counting half."""
    return sum(compare_category(a, b, category) for category in categories)


def beats(
    a: CategoryLine, b: CategoryLine, categories: Sequence[str] = config.CATEGORIES
) -> float:
    """Simulated matchup result for a vs b: 1.0 win, 0.5 tie, 0.0 loss.

    A matchup is won at >= 5 of 9 categories (more than half). An exact split
    is a tie. `categories` is injectable so the algorithm doc's 4-team,
    3-category worked example can be tested directly against this code.
    """
    won = category_wins(a, b, categories)
    half = len(categories) / 2
    if won > half:
        return 1.0
    if won < half:
        return 0.0
    return TIE


def caw(
    totals: dict[TeamId, CategoryLine], categories: Sequence[str] = config.CATEGORIES
) -> dict[TeamId, float]:
    """Category all-play win rate per team: 9 x (N-1) comparisons each."""
    team_ids = sorted(totals)
    comparisons = len(categories) * (len(team_ids) - 1)
    if comparisons <= 0:
        return {team_id: 0.0 for team_id in team_ids}

    result: dict[TeamId, float] = {}
    for team_id in team_ids:
        won = sum(
            category_wins(totals[team_id], totals[other], categories)
            for other in team_ids
            if other != team_id
        )
        result[team_id] = won / comparisons
    return result


def emw(
    totals: dict[TeamId, CategoryLine], categories: Sequence[str] = config.CATEGORIES
) -> dict[TeamId, float]:
    """Expected matchup win rate per team: N-1 replayed matchups each."""
    team_ids = sorted(totals)
    opponents = len(team_ids) - 1
    if opponents <= 0:
        return {team_id: 0.0 for team_id in team_ids}

    result: dict[TeamId, float] = {}
    for team_id in team_ids:
        won = sum(
            beats(totals[team_id], totals[other], categories)
            for other in team_ids
            if other != team_id
        )
        result[team_id] = won / opponents
    return result


def category_profile(totals: dict[TeamId, CategoryLine]) -> dict[TeamId, dict[str, float]]:
    """Per-category all-play win rate. Internal only -- never published as a number."""
    team_ids = sorted(totals)
    opponents = len(team_ids) - 1
    profile: dict[TeamId, dict[str, float]] = {}
    for team_id in team_ids:
        per_category: dict[str, float] = {}
        for category in config.CATEGORIES:
            if opponents <= 0:
                per_category[category] = 0.0
                continue
            won = sum(
                compare_category(totals[team_id], totals[other], category)
                for other in team_ids
                if other != team_id
            )
            per_category[category] = won / opponents
        profile[team_id] = per_category
    return profile
