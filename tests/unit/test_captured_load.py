"""`fetch/captured.load_week`: the matchups contract's reader guarantees.

Every defect a capture can carry must fail here, naming the defect, before
anything downstream sees it (User Story 2). A wrong ranking looks exactly like a
right one, so this is where wrong data has to be stopped.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

import pytest

from ccsv_rumble.fetch.captured import load_week
from ccsv_rumble.fetch.provider import ProviderError, WeekNotCaptured
from ccsv_rumble.schedule import week_range
from tests.conftest import MATCHUPS_WEEK1, read_matchup_rows

SEASON_START = date(2026, 10, 20)
TEAM_IDS = {f"t.{i:02d}" for i in range(1, 19)}


def _text(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _load(rows: list[dict[str, str]] | None = None, *, week: int = 1, **kwargs):
    text = MATCHUPS_WEEK1.read_text(encoding="utf-8") if rows is None else _text(rows)
    return load_week(
        text,
        week=week,
        team_ids=kwargs.pop("team_ids", TEAM_IDS),
        tz="America/Los_Angeles",
        calendar=lambda w: week_range(SEASON_START, w),
        **kwargs,
    )


def _edit(team_id: str, **changes: str) -> list[dict[str, str]]:
    rows = read_matchup_rows()
    for row in rows:
        if row["team_id"] == team_id:
            row.update(changes)
    return rows


def _row(rows: list[dict[str, str]], team_id: str) -> dict[str, str]:
    return next(r for r in rows if r["team_id"] == team_id)


# --- the happy path (US1) -----------------------------------------------------


def test_a_complete_week_loads() -> None:
    capture = _load()
    assert capture.week == 1
    assert len(capture.rows) == 18
    assert (capture.week_start, capture.week_end) == (date(2026, 10, 20), date(2026, 10, 25))
    assert capture.captured_at == datetime.fromisoformat("2026-10-26T09:00:00-07:00")
    assert capture.captured_at.tzinfo is not None


def test_raw_text_is_the_header_plus_this_weeks_lines_unchanged() -> None:
    original = MATCHUPS_WEEK1.read_text(encoding="utf-8")
    other_week = original.splitlines()[1].replace("1,", "2,", 1)
    capture = _load_text(original + other_week + "\n")
    assert capture.raw_text == original


def _load_text(text: str, week: int = 1):
    return load_week(
        text,
        week=week,
        team_ids=TEAM_IDS,
        tz="America/Los_Angeles",
        calendar=lambda w: week_range(SEASON_START, w),
    )


def test_a_week_with_no_rows_is_not_captured() -> None:
    with pytest.raises(WeekNotCaptured) as caught:
        _load(week=2)
    assert caught.value.week == 2
    assert "chrome_capture.py matchups --week 2" in str(caught.value)


# --- every defect fails, naming itself (US2) ----------------------------------


def test_a_missing_team_is_named() -> None:
    rows = [r for r in read_matchup_rows() if r["team_id"] != "t.07"]
    with pytest.raises(ProviderError, match=r"t\.07"):
        _load(rows)


def test_a_team_twice_is_named() -> None:
    rows = read_matchup_rows()
    rows.append(dict(_row(rows, "t.04")))
    with pytest.raises(ProviderError, match=r"t\.04"):
        _load(rows)


@pytest.mark.parametrize("value", ["", "12.5", "n/a"])
def test_a_bad_count_names_team_and_column(value: str) -> None:
    with pytest.raises(ProviderError, match=r"t\.05.*fga|fga.*t\.05"):
        _load(_edit("t.05", fga=value))


def test_more_makes_than_attempts_is_named() -> None:
    with pytest.raises(ProviderError, match=r"t\.05"):
        _load(_edit("t.05", fgm="999"))


def test_opponents_that_do_not_name_each_other_fail() -> None:
    rows = read_matchup_rows()
    a = _row(rows, "t.01")
    b = _row(rows, "t.02")
    a["opponent_id"], b["opponent_id"] = b["opponent_id"], a["opponent_id"]
    with pytest.raises(ProviderError, match="opponent"):
        _load(rows)


def test_an_unknown_team_id_fails() -> None:
    rows = read_matchup_rows()
    for row in rows:
        if row["team_id"] == "t.18":
            row["team_id"] = "t.99"
        if row["opponent_id"] == "t.18":
            row["opponent_id"] = "t.99"
    with pytest.raises(ProviderError, match=r"t\.99"):
        _load(rows)


def test_a_category_win_count_that_disagrees_names_both_teams() -> None:
    # t.01 beat t.03 in 4 categories.
    with pytest.raises(ProviderError, match=r"t\.01.*t\.03|t\.03.*t\.01") as caught:
        _load(_edit("t.01", cat_wins="6"))
    assert "6" in str(caught.value) and "4" in str(caught.value)


def test_a_capture_taken_before_the_week_ended_is_refused() -> None:
    """The real committed file: 20:43 PT on the week's last day."""
    rows = read_matchup_rows()
    for row in rows:
        row["captured_at"] = "2026-10-25T20:43:00-07:00"
    with pytest.raises(ProviderError, match="before it ended"):
        _load(rows)


def test_dates_that_disagree_with_the_calendar_name_both_ranges() -> None:
    rows = read_matchup_rows()
    for row in rows:
        row["week_end"] = "2026-10-26"
    with pytest.raises(ProviderError, match="2026-10-26") as caught:
        _load(rows)
    assert "2026-10-25" in str(caught.value)


def test_capture_times_that_differ_within_a_week_fail() -> None:
    with pytest.raises(ProviderError, match="captured_at"):
        _load(_edit("t.09", captured_at="2026-10-27T09:00:00-07:00"))


def test_rows_in_the_old_format_fail_on_missing_metadata() -> None:
    rows = [
        {k: v for k, v in r.items() if k not in ("captured_at", "week_start", "week_end")}
        for r in read_matchup_rows()
    ]
    with pytest.raises(ProviderError, match="captured_at"):
        _load(rows)


# --- things that look wrong and are not ---------------------------------------


def _pair(a_line: dict[str, str], b_line: dict[str, str]) -> list[dict[str, str]]:
    """The fixture with t.01 and t.03 (matchup 1) replaced by these lines."""
    rows = read_matchup_rows()
    _row(rows, "t.01").update(a_line)
    _row(rows, "t.03").update(b_line)
    return rows


# A line where only FG% is close: t.01 wins the other eight categories outright.
_A = dict(pts="400", reb="150", ast="90", stl="30", blk="20", tpm="40", to="20",
          ftm="80", fta="100", ft_pct_display=".800")
_B = dict(pts="300", reb="100", ast="60", stl="20", blk="10", tpm="20", to="40",
          ftm="70", fta="100", ft_pct_display=".700")


@pytest.mark.parametrize("a_wins", ["8", "9"])
def test_a_near_tie_passes_under_either_percentage_rule(a_wins: str) -> None:
    """.4412 vs .4408 is a win exactly and a tie at display precision (R2).

    Yahoo's rule is unknown; a valid week must not fail over it.
    """
    rows = _pair(
        {**_A, "fgm": "1103", "fga": "2500", "fg_pct_display": ".441", "cat_wins": a_wins},
        {**_B, "fgm": "1102", "fga": "2500", "fg_pct_display": ".441", "cat_wins": "0"},
    )
    assert len(_load(rows).rows) == 18


def test_a_tie_counted_as_half_passes() -> None:
    """The page may show 8.5 for eight wins and a tie (the scraper allows it)."""
    rows = _pair(
        {**_A, "fgm": "1103", "fga": "2500", "fg_pct_display": ".441", "cat_wins": "8.5"},
        {**_B, "fgm": "1102", "fga": "2500", "fg_pct_display": ".441", "cat_wins": "0.5"},
    )
    assert len(_load(rows).rows) == 18


def test_zero_attempts_is_data_not_a_misread() -> None:
    rows = _pair(
        {**_A, "fgm": "0", "fga": "0", "fg_pct_display": "-", "cat_wins": "8"},
        {**_B, "fgm": "10", "fga": "20", "fg_pct_display": ".500", "cat_wins": "1"},
    )
    assert len(_load(rows).rows) == 18
