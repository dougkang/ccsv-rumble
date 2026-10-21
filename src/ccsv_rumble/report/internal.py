"""The internal report: full ranking detail. Archived, NEVER published.

Carries the exact constants used, so an algorithm change can be compared
before/after on archived data as the constitution requires.
"""

from __future__ import annotations

from collections.abc import Sequence

from .. import config
from ..models import InternalReport, NotableEvent, Ranking


def declared_constants() -> dict[str, float]:
    """Snapshot of every constant that affects the score, for the archive."""
    return {
        "emw_weight": config.EMW_WEIGHT,
        "caw_weight": config.CAW_WEIGHT,
        "shrinkage_k": float(config.SHRINKAGE_K),
        "recency_half_life_weeks": float(config.RECENCY_HALF_LIFE_WEEKS),
        "significant_rank_change": float(config.SIGNIFICANT_RANK_CHANGE),
        "standout_baseline_multiple": config.STANDOUT_BASELINE_MULTIPLE,
        "standout_min_games": float(config.STANDOUT_MIN_GAMES),
        "matchup_win_threshold": config.MATCHUP_WIN_THRESHOLD,
    }


def build(
    *,
    season: str,
    week: int,
    entry_id: str,
    ranking: Ranking,
    events: Sequence[NotableEvent],
) -> InternalReport:
    return InternalReport(
        season=season,
        week=week,
        entry_id=entry_id,
        algorithm_version=config.ALGORITHM_VERSION,
        ranking=ranking,
        events=tuple(events),
        constants=declared_constants(),
    )
