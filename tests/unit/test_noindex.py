"""FR-051 / FR-053 / SC-011: crawler directives and no sitemap.

An unlisted URL is obscurity, not access control. These directives are the
convention-honoring half of that posture; FR-024 (no PII) is the half that
actually protects anyone.
"""

from __future__ import annotations

from ccsv_rumble.publish import StagedSite
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_index, render_page, robots_txt
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_snapshot


def _page_html() -> str:
    snapshot = make_snapshot(1)
    ranking = build_ranking([snapshot])
    report = internal_report.build(
        season="2026-27", week=1, entry_id="entry-001",
        ranking=ranking, events=derive_events(snapshot),
    )
    public = publishable_report.build(
        internal=report, history=[snapshot], is_projection=False
    )
    return render_page(
        report=public, entry_id="entry-001", generated_at="2026-10-27"
    ).html


def test_every_page_carries_noindex() -> None:
    assert 'name="robots"' in _page_html()
    assert "noindex" in _page_html()


def test_the_index_carries_noindex_too() -> None:
    html = render_index(season="2026-27", weeks=[1, 2])
    assert "noindex" in html


def test_robots_txt_disallows_everything() -> None:
    content = robots_txt()
    assert "User-agent: *" in content
    assert "Disallow: /" in content


def test_the_site_publishes_no_sitemap() -> None:
    staged = StagedSite()
    staged.finalize(season="2026-27", weeks=[1, 2])
    assert not any("sitemap" in name.lower() for name in staged.files)


def test_robots_is_always_staged() -> None:
    staged = StagedSite()
    staged.finalize(season="2026-27", weeks=[1])
    assert "robots.txt" in staged.files
