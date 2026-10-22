"""The week-0 page: User Story 1, the MVP.

Eighteen teams ordered from draft projections, movement unavailable, no figure
from the computation anywhere, and no model involved at any point.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble import config
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch.projection_provider import ProjectionError
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import write_rosters_csv
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"
VALID = Path("tests/fixtures/projections-valid.csv")


@pytest.fixture
def week_zero():
    """Week 0 is acquired from the roster CSV, not from a scoreboard."""
    return {"short_teams": 0, "with_positions": True, "roster_size": 10}


def _run(tmp_path: Path, projections: Path = VALID, client=None, *, state=None):
    state = state or {}
    rosters = write_rosters_csv(
        tmp_path / "rosters.csv",
        roster_size=int(state.get("roster_size", 10)),
        short_teams=int(state.get("short_teams", 0)),
        with_positions=bool(state.get("with_positions", True)),
    )
    return execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=ArchiveStore(tmp_path / "archive"),
        anthropic_client=client,
        generated_at="2026-10-22",
        projections_path=projections,
        rosters_path=rosters,
    )


def test_all_eighteen_teams_appear_in_rank_order(tmp_path: Path, week_zero) -> None:
    """SC-001, FR-005."""
    result = _run(tmp_path, state=week_zero)
    assert result.withheld is None
    assert len(result.pages) == 1

    page = result.pages[0]
    assert page.week == 0
    # Ranks 1..18 exactly once each, which `Ranking` enforces structurally.
    for rank in range(1, config.TEAM_COUNT + 1):
        assert f">{rank}<" in page.html or f">{rank}</" in page.html, f"rank {rank} missing"


def test_movement_is_unavailable_not_zero(tmp_path: Path, week_zero) -> None:
    """FR-006: zero would assert "unchanged", a different and false claim.

    Asserted on the class ATTRIBUTE, not the document -- `move-flat` also
    appears in the inlined stylesheet, where its presence means nothing.
    """
    html = _run(tmp_path, state=week_zero).pages[0].html
    assert html.count('class="move move-new"') == config.TEAM_COUNT
    assert 'class="move move-flat"' not in html, "a team rendered as unchanged at week 0"
    assert 'class="move move-up"' not in html
    assert 'class="move move-down"' not in html


def test_no_number_from_the_computation_reaches_the_page(
    tmp_path: Path, week_zero
) -> None:
    """FR-028, FR-029, SC-004.

    Not as figures, not rounded, not in alt text, tooltips, data attributes, or
    markup comments. The shrink constant must not appear either.
    """
    html = _run(tmp_path, state=week_zero).pages[0].html.lower()
    for forbidden in ("draft_score", "draftscore", "emw", "caw", "all-play", "allplay"):
        assert forbidden not in html, f"{forbidden!r} leaked onto the page"
    # The shrink constant itself.
    assert str(config.DRAFT_SHRINK) not in html


def test_both_algorithm_versions_appear_in_provenance(
    tmp_path: Path, week_zero
) -> None:
    """FR-033: a rank depending on two algorithms cannot be traced by citing one."""
    html = _run(tmp_path, state=week_zero).pages[0].html
    assert f"algorithm={config.ALGORITHM_VERSION}" in html
    assert f"draft-algorithm={config.DRAFT_ALGORITHM_VERSION}" in html


def test_no_model_is_involved(tmp_path: Path, week_zero) -> None:
    """US1's independent test: the ranking table needs no language model.

    The MVP is a complete page by FR-048's definition, with the article section
    omitted entirely rather than stubbed.
    """
    result = _run(tmp_path, client=None, state=week_zero)
    assert result.pages[0].has_article is False
    assert not result.notification.article_failures
    assert "<article" not in result.pages[0].html


def test_the_internal_report_keeps_the_decomposition(tmp_path: Path, week_zero) -> None:
    """FR-034, SC-010: explain any placement from the report alone."""
    _run(tmp_path, state=week_zero)
    store = ArchiveStore(tmp_path / "archive")
    entry_id = store.latest_entry_id(SEASON, 0)
    internal = (store.paths(SEASON, 0, entry_id).internal).read_text(encoding="utf-8")
    assert "draft_score" in internal
    assert "emw_proj" in internal
    assert "caw_proj" in internal
    assert "unprojected_count" in internal


def test_the_projection_snapshot_is_archived(tmp_path: Path, week_zero) -> None:
    """FR-011/FR-012: what replay reads instead of the live file."""
    _run(tmp_path, state=week_zero)
    store = ArchiveStore(tmp_path / "archive")
    entry_id = store.latest_entry_id(SEASON, 0)
    archived = store.read_projections(SEASON, 0, entry_id)
    assert archived is not None
    assert len(archived.projections) == 180
    assert archived.source_id
    # And the verbatim input beside it (Principle III).
    assert store.paths(SEASON, 0, entry_id).raw_projections.is_file()


# --- Coverage refusal ---------------------------------------------------------


def test_a_single_unrankable_team_refuses_to_publish(tmp_path: Path, week_zero) -> None:
    """FR-026/FR-038, per-team floor. The spec's named edge case."""
    with pytest.raises(ProjectionError, match="active slots"):
        _run(tmp_path, state=week_zero, projections=Path("tests/fixtures/projections-sparse-team.csv"))


def test_a_thin_spread_across_every_team_refuses_to_publish(
    tmp_path: Path, week_zero
) -> None:
    """The league-wide floor: what the per-team check alone would miss.

    Every team at 5/6 passes per-team at 0.833 and fails league-wide at 0.95,
    because a gap on all eighteen teams is a source problem.
    """
    with pytest.raises(ProjectionError, match="league-wide"):
        _run(tmp_path, state=week_zero, projections=Path("tests/fixtures/projections-sparse-league.csv"))


def test_missing_projections_at_week_zero_fail_cleanly(
    tmp_path: Path, week_zero
) -> None:
    """A clean Principle II failure, not an AssertionError traceback."""
    with pytest.raises(ProjectionError, match="projection"):
        _run(tmp_path, state=week_zero, projections=tmp_path / "absent.csv")


def test_a_roster_without_positions_trips_the_floor_loudly(
    tmp_path: Path, week_zero
) -> None:
    """Rather than silently ranking by "best six players regardless of position".

    With no position data every player is UTIL-only, so one slot of six fills
    and coverage collapses well under the floor.
    """
    week_zero["with_positions"] = False
    with pytest.raises(ProjectionError):
        _run(tmp_path, state=week_zero)


def test_incomplete_coverage_appears_as_prose_not_a_figure(
    tmp_path: Path, week_zero
) -> None:
    """FR-025 via research D6.

    The caveat must be visible on a rankings-only page: `category_notes` reaches
    only the article prompt, so without a page-level note a reader of the MVP
    page would never learn coverage was incomplete.
    """
    week_zero["roster_size"] = 12  # fixture projects only 10 per team
    html = _run(tmp_path, state=week_zero).pages[0].html

    assert "no projection" in html
    # Prose, in a note -- not a table column, and not a bare count in a cell.
    assert '<p class="note">' in html
    assert "unprojected" not in html.lower(), "an internal field name leaked"


def test_complete_coverage_adds_nothing_to_the_page(tmp_path: Path, week_zero) -> None:
    """The common case must stay silent rather than reassuring the reader."""
    html = _run(tmp_path, state=week_zero).pages[0].html
    assert "no projection" not in html
