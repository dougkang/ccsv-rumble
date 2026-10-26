"""`tools/chrome_capture.py`: day files, which weeks to capture, date parsing.

These are the parts of the capture that need no browser.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from datetime import date
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "chrome_capture.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("chrome_capture", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["chrome_capture"] = module
    spec.loader.exec_module(module)
    return module


def _csv(fields, rows) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _rows(tool, week: int, pts: str) -> list[dict[str, str]]:
    base = {f: "0" for f in tool.MATCHUP_FIELDS}
    return [
        {**base, "week": str(week), "matchup": "1", "team_id": "t.02", "pts": pts},
        {**base, "week": str(week), "matchup": "1", "team_id": "t.01", "pts": pts},
    ]


def test_recapturing_a_week_replaces_only_that_week(tool) -> None:
    fields = tool.MATCHUP_FIELDS
    existing = _csv(fields, _rows(tool, 1, "100") + _rows(tool, 2, "200"))
    merged = tool._merge_matchups(existing, _csv(fields, _rows(tool, 2, "999")), 2)

    rows = list(csv.DictReader(io.StringIO(merged)))
    assert [(r["week"], r["team_id"], r["pts"]) for r in rows] == [
        ("1", "t.01", "100"), ("1", "t.02", "100"),
        ("2", "t.01", "999"), ("2", "t.02", "999"),
    ]


def test_another_weeks_lines_survive_byte_for_byte(tool) -> None:
    fields = tool.MATCHUP_FIELDS
    existing = _csv(fields, _rows(tool, 1, "100"))
    merged = tool._merge_matchups(existing, _csv(fields, _rows(tool, 2, "200")), 2)
    week1 = [line for line in existing.splitlines()[1:]]
    assert all(line in merged.splitlines() for line in week1)


def test_old_format_rows_are_kept_with_blank_provenance(tool) -> None:
    old_fields = [f for f in tool.MATCHUP_FIELDS if f not in ("captured_at", "week_start", "week_end")]
    old_rows = [{k: v for k, v in r.items() if k in old_fields} for r in _rows(tool, 1, "100")]
    merged = tool._merge_matchups(
        _csv(old_fields, old_rows), _csv(tool.MATCHUP_FIELDS, _rows(tool, 2, "200")), 2
    )
    rows = list(csv.DictReader(io.StringIO(merged)))
    assert [r["week"] for r in rows] == ["1", "1", "2", "2"]
    assert rows[0]["captured_at"] == ""


def test_merging_into_an_empty_file(tool) -> None:
    merged = tool._merge_matchups("", _csv(tool.MATCHUP_FIELDS, _rows(tool, 1, "1")), 1)
    assert merged.splitlines()[0] == ",".join(tool.MATCHUP_FIELDS)


def _day_file(path: Path, week: int, captured_at: str, week_end: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "week,team_id,captured_at,week_end\n"
        f"{week},t.01,{captured_at},{week_end}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 21), [1]),       # mid week 1
        (date(2026, 10, 26), [1, 2]),    # Monday: week 1's final, then week 2
        (date(2026, 10, 30), [1, 2]),    # still no final for week 1: keep trying
    ],
)
def test_dailies_takes_the_final_capture_until_one_exists(
    tool, tmp_path: Path, today: date, expected: list[int]
) -> None:
    snaps = tmp_path / "matchups"
    _day_file(snaps / "2026-10-25.csv", 1, "2026-10-25T20:43:00-07:00", "2026-10-25")
    assert tool.weeks_to_capture("dailies", None, snaps, today) == expected


def test_once_the_final_exists_dailies_snapshots_only_the_current_week(
    tool, tmp_path: Path
) -> None:
    snaps = tmp_path / "matchups"
    _day_file(snaps / "2026-10-26.csv", 1, "2026-10-26T09:00:00-07:00", "2026-10-25")
    assert tool.weeks_to_capture("dailies", None, snaps, date(2026, 10, 27)) == [2]


def test_matchups_alone_snapshots_the_week_in_progress(tool, tmp_path: Path) -> None:
    assert tool.weeks_to_capture("matchups", None, tmp_path / "m", date(2026, 10, 26)) == [2]


def test_an_explicit_week_wins(tool, tmp_path: Path) -> None:
    assert tool.weeks_to_capture("dailies", 1, tmp_path / "m", date(2026, 11, 20)) == [1]


def test_before_opening_day_there_is_nothing_to_capture(tool, tmp_path: Path) -> None:
    with pytest.raises(tool.CaptureError, match="not started"):
        tool.weeks_to_capture("dailies", None, tmp_path / "m", date(2026, 10, 19))


def test_a_monday_file_holds_both_weeks(tool) -> None:
    fields = tool.MATCHUP_FIELDS
    day = tool._merge_matchups("", _csv(fields, _rows(tool, 1, "100")), 1)
    day = tool._merge_matchups(day, _csv(fields, _rows(tool, 2, "5")), 2)
    weeks = [r["week"] for r in csv.DictReader(io.StringIO(day))]
    assert weeks == ["1", "1", "2", "2"]


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (["Week 1: Oct 20 - Oct 25"], (date(2026, 10, 20), date(2026, 10, 25))),
        (["Oct 26 – Nov 1"], (date(2026, 10, 26), date(2026, 11, 1))),
        (["Dec 29 - Jan 4"], (date(2026, 12, 29), date(2027, 1, 4))),  # straddles New Year
        (["Jan 5 - 11"], (date(2027, 1, 5), date(2027, 1, 11))),
        ([], None),
        (["Oct 20 - Oct 25", "Oct 26 - Nov 1"], None),  # ambiguous
        (["Oct 20 - Oct 25", "Week 1 (Oct 20 - Oct 25)"], (date(2026, 10, 20), date(2026, 10, 25))),
    ],
)
def test_week_dates_are_read_only_when_unambiguous(tool, candidates, expected) -> None:
    assert tool.parse_week_dates(candidates, 2026) == expected


def test_rosters_are_kept_as_latest_and_as_a_daily_snapshot(tool, tmp_path: Path) -> None:
    tool.save_rosters(tmp_path, "team_id,player_id,name\nt.01,p1,A\n", date(2026, 10, 26))
    tool.save_rosters(tmp_path, "team_id,player_id,name\nt.01,p2,B\n", date(2026, 10, 27))

    assert "p2" in (tmp_path / "rosters.csv").read_text(encoding="utf-8")
    assert "p1" in (tmp_path / "rosters" / "2026-10-26.csv").read_text(encoding="utf-8")
    assert "p2" in (tmp_path / "rosters" / "2026-10-27.csv").read_text(encoding="utf-8")


def test_a_same_day_roster_recapture_replaces_that_days_copy(tool, tmp_path: Path) -> None:
    day = date(2026, 10, 26)
    tool.save_rosters(tmp_path, "team_id,player_id,name\nt.01,p1,A\n", day)
    tool.save_rosters(tmp_path, "team_id,player_id,name\nt.01,p9,Z\n", day)
    assert list((tmp_path / "rosters").iterdir()) == [tmp_path / "rosters" / "2026-10-26.csv"]
    assert "p9" in (tmp_path / "rosters" / "2026-10-26.csv").read_text(encoding="utf-8")
