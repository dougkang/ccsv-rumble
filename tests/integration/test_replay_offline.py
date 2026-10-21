"""Principle I's regeneration rule, as an executable assertion.

Replay must make no network call and invoke no model. This is the test most
likely to rot: a stray import that constructs a client at module load will fail
it, which is the point.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.cli import _render_archived
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"


@pytest.fixture
def archived(tmp_path: Path, fake_snapshot_builder) -> ArchiveStore:
    store = ArchiveStore(tmp_path / "archive")
    execute(
        RunPlan(SEASON, (1, 2, 3), (), 3),
        provider=FakeProvider(),
        store=store,
        anthropic_client=FakeAnthropic(),
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )
    return store


@pytest.fixture
def no_network(monkeypatch):
    """Any socket construction fails -- a real fetch cannot hide here."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("replay attempted a network connection")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)


@pytest.fixture
def no_model(monkeypatch):
    """Constructing an Anthropic client fails."""
    import ccsv_rumble.article.generate as generate

    def _forbidden(*args, **kwargs):
        raise AssertionError("replay invoked the article generator")

    monkeypatch.setattr(generate, "generate_article", _forbidden)


def test_replay_works_with_no_network_and_no_model(
    archived: ArchiveStore, no_network, no_model
) -> None:
    page = _render_archived(archived, SEASON, 2, "2026-10-27", None)

    assert page.week == 2
    assert "Standings" in page.html


def test_replay_reuses_the_archived_article(
    archived: ArchiveStore, no_network, no_model
) -> None:
    page = _render_archived(archived, SEASON, 2, "2026-10-27", None)
    assert page.has_article, "the archived article must be reused, not regenerated"


def test_replay_is_byte_identical_across_invocations(
    archived: ArchiveStore, no_network, no_model
) -> None:
    first = _render_archived(archived, SEASON, 2, "2026-10-27", None)
    second = _render_archived(archived, SEASON, 2, "2026-10-27", None)
    assert first.html == second.html


def test_replay_resolves_the_requested_entry(
    archived: ArchiveStore, tmp_path: Path, fake_snapshot_builder, no_network, no_model
) -> None:
    """`--entry` and `--latest` must address different snapshots after a correction."""
    fake_snapshot_builder["seed_shift"][2] = 500
    execute(
        RunPlan(SEASON, (), (2,), 3),
        provider=FakeProvider(),
        store=archived,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )
    assert archived.list_entry_ids(SEASON, 2) == ["entry-001", "entry-002"]

    as_published = _render_archived(archived, SEASON, 2, "2026-10-27", "entry-001")
    corrected = _render_archived(archived, SEASON, 2, "2026-10-27", None)

    assert as_published.entry_id == "entry-001"
    assert corrected.entry_id == "entry-002"
    assert as_published.html != corrected.html, (
        "--latest should show the corrected week; that is why verify must "
        "resolve the published entry_id instead"
    )


def test_replay_matches_execute_output(
    tmp_path: Path, fake_snapshot_builder, no_network
) -> None:
    """SC-005, asserted against a page `execute` actually produced.

    `execute` threads previous_ranks forward week by week; `_render_archived`
    computes the prior week's ranks in one shot. They agree only because
    previous_ranks annotates movement without influencing the computed order.
    This is the test that catches it if that invariant ever breaks -- comparing
    replay against replay would not.
    """
    store = ArchiveStore(tmp_path / "archive")
    result = execute(
        RunPlan(SEASON, (1, 2, 3, 4), (), 4),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )
    published = {page.week: page.html for page in result.pages}

    for week in (2, 3, 4):
        replayed = _render_archived(store, SEASON, week, "2026-10-27", None).html
        assert replayed == published[week], (
            f"week {week}: replay differs from what execute produced"
        )


def test_incomplete_archive_fails_loudly_rather_than_fetching(
    tmp_path: Path, no_network
) -> None:
    empty = ArchiveStore(tmp_path / "empty")
    with pytest.raises(Exception, match="no archived entry|missing snapshot"):
        _render_archived(empty, SEASON, 2, "2026-10-27", None)
