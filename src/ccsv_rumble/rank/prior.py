"""Optional roster-strength prior from a local projections file. PURE.

The algorithm doc s4 needs per-player 9-cat z-score values for the cold-start
weeks. No licensed API offers them, and scraping a site to power a public page is
both fragile and a terms question -- so this reads an optional local CSV the
maintainer populates by hand.

When the file is absent the algorithm doc's own rule applies: publish NO ranking
until week 2 and show standings only. A confidently wrong week-0 ranking is worse
for a casual audience than an absent one.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import Snapshot, TeamId


def load_player_values(path: Path) -> dict[str, float]:
    """player_id -> projected per-game 9-cat value. Returns {} when absent."""
    if not path.is_file():
        return {}
    values: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            player_id = (row.get("player_id") or "").strip()
            raw = (row.get("value") or "").strip()
            if not player_id or not raw:
                continue
            try:
                values[player_id] = float(raw)
            except ValueError:
                continue
    return values


def roster_prior(
    snapshot: Snapshot, player_values: dict[str, float]
) -> dict[TeamId, float] | None:
    """Per-team prior mapped onto a 0-1 scale, or None when unavailable.

    None is meaningfully different from a dict of zeros: it means "no projection
    signal", which the caller uses to let realized performance carry full weight
    rather than dragging every team toward an invented prior.
    """
    if not player_values or not snapshot.rosters:
        return None

    raw: dict[TeamId, float] = {}
    for team_id, slots in snapshot.rosters.items():
        raw[team_id] = sum(player_values.get(slot.player_id, 0.0) for slot in slots)

    if not raw:
        return None

    low = min(raw.values())
    high = max(raw.values())
    if high == low:
        return dict.fromkeys(sorted(raw), 0.5)
    return {team_id: (value - low) / (high - low) for team_id, value in sorted(raw.items())}
