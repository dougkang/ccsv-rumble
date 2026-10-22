"""Deterministic JSON serialization for archived models.

Every dump sorts keys. Unsorted serialization is one of the documented ways
nondeterminism leaks into output (research.md s8), and the archive is what the
golden-file test replays from.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from ..models import (
    Article,
    ArticleContent,
    CategoryLine,
    DraftPick,
    DraftResults,
    EventType,
    Matchup,
    PerGameLine,
    PlayerProjection,
    PlayerSlot,
    PlayerWeek,
    ProjectionSnapshot,
    Snapshot,
    Team,
    TeamNote,
    Transaction,
    ValidationFailure,
    ValidationOutcome,
)


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def to_jsonable(value: Any) -> Any:
    return _encode(value)


def dumps(value: Any) -> str:
    """Serialize with sorted keys and a trailing newline."""
    return json.dumps(_encode(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# --- Decoders ----------------------------------------------------------------


def _line(d: dict[str, Any]) -> CategoryLine:
    return CategoryLine(**d)


def _per_game(d: dict[str, Any]) -> PerGameLine:
    return PerGameLine(**d)


def _player_slot(d: dict[str, Any]) -> PlayerSlot:
    """Decode a roster slot, coercing `positions` back to a TUPLE.

    JSON has no tuple, so a naive `PlayerSlot(**d)` yields a list and the
    round-tripped slot no longer equals the original. That matters more than it
    looks: `archive/diff.py` compares normalized data to detect upstream
    corrections, so a list-vs-tuple mismatch would report a correction on every
    single run and append a useless archive entry each time.
    """
    return PlayerSlot(
        player_id=d["player_id"],
        name=d["name"],
        team_id=d["team_id"],
        status=d.get("status", ""),
        positions=tuple(d.get("positions", ())),
    )


def snapshot_from_dict(d: dict[str, Any]) -> Snapshot:
    return Snapshot(
        entry_id=d["entry_id"],
        acquired_at=datetime.fromisoformat(d["acquired_at"]),
        season=d["season"],
        week=d["week"],
        week_start=date.fromisoformat(d["week_start"]),
        week_end=date.fromisoformat(d["week_end"]),
        teams=tuple(Team(**t) for t in d["teams"]),
        category_totals={k: _line(v) for k, v in d["category_totals"].items()},
        matchups=tuple(Matchup(**m) for m in d.get("matchups", [])),
        rosters={
            k: tuple(_player_slot(p) for p in v) for k, v in d.get("rosters", {}).items()
        },
        transactions=tuple(
            Transaction(
                transaction_id=t["transaction_id"],
                type=EventType(t["type"]),
                occurred_on=date.fromisoformat(t["occurred_on"]),
                team_ids=tuple(t["team_ids"]),
                player_name=t.get("player_name"),
            )
            for t in d.get("transactions", [])
        ),
        player_weeks=tuple(
            PlayerWeek(
                player_id=p["player_id"],
                name=p["name"],
                team_id=p["team_id"],
                week=p["week"],
                line=_line(p["line"]),
            )
            for p in d.get("player_weeks", [])
        ),
        stat_category_map=d.get("stat_category_map", {}),
        supersedes=d.get("supersedes"),
        raw_source=d.get("raw_source", ""),
        completed_scored_weeks=d.get("completed_scored_weeks", 0),
    )


def projection_snapshot_from_dict(d: dict[str, Any]) -> ProjectionSnapshot:
    """Decode the archived projection snapshot that replay reads (FR-012)."""
    return ProjectionSnapshot(
        source_id=d["source_id"],
        retrieved_at=datetime.fromisoformat(d["retrieved_at"]),
        target_week=d["target_week"],
        projections=tuple(
            PlayerProjection(
                player_id=p["player_id"],
                name=p.get("name", ""),
                per_game=_per_game(p["per_game"]),
                projected_games=p["projected_games"],
            )
            for p in d.get("projections", [])
        ),
        raw_source=d.get("raw_source", ""),
    )


def draft_results_from_dict(d: dict[str, Any]) -> DraftResults:
    return DraftResults(
        season=d["season"],
        picks=tuple(DraftPick(**p) for p in d.get("picks", [])),
        is_complete=d.get("is_complete", False),
    )


def article_from_dict(d: dict[str, Any]) -> Article:
    content = None
    if d.get("content"):
        c = d["content"]
        content = ArticleContent(
            headline=c["headline"],
            intro=c["intro"],
            outro=c["outro"],
            team_notes=tuple(
                TeamNote(
                    team_id=n["team_id"],
                    prose=n["prose"],
                    attributed_event_ids=tuple(n.get("attributed_event_ids", [])),
                )
                for n in c["team_notes"]
            ),
        )
    v = d["validation"]
    return Article(
        week=d["week"],
        model=d["model"],
        generated_at=datetime.fromisoformat(d["generated_at"]),
        content=content,
        validation=ValidationOutcome(
            passed=v["passed"],
            checked_at=datetime.fromisoformat(v["checked_at"]),
            failures=tuple(ValidationFailure(**f) for f in v.get("failures", [])),
        ),
    )
