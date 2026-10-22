"""The third run outcome: nothing published, exit ZERO, no notification.

FR-003/FR-004. This is the behaviour most likely to be implemented wrongly,
because the correct result looks identical to a silent failure from the outside:
no page appears either way.

Both halves are asserted here, and the second is the one that matters --
a genuine failure must still be loud. If both paths go quiet, the gate is wrong.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ccsv_rumble import cli
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.models import LifecycleState
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.conftest import write_rosters_csv
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"


@pytest.fixture
def week_zero_builder():
    """Roster completeness the test controls. Week 0 reads the roster CSV."""
    return {"short_teams": 0, "roster_size": 10, "teams": 18}


def _run(tmp_path: Path, store: ArchiveStore, state: dict) -> object:
    rosters = None
    if state.get("teams", 18) > 0:
        rosters = write_rosters_csv(
            tmp_path / "rosters.csv",
            roster_size=int(state.get("roster_size", 10)),
            short_teams=int(state.get("short_teams", 0)),
            teams=int(state.get("teams", 18)),
        )
    return execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-22",
        projections_path=Path(state.get("projections", "tests/fixtures/projections-valid.csv")),
        rosters_path=rosters,
    )


def test_an_undrafted_league_withholds_and_produces_no_pages(
    tmp_path: Path, week_zero_builder
) -> None:
    week_zero_builder["teams"] = 0  # nothing captured: the league has not drafted
    result = _run(tmp_path, ArchiveStore(tmp_path / "archive"), week_zero_builder)

    assert result.withheld is not None
    assert result.withheld.state is LifecycleState.PRE_DRAFT
    assert not result.pages
    assert not result.weeks_published


def test_the_withheld_reason_is_debuggable(tmp_path: Path, week_zero_builder) -> None:
    """FR-008. 'pre-draft' alone is useless three weeks later."""
    week_zero_builder["short_teams"] = 2
    result = _run(tmp_path, ArchiveStore(tmp_path / "archive"), week_zero_builder)

    assert result.withheld is not None
    assert "2 of 18" in result.withheld.reason
    assert "10" in result.withheld.reason


def test_withholding_sends_no_notification(tmp_path: Path, week_zero_builder) -> None:
    """FR-004: MUST NOT trigger a failure notification.

    A weekly failure alert until draft night would train the maintainer to
    ignore the only channel Principle II has.
    """
    week_zero_builder["short_teams"] = 18
    result = _run(tmp_path, ArchiveStore(tmp_path / "archive"), week_zero_builder)
    assert not result.notification.has_content


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        archive=tmp_path / "archive",
        from_archive=False,
        season=SEASON,
        week=0,
        no_backfill=True,
        recheck_weeks=0,
        projections="tests/fixtures/projections-valid.csv",
        rosters=None,
        out=str(tmp_path / "out"),
        branch="pages",
        no_article=True,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_the_cli_exits_zero_and_publishes_nothing(
    tmp_path: Path, week_zero_builder, monkeypatch, caplog
) -> None:
    """The requirement FR-004 actually states, at the exit-code boundary.

    Before this was wired, `cmd_run` fell through to the `has_pages` guard and
    returned EXIT_REPORT while logging an error -- reporting a normal, undrafted
    league as a failed run.
    """
    week_zero_builder["short_teams"] = 18
    monkeypatch.setattr(cli, "_provider_from_env", lambda: FakeProvider())

    def _must_not_publish(*args, **kwargs):
        raise AssertionError("a withheld run attempted to publish")

    monkeypatch.setattr(cli, "publish", _must_not_publish)

    with caplog.at_level("INFO"):
        code = cli.cmd_run(_args(tmp_path), dry_run=False)

    assert code == cli.EXIT_OK
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "pre_draft" in messages
    assert "normal state, not a failure" in messages
    # And nothing was logged at ERROR: this outcome is not a fault.
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_a_real_acquisition_failure_is_still_loud(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """The inverse assertion, and the reason the gate is not simply 'be quiet'.

    If both the normal and the broken path exit zero in silence, the gate has
    made the project worse, not safer.

    The failure used here is a week-0 one on purpose. Simulating a provider
    fault no longer reaches anything: week 0 is acquired from the roster file,
    and the pre-draft check runs before the provider is touched at all -- so
    that version of this test had become vacuous. Sub-threshold projection
    coverage is a genuine week-0 failure and must stay loud (FR-026, FR-038).
    """
    write_rosters_csv(tmp_path / "rosters.csv")
    monkeypatch.setattr(cli, "_provider_from_env", lambda: FakeProvider())

    args = _args(
        tmp_path,
        rosters=str(tmp_path / "rosters.csv"),
        projections="tests/fixtures/projections-sparse-team.csv",
    )
    with caplog.at_level("INFO"):
        code = cli.cmd_run(args, dry_run=False)

    assert code == cli.EXIT_ACQUIRE
    assert code != cli.EXIT_OK
    assert [r for r in caplog.records if r.levelname == "ERROR"]


def test_the_quiet_and_loud_paths_are_distinguishable(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """Stated as one assertion, because it is the property that matters.

    Pre-draft: exit 0, no ERROR. Broken input: non-zero, with an ERROR. If these
    ever converge, a real outage becomes indistinguishable from draft season.
    """
    monkeypatch.setattr(cli, "_provider_from_env", lambda: FakeProvider())

    with caplog.at_level("INFO"):
        quiet = cli.cmd_run(_args(tmp_path), dry_run=False)
    quiet_errors = [r for r in caplog.records if r.levelname == "ERROR"]

    caplog.clear()
    write_rosters_csv(tmp_path / "rosters.csv")
    with caplog.at_level("INFO"):
        loud = cli.cmd_run(
            _args(
                tmp_path,
                rosters=str(tmp_path / "rosters.csv"),
                projections="tests/fixtures/projections-sparse-league.csv",
            ),
            dry_run=False,
        )
    loud_errors = [r for r in caplog.records if r.levelname == "ERROR"]

    assert (quiet, bool(quiet_errors)) == (cli.EXIT_OK, False)
    assert (loud != cli.EXIT_OK) and bool(loud_errors)
