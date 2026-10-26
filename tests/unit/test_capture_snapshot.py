"""A WeekCapture becomes the same Snapshot shape the API path builds."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from ccsv_rumble.fetch.captured import build_capture_snapshot, load_week
from ccsv_rumble.fetch.rosters import RosterCapture
from ccsv_rumble.models import Matchup
from ccsv_rumble.schedule import week_range
from tests.conftest import MATCHUPS_WEEK1, make_roster

TEAM_IDS = [f"t.{i:02d}" for i in range(1, 19)]
AT = datetime(2026, 10, 27, 16, 0, tzinfo=UTC)


def _capture():
    return load_week(
        MATCHUPS_WEEK1.read_text(encoding="utf-8"),
        week=1,
        team_ids=set(TEAM_IDS),
        tz="America/Los_Angeles",
        calendar=lambda w: week_range(date(2026, 10, 20), w),
    )


def _rosters(size: int = 10) -> RosterCapture:
    return RosterCapture(
        rosters={t: make_roster(t, size) for t in TEAM_IDS},
        team_names={t: f"Roster name {t}" for t in TEAM_IDS},
        managers={t: f"Manager {t}" for t in TEAM_IDS if t != "t.05"},
    )


def _build(existing=None, rosters=None):
    return build_capture_snapshot(
        _capture(),
        roster_capture=rosters or _rosters(),
        existing=existing,
        entry_id="entry-001",
        acquired_at=AT,
        season="2026-27",
        supersedes=None,
    )


def test_teams_use_the_weeks_name_and_the_rosters_manager() -> None:
    snapshot = _build()
    assert [t.team_id for t in snapshot.teams] == TEAM_IDS
    first = snapshot.teams[0]
    assert first.name == "Team 01"  # the week's capture, not the roster file
    assert first.manager_display_name == "Manager t.01"
    # An unknown manager is blank, never the team id.
    assert snapshot.teams[4].manager_display_name == ""


def test_totals_are_the_captured_counts() -> None:
    line = _build().category_totals["t.01"]
    assert (line.fgm, line.fga, line.ftm, line.fta) == (134, 242, 59, 79)
    assert (line.pts, line.reb, line.ast, line.stl, line.blk, line.tpm, line.to) == (
        352, 121, 67, 22, 18, 25, 37,
    )
    assert line.games_played == 0


def test_matchups_are_oriented_like_the_api_path() -> None:
    matchups = _build().matchups
    assert len(matchups) == 9
    assert Matchup(week=1, home_team_id="t.01", away_team_id="t.03") in matchups
    assert all(m.home_team_id < m.away_team_id for m in matchups)
    assert list(matchups) == sorted(matchups, key=lambda m: (m.home_team_id, m.away_team_id))


def test_provenance_fields() -> None:
    snapshot = _build()
    assert snapshot.stat_category_map == {}
    assert snapshot.raw_source == "matchups.csv"
    assert (snapshot.week_start, snapshot.week_end) == (date(2026, 10, 20), date(2026, 10, 25))


def test_a_first_acquisition_carries_the_roster_capture() -> None:
    snapshot = _build()
    assert snapshot.rosters == _rosters().rosters


def test_an_archived_week_keeps_its_archived_rosters() -> None:
    """R5: today's rosters must not rewrite a past week, or every waiver move
    would be archived as a stat correction."""
    archived = replace(_build(), rosters={t: make_roster(t, 9) for t in TEAM_IDS})
    snapshot = _build(existing=archived, rosters=_rosters(10))
    assert snapshot.rosters == archived.rosters
