"""Each article note is headed by its standings line, with prose beneath.

Neither golden file covers this: both render with `article=None`, so the whole
article section is absent from them. Without these assertions the note markup
has no test at all.

What the head line must carry is the same three facts the table does -- rank,
team name, and week-over-week movement -- so a reader scrolling the write-up
never has to scroll back to the table to know who moved where.
"""

from __future__ import annotations

import re

from ccsv_rumble.models import ArticleContent, TeamNote
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_page
from ccsv_rumble.render.validate import validate_page
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_snapshot


def _report_with_movement():
    """Two weeks, so `rank_change` is a real number rather than None.

    A single-week history makes every team "new", which would let a regression
    that dropped the movement span entirely still pass.
    """
    history = [make_snapshot(1), make_snapshot(2)]
    first = build_ranking(history[:1])
    ranking = build_ranking(
        history, previous_ranks={e.team_id: e.rank for e in first.entries}
    )
    internal = internal_report.build(
        season="2026-27", week=2, entry_id="entry-001",
        ranking=ranking, events=derive_events(history[-1], history[:-1]),
    )
    return publishable_report.build(
        internal=internal, history=history, is_projection=False
    )


def _render(report, *, prose: str = "A steady week."):
    article = ArticleContent(
        headline="Week 2 in review",
        intro="A busy week.",
        outro="Back next week.",
        team_notes=tuple(
            TeamNote(team_id=t.team_id, prose=prose, attributed_event_ids=())
            for t in report.teams
        ),
    )
    return render_page(
        report=report, entry_id="entry-001", generated_at="2026-11-03",
        article=article,
    ).html


def test_each_note_is_headed_by_rank_team_and_movement() -> None:
    report = _report_with_movement()
    html = _render(report)

    for team in report.teams:
        head = (
            f'<p class="team-note-head"><span class="note-rank">{team.rank}.</span> '
            f"<strong>{team.team_name}</strong> "
            f'<span class="note-move '
        )
        assert head in html, f"no standings line for {team.team_name} in its note"


def test_the_prose_is_a_separate_paragraph_from_the_head() -> None:
    """The ask was content on the next line, not trailing the team name."""
    html = _render(report := _report_with_movement(), prose="Distinct prose here.")
    assert report.teams
    assert (
        '<p class="team-note-head">' in html
        and "</p>\n    <p>Distinct prose here.</p>" in html
    ), "prose is not in its own paragraph beneath the head line"


def test_the_note_movement_matches_the_table_for_every_team() -> None:
    """One source of truth. A note disagreeing with the table is worse than
    either being absent, because the reader cannot tell which one is wrong.
    """
    report = _report_with_movement()
    html = _render(report)

    table = {
        team_id: label
        for team_id, label in re.findall(
            r'<td>([^<]*)</td>\s*<td>[^<]*</td>\s*<td>[^<]*</td>\s*'
            r'<td class="move move-\w+">([^<]*)</td>',
            html,
        )
    }
    notes = dict(
        re.findall(
            r'<strong>([^<]*)</strong> <span class="note-move move-\w+">([^<]*)</span>',
            html,
        )
    )
    assert notes, "no note movement spans rendered"
    for name, label in notes.items():
        assert table.get(name) == label, (
            f"{name}: table says {table.get(name)!r}, its note says {label!r}"
        )


def test_the_note_head_adds_no_number_the_table_does_not_have() -> None:
    """Strict disclosure: the head line repeats published facts, nothing new.

    Scanned on the rank and move spans rather than the whole head, because a
    team name may legitimately contain digits -- the fixture's are "Team 09"
    and the real league has "#14th Scariest Team".
    """
    report = _report_with_movement()
    html = _render(report)
    section = html.split('id="writeup-heading"', 1)[1]
    heads = re.findall(r'<p class="team-note-head">(.*?)</p>', section)
    assert len(heads) == len(report.teams)

    allowed = {str(t.rank) for t in report.teams}
    allowed |= {
        str(abs(t.rank_change)) for t in report.teams if t.rank_change is not None
    }
    figures = re.findall(
        r'<span class="note-rank">([^<]*)</span>|'
        r'<span class="note-move move-\w+">([^<]*)</span>',
        section,
    )
    assert figures
    for rank_text, move_text in figures:
        for number in re.findall(r"\d+(?:\.\d+)?", rank_text + " " + move_text):
            assert number in allowed, f"note head carries a foreign number: {number}"


def test_the_page_still_passes_its_own_screens_with_notes_rendered() -> None:
    """The disclosure and accessibility screens run over the new markup too."""
    validate_page(
        render_page(
            report=(report := _report_with_movement()),
            entry_id="entry-001",
            generated_at="2026-11-03",
            article=ArticleContent(
                headline="Week 2 in review",
                intro="A busy week.",
                outro="Back next week.",
                team_notes=tuple(
                    TeamNote(team_id=t.team_id, prose="Fine week.",
                             attributed_event_ids=())
                    for t in report.teams
                ),
            ),
        )
    )
