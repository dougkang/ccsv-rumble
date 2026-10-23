"""User Story 2: the draft recap, end to end.

The acceptance scenarios, in order: one league-wide article rather than one per
team (FR-041), archived as an input (FR-042), replayed without a second model
call (FR-044), and -- the two that matter most on draft night -- a page that
still publishes its ranking when the recap fails (FR-048) or when the board
never arrives (FR-049).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble import config
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.cli import _render_archived
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import DISPLAY_NAMES, write_draft_csv, write_rosters_csv
from tests.integration.conftest import FakeAnthropic, FakeProvider

SEASON = "2026-27"
FIXTURE = Path("tests/fixtures/projections-valid.csv")


def _run(tmp_path: Path, *, client=None, board: bool = True, store=None):
    rosters = write_rosters_csv(tmp_path / "rosters.csv", team_names=DISPLAY_NAMES)
    draft = (
        write_draft_csv(tmp_path / "draft.csv", team_names=DISPLAY_NAMES)
        if board
        else tmp_path / "absent.csv"
    )
    store = store or ArchiveStore(tmp_path / "archive")
    result = execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=store,
        anthropic_client=client,
        generated_at="2026-10-22",
        projections_path=FIXTURE,
        rosters_path=rosters,
        draft_results_path=draft,
    )
    return result, store


# --- Scenario 1: one league-wide article --------------------------------------


def test_the_recap_is_one_article_for_the_whole_league(tmp_path: Path) -> None:
    """FR-041. One `Article`, carrying a note for each of the 18 teams."""
    client = FakeAnthropic(behavior="recap")
    result, _ = _run(tmp_path, client=client)

    assert len(result.pages) == 1
    assert result.pages[0].has_article
    assert not result.notification.article_failures
    # Exactly one model call for the whole league, not one per team.
    assert len(client.calls) == 1


def test_the_recap_prompt_is_used_not_the_weekly_one(tmp_path: Path) -> None:
    """The two prompts ask for different things; week 0 must get the draft one.

    Asserted on the SYSTEM prompt actually sent, because a wiring mistake here
    would still produce a plausible-looking article -- one that talks about a
    week of results that has not happened.
    """
    client = FakeAnthropic(behavior="recap")
    _run(tmp_path, client=client)
    assert "draft recap" in client.systems[0]
    assert "weekly power-rankings column" not in client.systems[0]


def test_the_recap_reaches_the_page(tmp_path: Path) -> None:
    client = FakeAnthropic(behavior="recap")
    result, _ = _run(tmp_path, client=client)
    html = result.pages[0].html
    assert "Draft night in the books" in html
    assert "went first overall" in html


# --- Scenario 2: the screens --------------------------------------------------


@pytest.mark.parametrize(
    ("behavior", "reason"),
    [
        ("recap_discloses", "discloses method terms"),
        ("recap_invents_stats", "numbers absent from the report"),
    ],
)
def test_a_recap_failing_a_screen_is_not_published(
    tmp_path: Path, behavior: str, reason: str
) -> None:
    """FR-048: the ranking still publishes, the article section is omitted
    entirely -- no placeholder -- and the maintainer is told, because the page
    itself gives no sign anything is missing.
    """
    result, _ = _run(tmp_path, client=FakeAnthropic(behavior=behavior))

    page = result.pages[0]
    assert page.has_article is False
    assert result.weeks_published == [0]
    assert result.notification.article_failures
    # The notification carries the REASON, which is what the maintainer needs
    # in order to act on it.
    assert reason in " ".join(result.notification.article_failures)
    # No placeholder, no explanation.
    assert "unavailable" not in page.html.lower()


def test_a_model_outage_still_publishes_the_ranking(tmp_path: Path) -> None:
    """FR-048 for the generation failure rather than the screen failure."""
    result, _ = _run(tmp_path, client=FakeAnthropic(behavior="raise"))
    assert result.pages[0].has_article is False
    assert result.weeks_published == [0]
    assert result.notification.article_failures


# --- Scenario 3: archived once, replayed thereafter ---------------------------


def test_the_board_is_archived_as_an_input(tmp_path: Path) -> None:
    """FR-042. Archived immutably, which is what makes the replay below honest."""
    result, store = _run(tmp_path, client=FakeAnthropic(behavior="recap"))
    entry_id = result.pages[0].entry_id

    archived = store.read_draft_results(SEASON, 0, entry_id)
    assert archived is not None
    assert archived.is_complete
    assert len(archived.picks) == config.TEAM_COUNT * 10
    # Resolved ids, not display names -- the archive records what the pipeline
    # uses, so a later replay needs no second look at the roster file.
    assert {p.team_id for p in archived.picks} == set(DISPLAY_NAMES)


def test_replay_reproduces_the_recap_with_no_model_call(tmp_path: Path) -> None:
    """FR-044, acceptance scenario 3.

    The client is passed to `_render_archived`'s world not at all: replay reads
    the archived article. The assertion that matters is `client.calls`, which
    must not grow.
    """
    client = FakeAnthropic(behavior="recap")
    result, store = _run(tmp_path, client=client)
    original = result.pages[0].html
    assert len(client.calls) == 1

    replayed = _render_archived(store, SEASON, 0, "2026-10-22", entry_id=None)
    assert replayed.html == original
    assert len(client.calls) == 1, "replay issued a second model call"


# --- Scenario 4 / FR-049: no usable board -------------------------------------


def test_no_board_publishes_the_ranking_and_omits_the_article(
    tmp_path: Path,
) -> None:
    """FR-049. A recap from rosters alone is explicitly not the fallback."""
    client = FakeAnthropic(behavior="recap")
    result, _ = _run(tmp_path, client=client, board=False)

    assert result.weeks_published == [0]
    assert result.pages[0].has_article is False
    assert client.calls == [], "a recap was attempted with no draft board"
    assert result.notification.article_failures


def test_a_partial_board_is_treated_as_no_board(tmp_path: Path) -> None:
    """A draft caught in progress must not produce a confident recap of it."""
    rosters = write_rosters_csv(tmp_path / "rosters.csv", team_names=DISPLAY_NAMES)
    draft = write_draft_csv(
        tmp_path / "draft.csv", team_names=DISPLAY_NAMES, drop_picks=(42,)
    )
    client = FakeAnthropic(behavior="recap")
    result = execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=ArchiveStore(tmp_path / "archive"),
        anthropic_client=client,
        generated_at="2026-10-22",
        projections_path=FIXTURE,
        rosters_path=rosters,
        draft_results_path=draft,
    )

    assert result.weeks_published == [0]
    assert result.pages[0].has_article is False
    assert client.calls == []


def test_a_rankings_only_deployment_reports_no_article_failure(
    tmp_path: Path,
) -> None:
    """No API key and no board is not a degradation worth notifying about.

    Without this distinction the absent-board notification fires on every run of
    a rankings-only deployment, which trains the maintainer to ignore the one
    channel Principle II has.
    """
    result, _ = _run(tmp_path, client=None, board=False)
    assert result.weeks_published == [0]
    assert not result.notification.article_failures
