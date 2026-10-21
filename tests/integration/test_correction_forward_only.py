"""Corrections change the archive and future rankings -- never a published page.

FR-046/047/048/049 look contradictory until the `entry-NNN` layout is in place:
a week holds multiple entries, ranking reads the LATEST, and a published page
records the one it was built from so replay reproduces it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"


@pytest.fixture
def store(tmp_path: Path) -> ArchiveStore:
    return ArchiveStore(tmp_path / "archive")


def run(store: ArchiveStore, tmp_path: Path, plan: RunPlan):
    return execute(
        plan,
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )


def test_unchanged_week_creates_no_new_entry(
    store: ArchiveStore, tmp_path: Path, fake_snapshot_builder
) -> None:
    """The guard against junk entries.

    Yahoo payloads carry volatile per-request fields. A byte comparison would
    report a correction on every run and append a directory each time.
    """
    run(store, tmp_path, RunPlan(SEASON, (1, 2, 3), (), 3))
    assert store.list_entry_ids(SEASON, 2) == ["entry-001"]

    # Re-check week 2 with identical upstream data.
    run(store, tmp_path, RunPlan(SEASON, (), (2,), 3))
    assert store.list_entry_ids(SEASON, 2) == ["entry-001"], (
        "re-fetching an unchanged week must not append an entry"
    )


def test_a_real_correction_appends_an_entry_and_leaves_the_original(
    store: ArchiveStore, tmp_path: Path, fake_snapshot_builder
) -> None:
    run(store, tmp_path, RunPlan(SEASON, (1, 2, 3), (), 3))
    original = store.entry(SEASON, 2, "entry-001")

    fake_snapshot_builder["seed_shift"][2] = 500  # upstream revises week 2
    result = run(store, tmp_path, RunPlan(SEASON, (), (2,), 3))

    assert store.list_entry_ids(SEASON, 2) == ["entry-001", "entry-002"]
    assert store.entry(SEASON, 2, "entry-001") == original, (
        "entry-001 must be byte-identical afterward; archives are append-only"
    )
    assert store.entry(SEASON, 2, "entry-002").supersedes == "entry-001"
    assert any("week 2" in c for c in result.notification.corrections)


def test_ranking_reads_the_latest_entry(
    store: ArchiveStore, tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-047: corrected data feeds current and future rankings."""
    run(store, tmp_path, RunPlan(SEASON, (1, 2, 3), (), 3))
    before = store.latest_entry(SEASON, 2).category_totals

    fake_snapshot_builder["seed_shift"][2] = 500
    run(store, tmp_path, RunPlan(SEASON, (), (2,), 3))

    after = store.latest_entry(SEASON, 2).category_totals
    assert after != before
    assert store.latest_entry_id(SEASON, 2) == "entry-002"


def test_a_correction_does_not_republish_the_corrected_week(
    store: ArchiveStore, tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-048, and the reason correction and backfill are separate code paths.

    Week 2 is already archived, so it is NOT a gap. A run that only re-checks it
    must publish nothing for week 2.
    """
    run(store, tmp_path, RunPlan(SEASON, (1, 2, 3), (), 3))

    fake_snapshot_builder["seed_shift"][2] = 500
    result = run(store, tmp_path, RunPlan(SEASON, (), (2,), 3))

    assert 2 not in result.weeks_published, (
        "a corrected week must not be republished; only MISSING weeks publish"
    )


def test_published_page_records_the_entry_it_used(
    store: ArchiveStore, tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-049 -- the mechanism that keeps SC-005 true after a correction."""
    result = run(store, tmp_path, RunPlan(SEASON, (1, 2), (), 2))
    page = next(p for p in result.pages if p.week == 2)

    assert page.entry_id == "entry-001"
    assert f"provenance: entry={page.entry_id}" in page.html
