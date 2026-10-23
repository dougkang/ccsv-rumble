"""Roster ingest. League data, and deliberately NOT derived from projections.

The validation here is about what would corrupt a week silently rather than
loudly: a player credited to the wrong team, or an input whose row order makes
two captures of the same league diff as a correction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccsv_rumble.fetch.rosters import RosterError, load, parse_positions, parse_rows

HEAD = "team_id,player_id,name,positions,status,team_name"


def _rows(*lines: str) -> list[dict[str, str]]:
    keys = HEAD.split(",")
    return [dict(zip(keys, line.split(","), strict=False)) for line in lines]


def test_parses_rosters_by_team() -> None:
    capture = parse_rows(
        _rows(
            "t.01,nba.p.1,A,PG,,Keyboard Cats",
            "t.01,nba.p.2,B,C,,Keyboard Cats",
            "t.02,nba.p.3,C,SF,,Other Team",
        )
    )
    assert set(capture.rosters) == {"t.01", "t.02"}
    assert len(capture.rosters["t.01"]) == 2
    assert capture.rosters["t.01"][0].positions == ("PG",)


def test_team_names_are_carried() -> None:
    """Week 0 has no scoreboard, so names can only come from the capture.

    Without them the page would label every team by its id.
    """
    capture = parse_rows(_rows("t.01,nba.p.1,A,PG,,Keyboard Cats"))
    assert capture.team_names["t.01"] == "Keyboard Cats"


def test_managers_are_carried_when_the_column_is_present() -> None:
    """Week 0 has no scoreboard, so the Manager column can only come from here."""
    rows = [
        {"team_id": "t.01", "player_id": "nba.p.1", "name": "A", "manager": "Doug Kang"},
        {"team_id": "t.02", "player_id": "nba.p.2", "name": "B", "manager": ""},
    ]
    capture = parse_rows(rows)
    assert capture.managers == {"t.01": "Doug Kang"}


def test_a_capture_without_names_falls_back_to_the_id() -> None:
    capture = parse_rows(_rows("t.01,nba.p.1,A,PG,,"))
    assert capture.team_names["t.01"] == "t.01"


def test_row_order_does_not_change_the_result() -> None:
    """Otherwise two captures of the same league diff as an upstream correction.

    `archive/diff` compares normalized data, so an unstable ordering would
    append a junk entry on every run.
    """
    forward = parse_rows(
        _rows("t.01,nba.p.1,A,PG,,T", "t.01,nba.p.2,B,C,,T", "t.01,nba.p.3,C,SF,,T")
    )
    backward = parse_rows(
        _rows("t.01,nba.p.3,C,SF,,T", "t.01,nba.p.1,A,PG,,T", "t.01,nba.p.2,B,C,,T")
    )
    assert forward.rosters == backward.rosters


def test_a_player_on_two_rosters_is_rejected() -> None:
    """Keeping one silently would credit his week to the wrong team."""
    with pytest.raises(RosterError, match="cannot be on two rosters"):
        parse_rows(_rows("t.01,nba.p.1,A,PG,,T", "t.02,nba.p.1,A,PG,,T"))


def test_an_unknown_team_is_rejected_when_the_league_is_known() -> None:
    with pytest.raises(RosterError, match="unknown team"):
        parse_rows(_rows("t.99,nba.p.1,A,PG,,T"), known_team_ids={"t.01"})


def test_missing_columns_are_rejected() -> None:
    with pytest.raises(RosterError, match="missing required columns"):
        parse_rows([{"team_id": "t.01"}])


def test_a_row_without_ids_is_rejected() -> None:
    with pytest.raises(RosterError, match="missing team_id or player_id"):
        parse_rows(_rows("t.01,,A,PG,,T"))


def test_empty_input_is_rejected() -> None:
    with pytest.raises(RosterError, match="no rows"):
        parse_rows([])


def test_a_short_roster_is_accepted_not_rejected() -> None:
    """Ingest reports what the league looks like; the GATE decides meaning.

    A short roster is how PRE_DRAFT is detected, so refusing it at ingest would
    turn a normal pre-draft state into an acquisition failure -- which FR-004
    forbids.
    """
    capture = parse_rows(_rows("t.01,nba.p.1,A,PG,,T"))
    assert len(capture.rosters["t.01"]) == 1


def test_a_missing_file_names_the_capture_tool(tmp_path: Path) -> None:
    with pytest.raises(RosterError, match="yahoo_roster_capture"):
        load(tmp_path / "absent.csv")


def test_load_round_trips_a_written_file(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    path.write_text(
        f"{HEAD}\nt.01,nba.p.1,A Player,\"PG,SG\",,Keyboard Cats\n", encoding="utf-8"
    )
    capture = load(path)
    slot = capture.rosters["t.01"][0]
    assert slot.positions == ("PG", "SG")
    assert slot.name == "A Player"
    assert capture.team_names["t.01"] == "Keyboard Cats"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("PG,SG", ("PG", "SG")), ("pg, sf", ("PG", "SF")), ("", ()), (None, ())],
)
def test_parse_positions(raw: str, expected: tuple[str, ...]) -> None:
    assert parse_positions(raw) == expected
