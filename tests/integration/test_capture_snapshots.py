"""Daily snapshots: every capture is kept; the run ranks the final one.

Mid-week snapshots exist for the player impact tool, which reads day-over-day
deltas. The ranking must never use one: a week ranked from Thursday's totals
looks exactly like a week ranked from the final ones.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch.captured import CapturedProvider, pick_snapshot
from ccsv_rumble.fetch.provider import ProviderError, WeekNotCaptured
from ccsv_rumble.pipeline import capture_source, execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import read_matchup_rows, write_matchups_csv, write_rosters_csv

SEASON = "2026-27"
TZ = "America/Los_Angeles"


def _snapshot(day: Path, captured_at: str, *, pts: str | None = None) -> Path:
    rows = read_matchup_rows()
    if pts is not None:
        for row in rows:
            if row["team_id"] == "t.01":
                row["pts"] = pts  # stays below t.03's 383: no category flips
    day.parent.mkdir(parents=True, exist_ok=True)
    return write_matchups_csv(day, rows, captured_at=captured_at)


def _provider(tmp_path: Path) -> CapturedProvider:
    return CapturedProvider(
        tmp_path / "matchups",
        write_rosters_csv(tmp_path / "rosters.csv"),
        season_start=date(2026, 10, 20),
    )


def test_the_latest_snapshot_after_the_week_ended_is_ranked(tmp_path: Path) -> None:
    snaps = tmp_path / "matchups"
    _snapshot(snaps / "2026-10-23.csv", "2026-10-23T09:00:00-07:00", pts="200")
    _snapshot(snaps / "2026-10-26.csv", "2026-10-26T09:00:00-07:00", pts="350")
    _snapshot(snaps / "2026-10-28.csv", "2026-10-28T09:00:00-07:00", pts="351")  # a correction

    raw = _provider(tmp_path).fetch_week(SEASON, 1)
    t01 = next(r for r in raw["capture"].rows if r.team_id == "t.01")
    assert t01.totals.pts == 351


def test_mid_week_snapshots_alone_are_refused(tmp_path: Path) -> None:
    snaps = tmp_path / "matchups"
    _snapshot(snaps / "2026-10-22.csv", "2026-10-22T09:00:00-07:00")
    _snapshot(snaps / "2026-10-25.csv", "2026-10-25T20:43:00-07:00")

    with pytest.raises(ProviderError, match="before it ended"):
        _provider(tmp_path).fetch_week(SEASON, 1)


def test_a_week_in_no_snapshot_is_not_captured(tmp_path: Path) -> None:
    _snapshot(tmp_path / "matchups" / "2026-10-26.csv", "2026-10-26T09:00:00-07:00")
    with pytest.raises(WeekNotCaptured, match="week 2"):
        _provider(tmp_path).fetch_week(SEASON, 2)


def test_a_final_snapshot_beats_a_later_named_malformed_one() -> None:
    """Bad metadata never wins selection; it is reported only if it is all there is."""
    rows = read_matchup_rows()

    def text(captured_at: str) -> str:
        out = io.StringIO()
        writer = csv.DictWriter(out, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows({**r, "captured_at": captured_at} for r in rows)
        return out.getvalue()

    picked = pick_snapshot(
        [("a.csv", text("2026-10-26T09:00:00-07:00")), ("b.csv", text("garbage"))], 1, TZ
    )
    assert picked is not None and picked[0] == "a.csv"


def test_daily_snapshots_rank_end_to_end_and_archive_the_chosen_rows(tmp_path: Path) -> None:
    snaps = tmp_path / "matchups"
    _snapshot(snaps / "2026-10-24.csv", "2026-10-24T09:00:00-07:00", pts="200")
    final = _snapshot(snaps / "2026-10-26.csv", "2026-10-26T09:00:00-07:00")

    result = execute(
        RunPlan(SEASON, (), (), 1),
        source=capture_source(_provider(tmp_path)),
        store=ArchiveStore(tmp_path / "archive"),
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "no-projections.csv",
    )

    assert result.weeks_published == [1]
    raw = ArchiveStore(tmp_path / "archive").paths(SEASON, 1, "entry-001").raw_matchups
    assert raw.read_text(encoding="utf-8") == final.read_text(encoding="utf-8")
