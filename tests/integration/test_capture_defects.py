"""User Story 2: a defective capture publishes nothing, notifies, and says why.

A wrong ranking looks exactly like a right one, so each of these must stop the
run before the publish step -- and the page left live must stay untouched.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ccsv_rumble import cli
from tests.conftest import read_matchup_rows, write_matchups_csv, write_rosters_csv
from tests.integration.test_capture_no_credentials import offline  # noqa: F401


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent = []

    def send(self, notification) -> None:
        self.sent.append(notification)


@pytest.fixture
def harness(monkeypatch, tmp_path: Path):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_notifier", lambda: notifier)

    def _no_publish(*args, **kwargs):
        raise AssertionError("a defective capture reached the publish step")

    monkeypatch.setattr(cli, "publish", _no_publish)
    write_rosters_csv(tmp_path / "rosters.csv")
    return notifier


def _without(team_id: str):
    return [r for r in read_matchup_rows() if r["team_id"] != team_id]


def _edited(team_id: str, **changes: str):
    rows = read_matchup_rows()
    for row in rows:
        if row["team_id"] == team_id:
            row.update(changes)
    return rows


def _all(**changes: str):
    return [{**r, **changes} for r in read_matchup_rows()]


@pytest.mark.parametrize(
    ("rows", "week", "named"),
    [
        pytest.param(_without("t.07"), 1, "t.07", id="FR-005-missing-team"),
        pytest.param(_edited("t.05", fga=""), 1, "fga", id="FR-006-blank-count"),
        pytest.param(_edited("t.01", cat_wins="6"), 1, "category wins", id="FR-008-checksum"),
        pytest.param(
            _all(captured_at="2026-10-25T20:43:00-07:00"), 1, "before it ended",
            id="FR-009-in-progress",
        ),
        pytest.param(read_matchup_rows(), 2, "--week 2", id="FR-010-week-not-captured"),
    ],
)
def test_a_defective_capture_fails_the_run(
    tmp_path: Path, offline, harness, caplog, rows, week: int, named: str
) -> None:
    caplog.set_level(logging.INFO, logger="ccsv_rumble")
    matchups = write_matchups_csv(tmp_path / "matchups.csv", rows)

    code = cli.main(
        [
            "run", "--week", str(week),
            "--matchups", str(matchups),
            "--rosters", str(tmp_path / "rosters.csv"),
            "--projections", str(tmp_path / "no-projections.csv"),
            "--archive", str(tmp_path / "archive"),
        ]
    )

    assert code == cli.EXIT_ACQUIRE
    assert named in caplog.text
    assert len(harness.sent) == 1, "a failed run must notify (Principle II)"
    assert named in harness.sent[0].run_failure
    assert not (tmp_path / "archive" / "2026-27" / f"week-{week:02d}").exists()
