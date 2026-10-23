"""Roster-strength prior. PURE -- no I/O of any kind.

It did not used to be. `load_player_values()` lived here and called
`path.open()`, which Principle I forbids outright: the ranking computation MUST
be "free of I/O, network, and filesystem access". Reading moved to
`fetch/projections.py`, where filesystem access belongs, and this module now
receives already-parsed values.

`tests/unit/test_architecture.py` is the mechanism that is supposed to prevent
that drift, and it missed this for the whole life of the violation: it inspected
the import graph against INTERNAL package names, so `import csv` and
`from pathlib import Path` passed unnoticed. It now also rejects filesystem and
network access in a pure package.

TODO(FR-036): the prior's DEFINITION is still the one the design document
rejects -- it sums the whole roster and min-max normalizes to 0-1. Both are
wrong: FR-018 forbids summing bench depth the format cannot deploy, and a
percentile map puts the best team at exactly 1.000 where real EMW tops out near
.90, so blending it against a clustered EMW exaggerates both extremes. The
design document is explicit that RosterPrior IS DraftScore, recomputed from the
current roster, with no second definition of roster strength anywhere. Replaced
in the in-season phase; the file-I/O fix above is independent of it.
"""

from __future__ import annotations

from ..models import Snapshot, TeamId


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
