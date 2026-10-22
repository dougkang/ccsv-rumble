"""Roster acquisition. LEAGUE data, kept separate from projections.

Nothing acquired rosters before this: `LeagueDataProvider.fetch_rosters` existed
and was never called, and `build_snapshot` never set the field. The week-0
ranking is a pure function of rosters plus projections, so it could not run
against the live league no matter how complete the ranking code was.

ONE THING NOT TO DO, because it is the obvious shortcut and it is wrong:
do not derive rosters from the projections file. FR-025 requires that a rostered
player with NO projection be counted rather than dropped, and carried into the
internal report as a confidence caveat. A projections file omits exactly those
players by construction, so using it as the roster source would peg the
unprojected count at zero forever and quietly delete the caveat. The two inputs
disagree about who exists, which is precisely why both are needed.

Structured like `projections.py`: pure parsing first, then the I/O.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import PlayerSlot, TeamId
from .projection_provider import ProjectionError

REQUIRED_COLUMNS = ("team_id", "player_id", "name")


class RosterError(ProjectionError):
    """Roster acquisition or validation failure.

    Subclasses `ProjectionError` so the CLI's existing handler maps it to a
    Principle II failure -- publish nothing, exit non-zero, notify -- without a
    second except clause that could be forgotten.
    """


# --- Pure parsing -------------------------------------------------------------


def parse_positions(raw: Any) -> tuple[str, ...]:
    """Split the `positions` column. Empty is permitted but means UTIL-only."""
    return tuple(p.strip().upper() for p in str(raw or "").split(",") if p.strip())


@dataclass(frozen=True)
class RosterCapture:
    """Rosters plus the team names that came with them.

    Team names are carried here because week 0 has no scoreboard to read them
    from, and without them the published page would label every team by its id
    (`t.01`) -- technically correct and useless to a reader.
    """

    rosters: dict[TeamId, tuple[PlayerSlot, ...]]
    team_names: dict[TeamId, str]

    def __len__(self) -> int:
        return len(self.rosters)


def parse_rows(
    rows: list[dict[str, Any]], known_team_ids: set[TeamId] | None = None
) -> RosterCapture:
    """Raw rows -> rosters by team. Pure; no filesystem access."""
    if not rows:
        raise RosterError("roster source returned no rows")

    columns = {(c or "").strip().lower() for c in rows[0]}
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise RosterError(
            f"roster source is missing required columns: {missing}. "
            f"Expected at least {list(REQUIRED_COLUMNS)}."
        )

    by_team: dict[TeamId, list[PlayerSlot]] = {}
    names: dict[TeamId, str] = {}
    owner: dict[str, TeamId] = {}
    for row in rows:
        team_id = str(row.get("team_id", "")).strip()
        player_id = str(row.get("player_id", "")).strip()
        if not team_id or not player_id:
            raise RosterError(f"roster row is missing team_id or player_id: {row!r}")
        if known_team_ids is not None and team_id not in known_team_ids:
            raise RosterError(
                f"roster references unknown team {team_id!r}; known teams are "
                f"{sorted(known_team_ids)}"
            )
        if player_id in owner:
            # A player on two rosters means the capture is stale or duplicated,
            # and silently keeping one would credit his production to the wrong
            # team for the whole week.
            raise RosterError(
                f"player {player_id} appears on both {owner[player_id]} and "
                f"{team_id}; a player cannot be on two rosters"
            )
        owner[player_id] = team_id
        team_name = str(row.get("team_name", "") or "").strip()
        if team_name:
            names.setdefault(team_id, team_name)
        by_team.setdefault(team_id, []).append(
            PlayerSlot(
                player_id=player_id,
                name=str(row.get("name", "")).strip(),
                team_id=team_id,
                status=str(row.get("status", "") or "").strip(),
                positions=parse_positions(row.get("positions")),
            )
        )

    # Sorted so the snapshot is byte-stable regardless of input row order --
    # otherwise two captures of the same league would diff as a correction.
    return RosterCapture(
        rosters={
            team_id: tuple(sorted(slots, key=lambda s: s.player_id))
            for team_id, slots in sorted(by_team.items())
        },
        # Fall back to the id so a capture without names still renders.
        team_names={tid: names.get(tid, tid) for tid in sorted(by_team)},
    )


# --- Provider -----------------------------------------------------------------


def load(path: Path, known_team_ids: set[TeamId] | None = None) -> RosterCapture:
    """Read and parse the roster file. The only filesystem access here.

    Deliberately does NOT reject a team below `DRAFT_ROSTER_SIZE`. Ingest reports
    what the league looks like; the lifecycle gate decides what that means. A
    short roster is how `PRE_DRAFT` is detected, so refusing it here would turn
    a normal pre-draft state into an acquisition failure.
    """
    if not path.is_file():
        raise RosterError(
            f"roster file not found: {path}. The week-0 ranking needs rosters; "
            "capture them with tools/yahoo_roster_capture.js, or see "
            "specs/002-draft-ranking-week-0/research.md D12."
        )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            {(k or "").strip().lower(): v for k, v in row.items()}
            for row in csv.DictReader(handle)
        ]
    return parse_rows(rows, known_team_ids)
