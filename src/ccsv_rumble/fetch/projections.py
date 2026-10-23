"""Projection acquisition and parsing.

Structured like `yahoo.py`: pure parsing helpers first, then the class that does
I/O. The pure half is unit-testable without touching a filesystem, and the I/O
half is the only part that is not.

ONE TRAP, and it is the go/no-go on any projection source:

    FG and FT must arrive as MAKES AND ATTEMPTS, never as a percentage.

A source publishing `FG%` is rejected outright rather than partially used. Given
`.458` and nothing else, attempts are unrecoverable -- it is consistent with
11/24 and with 22/48, which aggregate into a team week differently. Inferring
attempts from minutes or shot-rate estimates would make exactly the two
categories the week-0 category profile depends on quietly fictional. FR-010
makes this a rejection, not a degradation.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import PerGameLine, PlayerProjection, ProjectionSnapshot, ValidationError
from .projection_provider import ProjectionError

#: Per-game counting categories, in the schema's column order.
_COUNTING = ("pts", "reb", "ast", "stl", "blk", "tpm", "to")
#: Makes/attempts columns. Their absence is the rejection FR-010 demands.
_RATIO = ("fgm", "fga", "ftm", "fta")
REQUIRED_COLUMNS = ("player_id", "projected_games", *_COUNTING, *_RATIO)

#: Column names that mean the source published a percentage instead.
_PERCENTAGE_COLUMNS = frozenset(
    {"fg_pct", "ft_pct", "fg%", "ft%", "fgpct", "ftpct", "fg_percent", "ft_percent"}
)


# --- Pure parsing -------------------------------------------------------------


def assert_makes_and_attempts(columns: list[str]) -> None:
    """Reject a percentage-only source before any row is read (FR-010)."""
    lowered = {c.strip().lower() for c in columns}
    offending = sorted(lowered & _PERCENTAGE_COLUMNS)
    if offending:
        raise ProjectionError(
            f"projection source publishes percentages {offending} instead of makes "
            "and attempts. Attempts cannot be recovered from a percentage -- '.458' "
            "is consistent with 11/24 and 22/48, which aggregate differently -- so "
            "this source is rejected rather than partially used (FR-010). Supply "
            f"{list(_RATIO)} per player."
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in lowered]
    if missing:
        raise ProjectionError(
            f"projection source is missing required columns: {missing}. "
            f"Expected at least {list(REQUIRED_COLUMNS)}."
        )


def _number(row: dict[str, Any], key: str, player_id: str) -> float:
    raw = str(row.get(key, "")).strip()
    if raw == "":
        raise ProjectionError(f"{player_id}: column {key!r} is empty")
    try:
        return float(raw)
    except ValueError as exc:
        raise ProjectionError(f"{player_id}: column {key!r} is not a number: {raw!r}") from exc


def parse_rows(rows: list[dict[str, Any]]) -> tuple[PlayerProjection, ...]:
    """Raw rows -> projections. Pure; no filesystem access."""
    if not rows:
        raise ProjectionError("projection source returned no rows")
    assert_makes_and_attempts(list(rows[0].keys()))

    out: list[PlayerProjection] = []
    seen: set[str] = set()
    for row in rows:
        player_id = str(row.get("player_id", "")).strip()
        if not player_id:
            raise ProjectionError("a projection row has no player_id")
        if player_id in seen:
            raise ProjectionError(f"duplicate projection for {player_id}")
        seen.add(player_id)

        games_raw = _number(row, "projected_games", player_id)
        if games_raw != int(games_raw):
            raise ProjectionError(
                f"{player_id}: projected_games must be a whole number, got {games_raw}"
            )

        try:
            line = PerGameLine(**{k: _number(row, k, player_id) for k in (*_COUNTING, *_RATIO)})
            out.append(
                PlayerProjection(
                    player_id=player_id,
                    name=str(row.get("name", "")).strip(),
                    per_game=line,
                    projected_games=int(games_raw),
                )
            )
        except ValidationError as exc:
            # Surface WHICH player failed -- a bare invariant message is not
            # actionable against a 180-row file.
            raise ProjectionError(f"{player_id}: {exc}") from exc
    return tuple(out)


def parse_positions(raw: str) -> tuple[str, ...]:
    """Split the `positions` column. Empty is permitted but means UTIL-only."""
    return tuple(p.strip().upper() for p in str(raw or "").split(",") if p.strip())


# --- Provider -----------------------------------------------------------------


class LocalFileProjectionProvider:
    """Reads a maintainer-curated file. Filesystem access is confined here.

    Chosen over automated retrieval because no licensed API supplies makes and
    attempts, and scraping a site to power a public page is both fragile and a
    terms question (research D1). The origin is still external -- a source the
    maintainer has rights to read -- and `source_id` records which.
    """

    def __init__(self, path: Path, source_id: str = "") -> None:
        self._path = path
        self._source_id = source_id or f"local:{path.name}"

    def source_id(self) -> str:
        return self._source_id

    def fetch_projections(self, season: str, target_week: int) -> list[dict[str, Any]]:
        if not self._path.is_file():
            raise ProjectionError(
                f"projection file not found: {self._path}. Week-0 ranking cannot be "
                "computed without projections; see contracts/projection-source.md "
                "for the required schema."
            )
        with self._path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]


def acquire(
    provider: LocalFileProjectionProvider,
    season: str,
    target_week: int,
    *,
    now: datetime | None = None,
) -> ProjectionSnapshot:
    """Fetch, validate, and normalize into an archivable snapshot.

    `retrieved_at` is injected rather than read here so the caller controls the
    only time-varying value, consistent with how rendering handles `generated_at`.
    """
    rows = provider.fetch_projections(season, target_week)
    return ProjectionSnapshot(
        source_id=provider.source_id(),
        retrieved_at=now or datetime.now(UTC),
        target_week=target_week,
        projections=parse_rows(rows),
        raw_source="raw-projections.csv",
    )
