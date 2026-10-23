"""Archiving the projection snapshot, and the round-trip that replay depends on.

FR-011/FR-012: without an archived snapshot, editing the projections file
silently changes the result of replaying a past week.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveError, ArchiveStore
from ccsv_rumble.models import (
    DraftPick,
    DraftResults,
    PerGameLine,
    PlayerProjection,
    PlayerSlot,
    ProjectionSnapshot,
)

from ..conftest import make_post_draft_snapshot

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
SEASON = "2026-27"


def _snapshot() -> ProjectionSnapshot:
    return ProjectionSnapshot(
        source_id="test-source",
        retrieved_at=NOW,
        target_week=0,
        projections=(
            PlayerProjection(
                "nba.p.1", "A", PerGameLine(pts=24.1, fgm=8.6, fga=18.8, ftm=4.1, fta=4.7), 4
            ),
            PlayerProjection("nba.p.2", "B", PerGameLine(pts=9.3, fgm=3.4, fga=7.9), 3),
        ),
        raw_source="raw-projections.csv",
    )


def test_projection_snapshot_round_trips(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    paths = store.create_entry(SEASON, 0, "entry-001")
    original = _snapshot()
    store.write_projections(paths, original, raw_text="player_id,pts\nnba.p.1,24.1\n")

    reloaded = store.read_projections(SEASON, 0, "entry-001")
    assert reloaded == original, "snapshot did not survive the round trip"


def test_per_game_precision_survives_archiving(tmp_path: Path) -> None:
    """Fractional per-game values must come back fractional.

    If they round-tripped through an int type, 8.6 would return as 8 and every
    replayed ranking would differ from the published one.
    """
    store = ArchiveStore(tmp_path)
    paths = store.create_entry(SEASON, 0, "entry-001")
    store.write_projections(paths, _snapshot())
    reloaded = store.read_projections(SEASON, 0, "entry-001")
    assert reloaded is not None
    first = reloaded.by_player()["nba.p.1"]
    assert first.per_game.fgm == 8.6
    assert first.per_game.fga == 18.8


def test_raw_input_is_archived_verbatim(tmp_path: Path) -> None:
    """Principle III: the pre-parse bytes, so a parser bug is diagnosable."""
    store = ArchiveStore(tmp_path)
    paths = store.create_entry(SEASON, 0, "entry-001")
    raw = "player_id,pts\nnba.p.1,24.1\n"
    store.write_projections(paths, _snapshot(), raw_text=raw)
    assert paths.raw_projections.read_text(encoding="utf-8") == raw


def test_a_correction_appends_an_entry_rather_than_overwriting(tmp_path: Path) -> None:
    """FR-013: a revised source never alters an already-published ranking."""
    store = ArchiveStore(tmp_path)
    first = store.create_entry(SEASON, 0, store.next_entry_id(SEASON, 0))
    store.write_projections(first, _snapshot())

    revised = ProjectionSnapshot(
        source_id="test-source",
        retrieved_at=datetime(2026, 10, 23, tzinfo=UTC),
        target_week=0,
        projections=(
            PlayerProjection("nba.p.1", "A", PerGameLine(pts=30.0, fgm=11.0, fga=20.0), 4),
        ),
    )
    second_id = store.next_entry_id(SEASON, 0)
    assert second_id == "entry-002"
    store.write_projections(store.create_entry(SEASON, 0, second_id), revised)

    # entry-001 is untouched: the published week stays reproducible.
    original = store.read_projections(SEASON, 0, "entry-001")
    assert original is not None
    assert original.by_player()["nba.p.1"].per_game.pts == 24.1
    assert store.read_projections(SEASON, 0, "entry-002") == revised


def test_entries_are_never_overwritten(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    store.create_entry(SEASON, 0, "entry-001")
    with pytest.raises(ArchiveError, match="append-only"):
        store.create_entry(SEASON, 0, "entry-001")


def test_absent_projections_read_as_none(tmp_path: Path) -> None:
    """Weeks archived before this feature have no snapshot; replay must still work."""
    store = ArchiveStore(tmp_path)
    store.create_entry(SEASON, 1, "entry-001")
    assert store.read_projections(SEASON, 1, "entry-001") is None
    assert store.read_draft_results(SEASON, 1, "entry-001") is None


def test_draft_results_round_trip(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    paths = store.create_entry(SEASON, 0, "entry-001")
    results = DraftResults(
        season=SEASON,
        picks=(DraftPick(1, "t.01", "nba.p.1", "A"), DraftPick(2, "t.02", "nba.p.2", "B")),
        is_complete=True,
    )
    store.write_draft_results(paths, results)
    assert store.read_draft_results(SEASON, 0, "entry-001") == results


def test_roster_positions_round_trip_as_a_tuple(tmp_path: Path) -> None:
    """Regression: JSON has no tuple, so a naive decode yields a list.

    A list-vs-tuple mismatch makes a reloaded snapshot unequal to the original,
    which would make `archive/diff.py` report an upstream correction on EVERY
    run and append a useless entry each time.
    """
    store = ArchiveStore(tmp_path)
    paths = store.create_entry(SEASON, 0, "entry-001")
    original = make_post_draft_snapshot()
    store.write_snapshot(paths, original)

    reloaded = store.entry(SEASON, 0, "entry-001")
    slot = reloaded.rosters["t.01"][0]
    assert isinstance(slot.positions, tuple), "positions decoded as a list, not a tuple"
    assert isinstance(original.rosters["t.01"][0], PlayerSlot)
    assert reloaded.rosters == original.rosters
    assert reloaded.completed_scored_weeks == original.completed_scored_weeks
