"""The draft recap's prompt and screens: FR-043, FR-045, FR-046, FR-047.

The recap is the one article that is *supposed* to be full of numbers -- pick
after pick after pick -- so the numerals screen has to be widened for it. These
tests pin down exactly how far: every pick and round number the model was shown
is allowed, and nothing else. An invented stat line still has to be caught,
because that is the failure the screen exists for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ccsv_rumble import config
from ccsv_rumble.article.prompt import (
    DRAFT_SYSTEM_PROMPT,
    build_draft_user_message,
)
from ccsv_rumble.article.validate import draft_permitted_numbers, validate_draft_recap
from ccsv_rumble.fetch.draft import parse_rows
from ccsv_rumble.fetch.projections import LocalFileProjectionProvider
from ccsv_rumble.fetch.projections import acquire as acquire_projections
from ccsv_rumble.models import ArticleContent, DraftResults, TeamNote
from ccsv_rumble.rank import draft_score as draft_scoring
from ccsv_rumble.rank import projected as projected_grid
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import DISPLAY_NAMES, make_post_draft_snapshot

FIXTURE = Path("tests/fixtures/projections-valid.csv")
NAME_TO_ID = {name: tid for tid, name in DISPLAY_NAMES.items()}


def _report():
    """A real week-0 publishable report, built the way the pipeline builds it."""
    snapshot = make_post_draft_snapshot()
    projections = acquire_projections(
        LocalFileProjectionProvider(FIXTURE, source_id="fixture"),
        "2026-27",
        0,
        now=datetime(2026, 10, 22, 12, 0, tzinfo=UTC),
    )
    grid = projected_grid.build_projected_grid(snapshot.rosters, projections)
    ranking = draft_scoring.build_draft_ranking(draft_scoring.score(grid), week=0)
    internal = internal_report.build(
        season="2026-27", week=0, entry_id="entry-001",
        ranking=ranking, events=derive_events(snapshot),
    )
    return publishable_report.build(
        internal=internal, history=[snapshot], is_projection=True
    )


def _board(report, rounds: int = 10) -> DraftResults:
    """A snake board over the report's actual teams."""
    team_ids = [t.team_id for t in report.teams]
    rows = []
    overall = 0
    for rnd in range(1, rounds + 1):
        order = team_ids if rnd % 2 else list(reversed(team_ids))
        for team_id in order:
            overall += 1
            rows.append(
                {
                    "overall": str(overall),
                    "player_id": f"nba.p.{overall}",
                    "player_name": f"Player {overall}",
                    "nba_team": "LAL",
                    "positions": "G",
                    "team_name": DISPLAY_NAMES[team_id],
                }
            )
    return parse_rows(rows, "2026-27", NAME_TO_ID)


def _content(report, *, intro: str, prose: str = "A sensible draft.") -> ArticleContent:
    return ArticleContent(
        headline="Draft night in the books",
        intro=intro,
        outro="Tip-off cannot come soon enough.",
        team_notes=tuple(
            TeamNote(team_id=t.team_id, prose=prose, attributed_event_ids=())
            for t in report.teams
        ),
    )


# --- The prompt ---------------------------------------------------------------


def test_the_prompt_identifies_teams_only_by_id() -> None:
    """The display name must not be a key the model can echo back.

    `TeamNote.team_id` is validated against the report's ids. If the board
    arrived naming `🥭 smoothie's team` and the model used that as the id, every
    note would be rejected as an unknown team and every team simultaneously
    reported as having no note -- a guaranteed failure on the first real run.

    The names still appear in the ranks block, because the recap has to be able
    to call teams what their managers call them. What matters is that each one is
    paired with its id there, and that the board itself carries ids only.
    """
    report = _report()
    message = build_draft_user_message(report, _board(report))
    board_block = message.split("DRAFT BOARD, in pick order:", 1)[1]

    for team_id, display in DISPLAY_NAMES.items():
        if team_id in {t.team_id for t in report.teams}:
            assert display not in board_block, (
                f"the board block leaks the display name {display!r}; the model "
                "will use it as a team_id and fail the coverage screen"
            )


def test_the_prompt_carries_no_figure_from_the_computation() -> None:
    """FR-043 sequencing, FR-047 disclosure.

    The architecture test proves `article/` cannot IMPORT the internal report.
    This proves the publishable one it does get carries nothing identifying
    either -- a prompt is still an artifact someone could paste into the page.
    """
    report = _report()
    message = build_draft_user_message(report, _board(report))
    lowered = message.lower()
    for identifier in config.DRAFT_INTERNAL_IDENTIFIERS:
        assert identifier not in lowered, f"prompt leaks {identifier}"


def test_the_system_prompt_forbids_round_pick_notation() -> None:
    """The numerals screen cannot allow "3.1" without allowing "28.4" too, so
    the prompt has to ask for words instead. If this instruction is ever
    dropped, the recap starts failing its own screen.
    """
    assert "3.1" in DRAFT_SYSTEM_PROMPT
    assert "never" in DRAFT_SYSTEM_PROMPT.lower()


# --- The numerals screen ------------------------------------------------------


def test_every_pick_and_round_number_is_permitted() -> None:
    report = _report()
    allowed = draft_permitted_numbers(_board(report))
    assert "1" in allowed
    assert "180" in allowed
    assert str(config.TEAM_COUNT) in allowed
    # Rounds 1..10 are all present as round numbers in their own right.
    for rnd in range(1, 11):
        assert str(rnd) in allowed


def test_a_number_beyond_the_board_is_still_foreign() -> None:
    report = _report()
    allowed = draft_permitted_numbers(_board(report))
    assert "181" not in allowed
    assert "28.4" not in allowed


def test_an_invented_stat_line_is_rejected() -> None:
    """The reason the screen is widened rather than removed."""
    report = _report()
    board = _board(report)
    content = _content(
        report, intro="Their first pick should be good for 28.4 points a game."
    )
    outcome = validate_draft_recap(content, report, board)
    assert not outcome.passed
    assert any(f.check == "no_foreign_numbers" for f in outcome.failures)


def test_citing_real_picks_and_rounds_passes() -> None:
    report = _report()
    board = _board(report)
    content = _content(
        report,
        intro=(
            "Player 1 went first overall, and by pick 18 the first round was "
            "already looking lopsided. Round 10 had some reaches."
        ),
    )
    outcome = validate_draft_recap(content, report, board)
    assert outcome.passed, [f.message for f in outcome.failures]


# --- The disclosure and tone screens ------------------------------------------


def test_disclosing_the_method_is_rejected() -> None:
    """FR-045. The screen is the same one the weekly column passes through."""
    report = _report()
    content = _content(
        report, intro="Their all-play projection is what put them on top."
    )
    outcome = validate_draft_recap(content, report, _board(report))
    assert not outcome.passed
    assert any(f.check == "no_disclosure" for f in outcome.failures)


def test_an_insult_aimed_at_a_person_is_rejected() -> None:
    """FR-046 draws its line at competence and character, not at humour."""
    report = _report()
    content = _content(
        report,
        intro="A fine draft all round.",
        prose="Whoever made this pick is incompetent.",
    )
    outcome = validate_draft_recap(content, report, _board(report))
    assert not outcome.passed
    assert any(f.check == "tone" for f in outcome.failures)


def test_teasing_a_pick_is_allowed() -> None:
    """The other half of FR-046, and the point of a draft recap.

    A screen that rejected this would cost the page its article on the
    highest-traffic day of the season, which is a worse outcome than the joke.
    """
    report = _report()
    content = _content(
        report,
        intro="Taking a third centre in round 5 is certainly a choice.",
        prose="Loaded up on guards and will be hunting rebounds all year.",
    )
    outcome = validate_draft_recap(content, report, _board(report))
    assert outcome.passed, [f.message for f in outcome.failures]


def test_every_team_must_get_a_note() -> None:
    """FR-041 is one article, not one per team -- but every team is in it."""
    report = _report()
    full = _content(report, intro="A good night all round.")
    short = ArticleContent(
        headline=full.headline,
        intro=full.intro,
        outro=full.outro,
        team_notes=full.team_notes[:-1],
    )
    outcome = validate_draft_recap(short, report, _board(report))
    assert not outcome.passed
    assert any(f.check == "team_coverage" for f in outcome.failures)
