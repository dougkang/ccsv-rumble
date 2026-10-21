"""Notable event derivation. PURE.

`event_id` is DETERMINISTIC, derived from (week, type, subject) -- never a UUID.
A changing id would break both the golden-file render test and the article's
`attributed_event_ids` round-trip, since the article references events by id.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from .. import config
from ..models import (
    CategoryLine,
    EventType,
    NotableEvent,
    Snapshot,
    TeamId,
)

#: Categories a standout week is measured in. Ratio categories are excluded --
#: a high percentage on three attempts is not a performance.
_STANDOUT_CATEGORIES: tuple[str, ...] = ("pts", "reb", "ast", "stl", "blk", "tpm")


def make_event_id(week: int, event_type: EventType, subject: str) -> str:
    """Stable id for one event. Same inputs always yield the same id."""
    digest = hashlib.sha256(
        f"{week}|{event_type.value}|{subject}".encode()
    ).hexdigest()[:12]
    return f"evt-{week:02d}-{event_type.value}-{digest}"


def _baseline(player_history: Sequence[CategoryLine], category: str) -> float:
    values = [getattr(line, category) for line in player_history]
    if not values:
        return 0.0
    return sum(values) / len(values)


def standout_performances(
    current: Snapshot,
    prior_weeks: Sequence[Snapshot],
) -> list[NotableEvent]:
    """Players whose week beat their own season baseline by a declared multiple.

    Declared rule, not subjective judgment (FR-009): the same week always yields
    the same set. Players below the games-played floor are excluded to keep
    small samples out.
    """
    history: dict[str, list[CategoryLine]] = {}
    for snapshot in prior_weeks:
        for pw in snapshot.player_weeks:
            history.setdefault(pw.player_id, []).append(pw.line)

    events: list[NotableEvent] = []
    for pw in sorted(current.player_weeks, key=lambda p: (p.player_id, p.team_id)):
        if pw.line.games_played < config.STANDOUT_MIN_GAMES:
            continue
        past = history.get(pw.player_id, [])
        if not past:
            continue
        beaten: list[tuple[str, int, float]] = []
        for category in _STANDOUT_CATEGORIES:
            baseline = _baseline(past, category)
            value = getattr(pw.line, category)
            if baseline > 0 and value >= baseline * config.STANDOUT_BASELINE_MULTIPLE:
                beaten.append((category, value, baseline))
        if not beaten:
            continue
        category, value, baseline = max(beaten, key=lambda row: row[1] / row[2])
        events.append(
            NotableEvent(
                event_id=make_event_id(
                    current.week, EventType.STANDOUT_PERFORMANCE, pw.player_id
                ),
                type=EventType.STANDOUT_PERFORMANCE,
                team_ids=(pw.team_id,),
                player_name=pw.name,
                summary=(
                    f"{pw.name} posted {value} {category} in week {current.week}, "
                    f"well above a season average of {baseline:.1f}"
                ),
                occurred_on=current.week_end,
                detail={"category": category, "value": value},
            )
        )
    return events


def transaction_events(current: Snapshot) -> list[NotableEvent]:
    """Trades, adds, drops, and availability changes already present in the data."""
    events: list[NotableEvent] = []
    for txn in sorted(
        current.transactions, key=lambda t: (t.occurred_on, t.transaction_id)
    ):
        subject = txn.player_name or txn.transaction_id
        if txn.type is EventType.TRADE:
            summary = f"{subject} was traded"
        elif txn.type is EventType.ADD:
            summary = f"{subject} was added"
        elif txn.type is EventType.DROP:
            summary = f"{subject} was dropped"
        else:
            summary = f"{subject} had an availability change"
        events.append(
            NotableEvent(
                event_id=make_event_id(current.week, txn.type, txn.transaction_id),
                type=txn.type,
                team_ids=tuple(sorted(txn.team_ids)),
                player_name=txn.player_name,
                summary=summary,
                occurred_on=txn.occurred_on,
            )
        )
    return events


def injury_events(current: Snapshot) -> list[NotableEvent]:
    """Availability changes visible on the roster (status fields like OUT/IL)."""
    notable_statuses = {"O", "OUT", "IL", "INJ", "GTD", "DTD"}
    events: list[NotableEvent] = []
    for team_id in sorted(current.rosters):
        for slot in sorted(current.rosters[team_id], key=lambda s: s.player_id):
            status = (slot.status or "").strip().upper()
            if status and status in notable_statuses:
                events.append(
                    NotableEvent(
                        event_id=make_event_id(
                            current.week, EventType.INJURY_STATUS, slot.player_id
                        ),
                        type=EventType.INJURY_STATUS,
                        team_ids=(team_id,),
                        player_name=slot.name,
                        summary=f"{slot.name} listed as {status}",
                        occurred_on=current.week_end,
                        detail={"status": status},
                    )
                )
    return events


def derive_events(
    current: Snapshot, prior_weeks: Sequence[Snapshot] = ()
) -> tuple[NotableEvent, ...]:
    """All notable events for the week, in a deterministic order."""
    events = (
        injury_events(current)
        + transaction_events(current)
        + standout_performances(current, prior_weeks)
    )
    events.sort(key=lambda e: (e.type.value, e.event_id))
    return tuple(events)


def events_for_team(
    events: Sequence[NotableEvent], team_id: TeamId
) -> tuple[NotableEvent, ...]:
    return tuple(e for e in events if team_id in e.team_ids)
