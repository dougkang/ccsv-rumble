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
    assert html.count("<section ") == html.count("aria-labelledby") >= 1


def test_page_declares_a_language_and_viewport(html: str) -> None:
    assert '<html lang="en">' in html
    assert 'name="viewport"' in html


def test_no_third_party_resources(html: str) -> None:
    assert not inspect(html).external_refs


def test_stylesheet_is_light_only() -> None:
    """The design philosophy fixes the background at white, and a dark palette
    cannot be expressed in its four colours -- so there is exactly one scheme,
    declared so user-agent chrome does not invert around it."""
    css = stylesheet()
    assert "color-scheme: light" in css
    assert "prefers-color-scheme" not in css


PALETTE = {"#111", "#fff", "#555", "#f5c518"}
FONT_STACK = '"Helvetica Neue", Helvetica, Arial, sans-serif'
_HEX = re.compile(r"#[0-9a-fA-F]{3,6}\b")


def _luminance(hex_colour: str) -> float:
    digits = hex_colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    channels = []
    for i in (0, 2, 4):
        c = int(digits[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _tokens(css: str) -> dict[str, str]:
    root = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert root, "stylesheet declares no :root block"
    return {
        name: value.lower()
        for name, value in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;", root.group(1))
    }


def test_palette_meets_contrast_floor() -> None:
    """Computed from the declared tokens, not asserted in a comment: a token
    edit that drops below 4.5:1 fails here instead of on a reader's phone."""
    css = stylesheet()
    tokens = _tokens(css)

    # Contrast first, so a too-light token reports its ratio rather than
    # tripping the palette check below with a less useful message.
    for fg, bg in (("ink", "paper"), ("muted", "paper"), ("ink", "select")):
        ratio = _contrast(tokens[fg], tokens[bg])
        assert ratio >= 4.5, f"--{fg} on --{bg} is {ratio:.2f}:1"

    assert set(tokens.values()) == PALETTE
    literals = [h.lower() for h in _HEX.findall(css)]
    for value in PALETTE:
        assert literals.count(value) == 1, f"{value} used outside :root"
    assert set(literals) == PALETTE, f"stray colours: {set(literals) - PALETTE}"


def test_every_font_size_meets_the_floor() -> None:
    """Checks every declaration rather than named selectors on purpose: a
    per-selector check passes while a 0.62rem sits under the selector it never
    names. Hence rem only -- a px or em value would slip past the comparison."""
    css = stylesheet()
    sizes = [s.strip() for s in re.findall(r"font-size:\s*([^;}]+)", css)]
    assert sizes, "stylesheet declares no font sizes"
    for size in sizes:
        assert re.fullmatch(r"\d*\.?\d+rem", size), f"font-size {size!r} is not in rem"
        assert float(size[:-3]) >= 0.72, f"font-size {size} is below the 0.72rem floor"
    assert not re.search(r"(?<![-\w])font\s*:", css), "font: shorthand can hide a size"


def test_single_font_stack() -> None:
    css = stylesheet()
    assert css.count("--font:") == 1
    for family in re.findall(r"font-family:\s*([^;}]+)", css):
        assert family.strip() in ("var(--font)", FONT_STACK), family


def test_no_banned_primitives() -> None:
    """Every element is a rectangle, nothing floats, nothing is fetched."""
    css = stylesheet().lower()
    banned = ("border-radius", "box-shadow", "gradient", "italic", "@font-face", "@import", "url(")
    found = [b for b in banned if b in css]
    assert not found, f"stylesheet uses banned primitives: {found}"


def test_stylesheet_ships_unescaped(html: str) -> None:
    """The inlined <style> must be the stylesheet byte for byte. Autoescaping
    once turned the quotes around "Helvetica Neue" into &#34;, which a <style>
    element does not decode -- the font-family was silently invalid and every
    page fell back to Times while every test that reads stylesheet() passed."""
    css = stylesheet()
    assert "<" not in css, "a '<' in the stylesheet can open or close a tag"
    for page in (html, render_index(season="2026-27", weeks=[1, 2, 3])):
        shipped = re.search(r"<style>(.*?)</style>", page, re.S)
        assert shipped, "page has no inlined <style>"
        assert shipped.group(1) == css


def test_wide_content_scrolls_inside_its_own_container() -> None:
    """The body must never scroll horizontally on a narrow phone."""
    css = stylesheet()
    assert "overflow-x: auto" in css


def test_index_is_also_accessible() -> None:
    structure = inspect(render_index(season="2026-27", weeks=[1, 2, 3]))
    assert structure.h1_count == 1
    assert not structure.external_refs
