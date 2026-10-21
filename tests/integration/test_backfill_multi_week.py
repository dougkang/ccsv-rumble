"""The highest-value integration test (plan.md flags it as such).

Weeks 1-2 archived; weeks 3, 4, 5 missing. The article stage fails on week 4 only.

This exercises FR-039, FR-042, and FR-044 simultaneously. The subtlest assertion
is the ordering one: week 4's movement must compare against WEEK 3, not against
week 2's published ranking. Getting that wrong produces plausible-looking but
wrong movement numbers on every backfilled page.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.pipeline import execute
from ccsv_rumble.publish import StagedSite
from ccsv_rumble.schedule import RunPlan
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"


@pytest.fixture
def seeded(tmp_path: Path, fake_snapshot_builder) -> ArchiveStore:
    """Archive weeks 1-2 so that 3-5 register as gaps."""
    store = ArchiveStore(tmp_path / "archive")
    provider = FakeProvider()
    plan = RunPlan(season=SEASON, gap_weeks=(1, 2), recheck_weeks=(), current_week=2)
    execute(
        plan,
        provider=provider,
        store=store,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )
    return store


def run_backfill(store: ArchiveStore, tmp_path: Path, client):
    plan = RunPlan(season=SEASON, gap_weeks=(3, 4, 5), recheck_weeks=(), current_week=5)
    return execute(
        plan,
        provider=FakeProvider(),
        store=store,
        anthropic_client=client,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )


def test_backfills_every_missing_week_in_ascending_order(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    client = FakeAnthropic(fail_weeks={4})
    result = run_backfill(seeded, tmp_path, client)

    assert result.weeks_published == [3, 4, 5], "weeks must publish in ascending order"
    assert client.calls == [3, 4, 5], "articles must be generated in week order"


def test_week_four_movement_compares_against_week_three(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    """The subtle one.

    If the implementation compared each backfilled week against the most recent
    PUBLISHED ranking (week 2) instead of the preceding week, week 4's movement
    would be measured from the wrong baseline. Assert it against an independent
    computation of week 3's ranks.
    """
    from ccsv_rumble.rank.score import build_ranking

    run_backfill(seeded, tmp_path, FakeAnthropic(fail_weeks={4}))

    history = [seeded.latest_entry(SEASON, w) for w in (1, 2, 3)]
    week3_ranks = {e.team_id: e.rank for e in build_ranking(history).entries}

    week4_internal = seeded.read_publishable_raw(
        SEASON, 4, seeded.latest_entry_id(SEASON, 4)
    )
    assert week4_internal is not None
    for team in week4_internal["teams"]:
        assert team["previous_rank"] == week3_ranks[team["team_id"]], (
            f"team {team['team_id']} week-4 previous_rank is "
            f"{team['previous_rank']}, but week 3 ranked it "
            f"{week3_ranks[team['team_id']]}"
        )


def test_failing_week_degrades_alone_and_the_rest_keep_articles(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    result = run_backfill(seeded, tmp_path, FakeAnthropic(fail_weeks={4}))
    by_week = {page.week: page for page in result.pages}

    assert by_week[3].has_article, "week 3 should keep its article"
    assert by_week[5].has_article, "week 5 should keep its article"
    assert not by_week[4].has_article, "week 4's article failed; omit it"

    # FR-030a: omitted entirely, with no placeholder explaining the absence.
    assert "write-up" not in by_week[4].html.lower()
    assert "unavailable" not in by_week[4].html.lower()


def test_one_bad_week_does_not_abort_the_backfill(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    result = run_backfill(seeded, tmp_path, FakeAnthropic(fail_weeks={4}))
    assert 5 in result.weeks_published, "the loop must continue past a failed week"


def test_all_weeks_stage_into_a_single_push(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    """FR-042: every affected page lands in one commit, or none does."""
    result = run_backfill(seeded, tmp_path, FakeAnthropic(fail_weeks={4}))

    staged = StagedSite()
    for page in result.pages:
        staged.add_page(page)
    staged.finalize(season=SEASON, weeks=result.weeks_published)

    assert {"week-03.html", "week-04.html", "week-05.html"} <= set(staged.files)
    assert "index.html" in staged.files
    assert "robots.txt" in staged.files


def test_backfill_is_reported(seeded: ArchiveStore, tmp_path: Path) -> None:
    """FR-043 and FR-030: the page is silent, so this is the only signal."""
    result = run_backfill(seeded, tmp_path, FakeAnthropic(fail_weeks={4}))
    note = result.notification

    assert sorted(note.backfilled_weeks) == [3, 4]
    assert any("week 4" in failure for failure in note.article_failures)
    assert note.has_content


def test_backfilled_pages_are_labelled_and_not_presented_as_current(
    seeded: ArchiveStore, tmp_path: Path
) -> None:
    """FR-041: a page published late must not read as though it were current."""
    result = run_backfill(seeded, tmp_path, FakeAnthropic())
    by_week = {page.week: page for page in result.pages}

    assert "published late" in by_week[3].html
    assert "published late" not in by_week[5].html, "week 5 is the current week"


def test_week_bounds_are_sane(seeded: ArchiveStore) -> None:
    snapshot = seeded.latest_entry(SEASON, 1)
    assert snapshot.week_start <= snapshot.week_end
    assert snapshot.week_start >= date(2026, 1, 1)
