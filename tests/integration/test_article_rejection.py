"""Content validation rejects fabrications and bad attributions.

These are the checks that matter most: a hallucinated trade passes every
structural check while being worse than a broken page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.article.validate import validate_article
from ccsv_rumble.models import ArticleContent, Movement, TeamNote
from ccsv_rumble.pipeline import execute
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from ccsv_rumble.schedule import RunPlan
from tests.conftest import make_snapshot
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"


@pytest.fixture
def report():
    snapshot = make_snapshot(1)
    ranking = build_ranking([snapshot])
    internal = internal_report.build(
        season=SEASON, week=1, entry_id="entry-001",
        ranking=ranking, events=derive_events(snapshot),
    )
    return publishable_report.build(
        internal=internal, history=[snapshot], is_projection=False
    )


def _notes(report, **overrides) -> tuple[TeamNote, ...]:
    return tuple(
        TeamNote(
            team_id=t.team_id,
            prose=overrides.get(t.team_id, ("Quiet week.",))[0],
            attributed_event_ids=overrides.get(t.team_id, ("", ()))[1]
            if t.team_id in overrides
            else (),
        )
        for t in report.teams
    )


def _article(report, notes=None) -> ArticleContent:
    return ArticleContent(
        headline="Week 1 in review",
        intro="A busy week.",
        outro="Back next week.",
        team_notes=notes if notes is not None else _notes(report),
    )


def test_a_clean_article_passes(report) -> None:
    assert validate_article(_article(report), report).passed


def test_cites_an_event_that_does_not_exist(report) -> None:
    """FR-022 as a set operation -- immune to phrasing."""
    notes = list(_notes(report))
    notes[0] = TeamNote(
        team_id=report.teams[0].team_id,
        prose="A blockbuster trade reshaped the roster.",
        attributed_event_ids=("evt-99-trade-doesnotexist",),
    )
    outcome = validate_article(_article(report, tuple(notes)), report)

    assert not outcome.passed
    assert any(f.check == "event_traceability" for f in outcome.failures)


def test_attributes_a_cause_to_a_team_that_barely_moved(report) -> None:
    """FR-019 as a lookup."""
    noisy = next(
        t for t in report.teams if t.movement is not Movement.SIGNIFICANT
    )
    notes = [
        TeamNote(
            team_id=t.team_id,
            prose="Quiet week.",
            attributed_event_ids=("evt-fake",) if t.team_id == noisy.team_id else (),
        )
        for t in report.teams
    ]
    outcome = validate_article(_article(report, tuple(notes)), report)

    assert not outcome.passed
    assert any(f.check == "noise_attribution" for f in outcome.failures)


def test_discloses_the_ranking_method(report) -> None:
    article = ArticleContent(
        headline="Week 1 in review",
        intro="Their all-play win rate carried them this week.",
        outro="Back next week.",
        team_notes=_notes(report),
    )
    outcome = validate_article(article, report)

    assert not outcome.passed
    assert any(f.check == "no_disclosure" for f in outcome.failures)


def test_uses_a_number_absent_from_the_report(report) -> None:
    notes = list(_notes(report))
    notes[0] = TeamNote(
        team_id=report.teams[0].team_id,
        prose="They put up 1437 points, a league record.",
        attributed_event_ids=(),
    )
    outcome = validate_article(_article(report, tuple(notes)), report)

    assert not outcome.passed
    assert any(f.check == "no_foreign_numbers" for f in outcome.failures)


def test_the_record_string_is_not_a_false_positive(report) -> None:
    """The guaranteed false positive, guarded against.

    Prose naturally reads "at 6-4 they...". A naive numerals scan would flag
    both halves, so `permitted_numbers` decomposes the record.
    """
    team = report.teams[0]
    notes = list(_notes(report))
    notes[0] = TeamNote(
        team_id=team.team_id,
        prose=f"At {team.record} they are right in the hunt.",
        attributed_event_ids=(),
    )
    outcome = validate_article(_article(report, tuple(notes)), report)

    foreign = [f for f in outcome.failures if f.check == "no_foreign_numbers"]
    assert not foreign, f"record string wrongly flagged: {foreign}"


def test_demeaning_language_is_rejected(report) -> None:
    article = ArticleContent(
        headline="Week 1 in review",
        intro="A pathetic showing from the bottom half.",
        outro="Back next week.",
        team_notes=_notes(report),
    )
    outcome = validate_article(article, report)

    assert not outcome.passed
    assert any(f.check == "tone" for f in outcome.failures)


def test_missing_team_coverage_is_rejected(report) -> None:
    outcome = validate_article(
        _article(report, _notes(report)[:5]), report
    )
    assert not outcome.passed
    assert any(f.check == "team_coverage" for f in outcome.failures)


def test_a_rejected_article_is_archived_with_its_reasons(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-027: rejected articles are archived too, so failures are diagnosable."""
    store = ArchiveStore(tmp_path / "archive")
    result = execute(
        RunPlan(SEASON, (1,), (), 1),
        provider=FakeProvider(),
        store=store,
        anthropic_client=FakeAnthropic(behavior="fabricate"),
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )

    assert not result.pages[0].has_article, "a rejected article must not publish"

    archived = store.read_article(SEASON, 1, "entry-001")
    assert archived is not None, "the rejected article must still be archived"
    assert not archived.validation.passed
    assert any(
        f.check == "event_traceability" for f in archived.validation.failures
    )
