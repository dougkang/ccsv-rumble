"""Movement significance. PURE.

In an 18-team league with recency-weighted inputs, most small rank changes are
noise. Without this gate the article would manufacture a causal story for all 18
teams every week, which is the main way the output would read as machine-generated
filler. This classification is what makes FR-019 enforceable.
"""

from __future__ import annotations

from .. import config
from ..models import Movement


def classify_movement(rank_change: int | None) -> Movement:
    """UNAVAILABLE when there is no previous rank, never a zero change."""
    if rank_change is None:
        return Movement.UNAVAILABLE
    if abs(rank_change) >= config.SIGNIFICANT_RANK_CHANGE:
        return Movement.SIGNIFICANT
    return Movement.WITHIN_NOISE
