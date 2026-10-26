"""Text raw inputs are archived verbatim, and quarantined in their own format."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ccsv_rumble.archive.store import ArchiveStore

ROWS = "week,team_id,pts\n1,t.01,352\n1,t.03,383\n"


def test_raw_text_is_written_byte_for_byte(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    paths = store.create_entry("2026-27", 1, "entry-001")
    store.write_raw_text(paths.raw_matchups, ROWS)
    assert paths.raw_matchups.name == "raw-matchups.csv"
    assert paths.raw_matchups.read_text(encoding="utf-8") == ROWS


def test_raw_text_is_still_scrubbed(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    paths = store.create_entry("2026-27", 1, "entry-001")
    store.write_raw_text(paths.raw_matchups, "note\nsk-ant-abcdefghijklmnop\n")
    assert "sk-ant-" not in paths.raw_matchups.read_text(encoding="utf-8")


def test_quarantined_text_stays_outside_the_entries(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    target = store.quarantine_text(
        "2026-27", 1, datetime(2026, 10, 26, 16, 0, tzinfo=UTC), ROWS
    )
    assert target == tmp_path / "_quarantine" / "2026-27" / "week-01-20261026T160000Z.csv"
    assert target.read_text(encoding="utf-8") == ROWS
    assert not store.has_week("2026-27", 1)
