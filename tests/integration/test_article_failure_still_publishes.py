"""FR-029: an article failure degrades the page, it does not suppress the run.

A failure here that blocks publication is a misreading of Principle II -- the
constitution's "complete page is defined per feature" clause exists for exactly
this case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"


def run_with(client, tmp_path: Path):
    store = ArchiveStore(tmp_path / "archive")
    return execute(
        RunPlan(SEASON, (1,), (), 1),
        provider=FakeProvider(),
        store=store,
        anthropic_client=client,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )


@pytest.mark.parametrize("behavior", ["raise", "refusal", "max_tokens", "fabricate"])
def test_every_article_failure_mode_still_publishes_rankings(
    behavior: str, tmp_path: Path, fake_snapshot_builder
) -> None:
    result = run_with(FakeAnthropic(behavior=behavior), tmp_path)

    assert result.has_pages, f"{behavior}: the rankings page must still publish"
    page = result.pages[0]
    assert not page.has_article
    assert "Standings" in page.html, "rankings content must survive"
    assert result.notification.article_failures, "the failure must be reported"


def test_a_refusal_does_not_crash_the_run(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """A refusal is HTTP 200 with empty content.

    Code that reads content[0] unconditionally would raise IndexError here and
    turn a degraded publish into a failed run.
    """
    result = run_with(FakeAnthropic(behavior="refusal"), tmp_path)

    assert result.has_pages
    assert any("declined" in f for f in result.notification.article_failures)


def test_no_api_key_means_rankings_only_with_no_failure_reported(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """Absent configuration is not a failure -- nothing to report."""
    result = run_with(None, tmp_path)

    assert result.has_pages
    assert not result.pages[0].has_article
    assert not result.notification.article_failures


def test_the_page_gives_no_sign_an_article_was_expected(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-030a: silent omission.

    This is exactly why the notification channel is load-bearing -- a reader
    cannot distinguish a failed article from a week with no article planned.
    """
    result = run_with(FakeAnthropic(behavior="raise"), tmp_path)
    html = result.pages[0].html.lower()

    for placeholder in ("no write-up", "unavailable", "could not", "coming soon"):
        assert placeholder not in html, f"page hints at the missing article: {placeholder}"


def test_a_good_article_does_publish(tmp_path: Path, fake_snapshot_builder) -> None:
    """The control case -- otherwise the tests above would pass trivially."""
    result = run_with(FakeAnthropic(behavior="ok"), tmp_path)

    assert result.pages[0].has_article
    assert not result.notification.article_failures
    assert "in review" in result.pages[0].html
