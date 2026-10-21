"""Correction detection.

Compares a re-fetched week against its latest archived entry using NORMALIZED
values only -- never raw bytes.

Yahoo responses carry volatile per-request fields (request ids, timestamps,
ordering). A byte comparison would report a correction on every single run and
append a junk archive entry each time, which is both noise and an ever-growing
repository. Only a difference in the data the ranking actually consumes counts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Snapshot
from .serde import to_jsonable


@dataclass(frozen=True)
class WeekDiff:
    changed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.changed


def compare(existing: Snapshot, fetched: Snapshot) -> WeekDiff:
    """Return whether `fetched` represents a real correction to `existing`."""
    reasons: list[str] = []

    if to_jsonable(existing.category_totals) != to_jsonable(fetched.category_totals):
        for team_id in sorted(
            set(existing.category_totals) | set(fetched.category_totals)
        ):
            before = existing.category_totals.get(team_id)
            after = fetched.category_totals.get(team_id)
            if to_jsonable(before) != to_jsonable(after):
                reasons.append(f"category totals changed for team {team_id}")

    if to_jsonable(existing.rosters) != to_jsonable(fetched.rosters):
        reasons.append("rosters changed")

    if to_jsonable(existing.transactions) != to_jsonable(fetched.transactions):
        reasons.append("transactions changed")

    if to_jsonable(existing.player_weeks) != to_jsonable(fetched.player_weeks):
        reasons.append("player box scores changed")

    return WeekDiff(changed=bool(reasons), reasons=tuple(reasons))
