"""The manager name survives the capture and reaches the page.

Week 0 has no scoreboard, so the roster capture is the ONLY source for manager
names once the league API is out of the picture. Before this, week 0 hardcoded
`manager_display_name=""` and the page rendered an empty Manager column for all
18 teams -- a blank cell that looked like league data rather than a gap.
"""

from __future__ import annotations

from pathlib import Path

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch import rosters as roster_source
from ccsv_rumble.pipeline import acquire_week_zero
from tests.conftest import DISPLAY_NAMES, write_rosters_csv

MANAGERS = {f"t.{i:02d}": name for i, name in enumerate(
    ["Doug Kang", "Daniel", "Elsie", "Pat", "Sam", "Jo", "Alex", "Ray", "Kim",
     "Lou", "Mo", "Nic", "Ada", "Ben", "Cleo", "Dev", "Eli", "Fay"], start=1)}


def test_the_manager_column_is_parsed(tmp_path: Path) -> None:
    path = write_rosters_csv(
        tmp_path / "rosters.csv", team_names=DISPLAY_NAMES, managers=MANAGERS
    )
    capture = roster_source.load(path)
    assert capture.managers["t.01"] == "Doug Kang"
    assert capture.managers["t.02"] == "Daniel"
    assert len(capture.managers) == len(capture.rosters)


def test_a_capture_without_managers_still_loads(tmp_path: Path) -> None:
    """The column is optional: an older capture must not break the run."""
    path = write_rosters_csv(tmp_path / "rosters.csv", team_names=DISPLAY_NAMES)
    capture = roster_source.load(path)
    assert capture.managers == {}
    assert len(capture.rosters) == 18


def test_an_unreadable_manager_is_blank_never_the_team_id(tmp_path: Path) -> None:
    """Team names fall back to the id; managers must NOT.

    `t.04` is a plausible-looking label for a team and a nonsensical one for a
    person. A blank cell is honest; an id in the Manager column reads as data.
    """
    partial = {"t.01": "Doug Kang"}
    path = write_rosters_csv(
        tmp_path / "rosters.csv", team_names=DISPLAY_NAMES, managers=partial
    )
    capture = roster_source.load(path)
    assert capture.managers["t.01"] == "Doug Kang"
    # Absent, not blank, and above all never the id -- `t.04` is a plausible
    # label for a team and a nonsensical one for a person.
    assert "t.02" not in capture.managers
    assert not any(m.startswith("t.") for m in capture.managers.values())


def test_managers_reach_the_week_zero_snapshot(tmp_path: Path) -> None:
    """The plumbing that was missing: capture -> Team.manager_display_name."""
    path = write_rosters_csv(
        tmp_path / "rosters.csv", team_names=DISPLAY_NAMES, managers=MANAGERS
    )
    capture = roster_source.load(path)
    snapshot = acquire_week_zero(
        ArchiveStore(tmp_path / "archive"),
        season="2026-27",
        capture=capture,
        stat_map={},
    )
    by_id = {t.team_id: t for t in snapshot.teams}
    assert by_id["t.01"].manager_display_name == "Doug Kang"
    assert by_id["t.11"].manager_display_name == "Mo"
    # Every team got one, so no cell is silently blank.
    assert all(t.manager_display_name for t in snapshot.teams)
