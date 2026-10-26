"""`tools/chrome_capture.py`: per-week replace, default week, date parsing.

These are the parts of the capture that need no browser. Capturing week 2 must
never erase week 1, or backfill and the correction window lose their data.
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


@pytest.mark.parametrize(
    ("today", "week"),
    [(date(2026, 10, 26), 1), (date(2026, 11, 1), 1), (date(2026, 11, 2), 2)],
)
def test_the_default_week_is_the_last_one_that_ended(tool, today: date, week: int) -> None:
    assert tool.last_ended_week(today) == week


def test_before_any_week_ends_there_is_no_default(tool) -> None:
    with pytest.raises(tool.CaptureError, match="no matchup week has ended"):
        tool.last_ended_week(date(2026, 10, 25))


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
