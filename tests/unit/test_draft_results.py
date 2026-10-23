"""Draft board acquisition: FR-042, FR-049.

The theme of this file is that an unusable board must cost the ARTICLE and
nothing else. Every malformed input below has to come back as `None` from
`load_or_none` rather than as an exception, because a raised error here would
turn a page that is merely missing its recap into a failed run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble import config
from ccsv_rumble.archive import serde
from ccsv_rumble.fetch.draft import DraftError, load_or_none, parse_rows
from tests.conftest import DISPLAY_NAMES, write_draft_csv

SEASON = "2026-27"


def _rows(**overrides) -> list[dict]:
    base = {
        "round": "1",
        "pick_in_round": "1",
        "overall": "1",
        "player_id": "nba.p.1",
        "player_name": "A. Player",
        "nba_team": "LAL",
        "positions": "PG,SG",
        "team_name": "Keyboard Cats",
    }
    return [base | overrides]


NAME_TO_ID = {name: tid for tid, name in DISPLAY_NAMES.items()}


def test_picks_are_keyed_on_canonical_team_ids_not_display_names() -> None:
    """The join happens at load time, once.

    If display names reached the prompt, the model would echo them back as
    `TeamNote.team_id` and every note would fail the validator's coverage check
    while every team would simultaneously be reported as missing.
    """
    results = parse_rows(_rows(), SEASON, NAME_TO_ID)
    assert results.picks[0].team_id == "t.01"
    assert results.picks[0].positions == ("PG", "SG")
    assert results.picks[0].nba_team == "LAL"


def test_a_name_the_rosters_do_not_know_is_an_error() -> None:
    """Silently dropping the pick would produce a recap missing a whole team."""
    with pytest.raises(DraftError, match="does not know"):
        parse_rows(_rows(team_name="Some Other League's Team"), SEASON, NAME_TO_ID)


def test_missing_columns_are_named() -> None:
    with pytest.raises(DraftError, match="missing columns"):
        parse_rows([{"overall": "1"}], SEASON, NAME_TO_ID)


def test_no_rows_is_an_error_not_an_empty_board() -> None:
    with pytest.raises(DraftError, match="no rows"):
        parse_rows([], SEASON, NAME_TO_ID)


def test_an_unparseable_pick_number_is_an_error() -> None:
    with pytest.raises(DraftError, match="unparseable pick"):
        parse_rows(_rows(overall="first"), SEASON, NAME_TO_ID)


def test_a_full_board_is_complete(tmp_path: Path) -> None:
    path = write_draft_csv(tmp_path / "d.csv", team_names=DISPLAY_NAMES)
    results = load_or_none(path, SEASON, DISPLAY_NAMES)
    assert results is not None
    assert results.is_complete
    assert len(results.picks) == config.TEAM_COUNT * 10
    # Sorted by overall regardless of file order, so the recap's "in pick order"
    # view really is in pick order.
    assert [p.pick_number for p in results.picks] == list(range(1, 181))


def test_a_board_with_a_gap_is_unavailable(tmp_path: Path) -> None:
    """FR-049. A recap from a partial board would describe a draft that did not
    happen -- and unlike a missing article, a wrong one looks fine to a reader.
    """
    path = write_draft_csv(
        tmp_path / "d.csv", team_names=DISPLAY_NAMES, drop_picks=(57,)
    )
    assert load_or_none(path, SEASON, DISPLAY_NAMES) is None


def test_a_draft_paused_between_rounds_is_unavailable(tmp_path: Path) -> None:
    """Rounds 1-3 only -- the case contiguity alone cannot catch.

    54 picks is contiguous from 1, divides evenly by the team count, and touches
    all 18 teams. Every structural check except SIZE passes, so without the
    `DRAFT_ROSTER_SIZE` constraint a third of a draft would be reported as a
    finished one and the recap would describe a draft that did not happen.
    """
    path = write_draft_csv(tmp_path / "d.csv", team_names=DISPLAY_NAMES, rounds=3)
    assert load_or_none(path, SEASON, DISPLAY_NAMES) is None


def test_a_board_with_an_extra_round_is_unavailable(tmp_path: Path) -> None:
    """The other side of the size check: 11 rounds is not this league's draft."""
    path = write_draft_csv(tmp_path / "d.csv", team_names=DISPLAY_NAMES, rounds=11)
    assert load_or_none(path, SEASON, DISPLAY_NAMES) is None


def test_a_board_missing_a_whole_team_is_unavailable(tmp_path: Path) -> None:
    path = write_draft_csv(
        tmp_path / "d.csv", team_names=DISPLAY_NAMES, rounds=10, teams=17
    )
    assert load_or_none(path, SEASON, DISPLAY_NAMES) is None


def test_an_absent_file_is_none_not_an_exception(tmp_path: Path) -> None:
    assert load_or_none(tmp_path / "nope.csv", SEASON, DISPLAY_NAMES) is None


def test_malformed_csv_is_none_not_an_exception(tmp_path: Path) -> None:
    """`csv.Error` is not a `ValueError`.

    Without it in the except clause an unclosed quote escapes `load_or_none`
    and crashes the run -- precisely the outcome FR-049 forbids.
    """
    path = tmp_path / "d.csv"
    path.write_text(
        'round,pick_in_round,overall,player_id,player_name,nba_team,positions,team_name\n'
        '1,1,1,nba.p.1,"unclosed quote,LAL,G,Keyboard Cats\n',
        encoding="utf-8",
    )
    assert load_or_none(path, SEASON, DISPLAY_NAMES) is None


def test_unresolvable_names_do_not_raise_through_load(tmp_path: Path) -> None:
    """The error is real, but the run survives it."""
    path = write_draft_csv(tmp_path / "d.csv", team_names=DISPLAY_NAMES)
    assert load_or_none(path, SEASON, {"t.01": "Nobody"}) is None


def test_positions_survive_the_archive_round_trip(tmp_path: Path) -> None:
    """A list-vs-tuple mismatch would make every archived board compare unequal
    to the freshly parsed one, which is how `archive/diff` reports a phantom
    correction on every run.
    """
    original = parse_rows(_rows(), SEASON, NAME_TO_ID)
    encoded = serde.to_jsonable(original)
    decoded = serde.draft_results_from_dict(encoded)
    assert decoded == original
    assert isinstance(decoded.picks[0].positions, tuple)
