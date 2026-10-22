"""User Story 4: a disputed week-0 ranking reproduces weeks later.

This is the regression test for a real defect. Projections used to be read at
RANK time from the live file, so editing `data/projections.csv` silently changed
the result of replaying a past week -- and week 0 could not replay at all,
because its ranking never came from `build_ranking`.
"""

from __future__ import annotations

import socket
from dataclasses import replace
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.cli import _render_archived
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import make_post_draft_snapshot, write_rosters_csv
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"
FIXTURE = Path("tests/fixtures/projections-valid.csv")


@pytest.fixture
def week_zero():
    """Week 0 is acquired from the roster CSV, not a scoreboard."""
    return None


@pytest.fixture
def no_network(monkeypatch):
    """Any socket construction fails -- a real fetch cannot hide here."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("replay attempted a network connection")

    monkeypatch.setattr(socket, "socket", _forbidden)


@pytest.fixture
def published(tmp_path: Path, week_zero) -> tuple[ArchiveStore, str, Path]:
    """Publish week 0 from a COPY of the fixture the test can later edit."""
    live = tmp_path / "projections.csv"
    live.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    rosters = write_rosters_csv(tmp_path / "rosters.csv")

    store = ArchiveStore(tmp_path / "archive")
    result = execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-22",
        projections_path=live,
        rosters_path=rosters,
    )
    assert result.pages, "setup failed: week 0 did not publish"
    return store, result.pages[0].html, live


def test_replay_reproduces_the_published_page(published, no_network) -> None:
    """SC-003: byte-identical, offline."""
    store, original_html, _ = published
    page = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
    assert page.html == original_html


def test_editing_the_live_projections_file_cannot_change_a_past_page(
    published, no_network
) -> None:
    """The defect this feature closes, as an executable assertion (FR-013).

    Replay reads the ARCHIVED snapshot. On the old code it read the live file,
    so this edit would have changed a page that was already published.
    """
    store, original_html, live = published

    # Revise every projection sharply -- enough to reorder the table if it were read.
    rows = live.read_text(encoding="utf-8").splitlines()
    header, body = rows[0], rows[1:]
    revised = [header]
    for index, line in enumerate(body):
        cells = line.split(",")
        # cells[4] is `pts`; invert the ordering so any live read would reorder.
        cells[4] = f"{(len(body) - index) * 0.37:.1f}"
        revised.append(",".join(cells))
    live.write_text("\n".join(revised) + "\n", encoding="utf-8")

    page = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
    assert page.html == original_html, (
        "replay changed after the projections file was edited -- it is reading "
        "the live file rather than the archived snapshot"
    )


def test_replay_is_stable_across_repeated_runs(published, no_network) -> None:
    store, _, _ = published
    first = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
    second = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
    assert first.html == second.html


def test_replay_invokes_no_model(published, no_network, monkeypatch) -> None:
    """Principle I's regeneration rule: no nondeterministic stage on replay."""
    import ccsv_rumble.article.generate as generate

    def _forbidden(*args, **kwargs):
        raise AssertionError("replay invoked article generation")

    monkeypatch.setattr(generate, "generate_article", _forbidden)
    page = _render_archived(store=published[0], season=SEASON, week=0,
                            generated_at="2026-10-22", entry_id=None)
    assert page.has_article is False


def test_replay_carries_both_algorithm_versions(published, no_network) -> None:
    """A replayed page must be traceable to the same pair that produced it."""
    store, _, _ = published
    html = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None).html
    assert "algorithm=v1" in html
    assert "draft-algorithm=draft-v1" in html


def test_a_week_zero_entry_without_projections_refuses_to_replay(
    tmp_path: Path, week_zero, no_network
) -> None:
    """Better to refuse than to silently reproduce a DIFFERENT ranking.

    Week 0's ranking is a pure function of the projection snapshot, so without
    one there is nothing to reproduce from -- and `build_ranking` over an empty
    history would quietly invent a different table.
    """
    from ccsv_rumble.fetch.projection_provider import ProjectionError

    store = ArchiveStore(tmp_path / "archive")
    paths = store.create_entry(SEASON, 0, "entry-001")
    store.write_snapshot(paths, replace(make_post_draft_snapshot(), week=0))

    with pytest.raises(ProjectionError, match="unreproducible"):
        _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
