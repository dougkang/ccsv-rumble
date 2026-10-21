"""Constitution Principle IV: the page must be usable by everyone in the league.

Accessibility is not polish here -- the page is read on phones by a congregation
of varied ages and devices, and a weekly page nobody can read is a weekly page
that failed.
"""

from __future__ import annotations

import re

import pytest

from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_index, render_page, stylesheet
from ccsv_rumble.render.validate import inspect
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_snapshot


@pytest.fixture
def html() -> str:
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


def test_exactly_one_h1(html: str) -> None:
    assert inspect(html).h1_count == 1


def test_heading_levels_are_not_skipped(html: str) -> None:
    levels = [int(m) for m in re.findall(r"<h([1-6])", html)]
    assert levels, "page has no headings"
    assert levels[0] == 1
    for previous, current in zip(levels, levels[1:], strict=False):
        assert current <= previous + 1, (
            f"heading jumps from h{previous} to h{current}"
        )


def test_ranking_table_headers_are_scoped(html: str) -> None:
    """Screen readers need scope to associate cells with their headers."""
    structure = inspect(html)
    assert structure.table_count >= 1
    # Five column headers plus one row header per team.
    assert structure.scoped_headers >= 5 + 18


def test_table_has_a_caption(html: str) -> None:
    assert "<caption>" in html


def test_landmarks_are_present(html: str) -> None:
    for landmark in ("<header>", "<main>", "<footer>"):
        assert landmark in html, f"missing landmark {landmark}"


def test_sections_are_labelled(html: str) -> None:
    assert html.count("aria-labelledby") >= 2


def test_page_declares_a_language_and_viewport(html: str) -> None:
    assert '<html lang="en">' in html
    assert 'name="viewport"' in html


def test_no_third_party_resources(html: str) -> None:
    assert not inspect(html).external_refs


def test_stylesheet_supports_both_colour_schemes() -> None:
    css = stylesheet()
    assert "color-scheme" in css
    assert "prefers-color-scheme: dark" in css


def test_wide_content_scrolls_inside_its_own_container() -> None:
    """The body must never scroll horizontally on a narrow phone."""
    css = stylesheet()
    assert "overflow-x: auto" in css


def test_index_is_also_accessible() -> None:
    structure = inspect(render_index(season="2026-27", weeks=[1, 2, 3]))
    assert structure.h1_count == 1
    assert not structure.external_refs
