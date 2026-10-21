"""Principle II: a failure before the report publishes NOTHING.

The asymmetry that matters: a failure upstream of the report blocks publication
entirely, while a failure in the optional article degrades one page. Both paths
must be covered by tests (constitution Quality Gates item 3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch.provider import ProviderError
from ccsv_rumble.models import ValidationError
from ccsv_rumble.pipeline import execute
from ccsv_rumble.publish import StagedSite, publish
from ccsv_rumble.render.validate import PageInvalid, validate_page
from ccsv_rumble.schedule import RunPlan
from tests.conftest import make_snapshot
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"


def test_a_fetch_failure_produces_no_pages(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    store = ArchiveStore(tmp_path / "archive")
    provider = FakeProvider()
    provider.fail_weeks = {1}

    with pytest.raises(ProviderError):
        execute(
            RunPlan(SEASON, (1,), (), 1),
            provider=provider,
            store=store,
            anthropic_client=None,
            generated_at="2026-10-27",
            projections_path=tmp_path / "missing.csv",
        )

    assert not store.has_week(SEASON, 1), "a failed fetch must archive nothing"


def test_a_mid_backfill_failure_publishes_nothing_at_all(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """All-or-nothing: weeks 1-2 succeeding does not license a partial publish."""
    store = ArchiveStore(tmp_path / "archive")
    provider = FakeProvider()
    provider.fail_weeks = {3}

    with pytest.raises(ProviderError):
        execute(
            RunPlan(SEASON, (1, 2, 3), (), 3),
            provider=provider,
            store=store,
            anthropic_client=FakeAnthropic(),
            generated_at="2026-10-27",
            projections_path=tmp_path / "missing.csv",
        )
    # The exception propagates before any push, so the site is untouched.


def test_a_short_league_is_rejected_rather_than_ranked(tmp_path: Path) -> None:
    """A snapshot missing teams must fail loudly, not rank 17 teams silently."""
    from ccsv_rumble.models import Snapshot

    full = make_snapshot(1)
    with pytest.raises(ValidationError, match="expected 18 teams"):
        Snapshot(
            entry_id=full.entry_id,
            acquired_at=full.acquired_at,
            season=full.season,
            week=full.week,
            week_start=full.week_start,
            week_end=full.week_end,
            teams=full.teams[:-1],
            category_totals=full.category_totals,
        )


def test_an_invalid_page_blocks_publication() -> None:
    from ccsv_rumble.models import PublishedPage

    broken = PublishedPage(
        season=SEASON, week=1, entry_id="entry-001",
        algorithm_version="v1", has_article=False, path="week-01.html",
        html="<html><body><p>TODO: fill this in</p></body></html>",
    )
    with pytest.raises(PageInvalid) as excinfo:
        validate_page(broken)

    message = str(excinfo.value)
    assert "h1" in message or "placeholder" in message


def test_a_page_fetching_third_party_resources_is_rejected() -> None:
    """Principle IV: no third-party script, font, or stylesheet at page load."""
    from ccsv_rumble.models import PublishedPage

    page = PublishedPage(
        season=SEASON, week=1, entry_id="entry-001",
        algorithm_version="v1", has_article=False, path="week-01.html",
        html=(
            '<html><head><meta name="robots" content="noindex">'
            '<link href="https://fonts.example.com/x.css"></head>'
            "<body><h1>Rankings</h1><table><tr><th scope='col'>Rank</th></tr>"
            "</table></body></html>"
        ),
    )
    with pytest.raises(PageInvalid, match="third-party"):
        validate_page(page)


def test_publish_to_an_unreachable_remote_raises(tmp_path: Path) -> None:
    """Exit code 4: the previous site stays intact."""
    from ccsv_rumble.publish import PublishError

    staged = StagedSite()
    staged.files["index.html"] = "<html></html>"

    with pytest.raises(PublishError):
        publish(
            staged,
            repository="does-not-exist/nope",
            branch="pages",
            token=None,
            commit_message="test",
            workdir=tmp_path,
        )
