"""Draft results. LEAGUE data, needed only by the recap.

The ranking never touches this. That split is deliberate and load-bearing: the
week-0 page publishes from rosters and projections alone, so a missing or
malformed draft board costs the article and nothing else (FR-049).

Two things are enforced here rather than left to the prompt.

**Completeness.** A partial board is treated as unavailable, because a recap
written from half a draft would confidently describe a draft that did not
happen -- and unlike a missing article, a wrong one is not visibly wrong to a
reader.

**Team identity.** The captured board names teams the way the league page does
(`🥭 smoothie's team`), while every other stage keys on `t.01`. Resolving that
join HERE, once, is what keeps display names out of the prompt: the model is
given canonical ids, so it cannot invent a `team_id` that the article
validator's coverage check would then reject. A name that does not resolve
makes the whole board unusable -- a recap that silently omits a team is worse
than no recap.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import config
from ..models import DraftPick, DraftResults, TeamId
from .projection_provider import ProjectionError

REQUIRED_COLUMNS = ("overall", "player_id", "player_name", "team_name")


class DraftError(ProjectionError):
    """Draft acquisition or validation failure.

    Subclasses `ProjectionError` only so an unexpected one cannot escape the
    CLI's handlers as a traceback. In normal operation it never reaches the
    caller: `load_or_none` swallows it, because FR-049 makes an unusable draft
    board a reason to omit the article, not to fail the run.
    """


def parse_rows(
    rows: list[dict[str, Any]], season: str, name_to_id: Mapping[str, TeamId]
) -> DraftResults:
    """Raw rows -> DraftResults keyed on canonical team ids.

    Pure; no filesystem access. `name_to_id` maps the board's display names to
    the ids the rest of the pipeline uses, and is required rather than optional
    so the join can never be skipped by accident.
    """
    if not rows:
        raise DraftError("draft source returned no rows")

    columns = {(c or "").strip().lower() for c in rows[0]}
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise DraftError(f"draft source is missing columns: {missing}")

    picks: list[DraftPick] = []
    unresolved: set[str] = set()
    for row in rows:
        try:
            overall = int(str(row.get("overall", "")).strip())
        except ValueError as exc:
            raise DraftError(f"unparseable pick number in {row!r}") from exc

        name = str(row.get("team_name", "")).strip()
        team_id = name_to_id.get(name)
        if team_id is None:
            unresolved.add(name)
            continue

        picks.append(
            DraftPick(
                pick_number=overall,
                team_id=team_id,
                player_id=str(row.get("player_id", "")).strip(),
                player_name=str(row.get("player_name", "")).strip(),
                positions=tuple(
                    p.strip()
                    for p in str(row.get("positions", "")).split(",")
                    if p.strip()
                ),
                nba_team=str(row.get("nba_team", "")).strip(),
            )
        )

    if unresolved:
        raise DraftError(
            f"draft board names teams the roster capture does not know: "
            f"{sorted(unresolved)}. Both must come from the same league."
        )

    picks.sort(key=lambda p: p.pick_number)

    # A finished draft is a contiguous 1..N with no gaps and no repeats, AND it
    # is the right size: every team holding exactly `DRAFT_ROSTER_SIZE` picks.
    #
    # The size check is what makes this honest. Contiguity alone accepts a draft
    # PAUSED at the end of a round -- 54 picks is contiguous from 1, divides by
    # the team count, and touches all 18 teams -- so on its own it would report
    # a third of a draft as a finished one, which is exactly the failure this
    # function exists to prevent. The league drafts active slots plus bench and
    # leaves IL empty, so a complete board is 18 x 10.
    numbers = [p.pick_number for p in picks]
    per_team = Counter(p.team_id for p in picks)
    complete = (
        numbers == list(range(1, len(numbers) + 1))
        and len(numbers) == config.TEAM_COUNT * config.DRAFT_ROSTER_SIZE
        and len(per_team) == config.TEAM_COUNT
        and set(per_team.values()) == {config.DRAFT_ROSTER_SIZE}
    )

    return DraftResults(season=season, picks=tuple(picks), is_complete=complete)


def load_or_none(
    path: Path, season: str, team_names: Mapping[TeamId, str]
) -> DraftResults | None:
    """Read the draft board, or None when it cannot be used.

    Returns None rather than raising, on purpose. FR-049: if draft results are
    unavailable or incomplete the run publishes the ranking and omits the
    article. Raising here would turn a degraded page into a failed run, which is
    the opposite of what the spec asks for.

    `team_names` is the roster capture's `{team_id: display_name}`, inverted
    here to resolve the board's names.
    """
    if not path.is_file():
        return None

    name_to_id = {name: team_id for team_id, name in team_names.items()}
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [
                {(k or "").strip().lower(): v for k, v in row.items()}
                for row in csv.DictReader(handle)
            ]
        results = parse_rows(rows, season, name_to_id)
    # csv.Error is NOT a ValueError: a malformed row would otherwise escape and
    # crash the run, which is precisely what FR-049 forbids.
    except (DraftError, csv.Error, OSError, ValueError):
        return None
    return results if results.is_complete else None
