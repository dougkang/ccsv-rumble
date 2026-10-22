"""SC-001's actual acceptance condition: the SCHEDULED job reaches week 0.

Every other week-0 test passes `RunPlan(..., 0)` by hand. That proves the
ranking works; it does not prove the weekly run can get there. Before this,
`build_plan` never produced week 0, so the page was reachable only via an
explicit `--week 0` — SC-001 would have been false in production while every
other test stayed green.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ccsv_rumble import config
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.models import LifecycleState
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import build_plan
from tests.conftest import write_rosters_csv
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"
SEASON_START = date(2026, 10, 20)
PROJECTIONS = Path("tests/fixtures/projections-valid.csv")

#: Two days in: the draft has happened, no week has finished.
POST_DRAFT_DAY = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def _run(tmp_path: Path, *, rosters: Path | None, clock: datetime = POST_DRAFT_DAY):
    """Plan and execute exactly as the scheduled job does — no explicit week."""
    store = ArchiveStore(tmp_path / "archive")
    plan = build_plan(store, SEASON, SEASON_START, clock=clock)
    result = execute(
        plan,
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-22",
        projections_path=PROJECTIONS,
        rosters_path=rosters,
    )
    return plan, result, store


def test_the_scheduled_run_publishes_the_week_zero_page(tmp_path: Path) -> None:
    """SC-001, through the route the weekly job actually takes."""
    rosters = write_rosters_csv(tmp_path / "rosters.csv")
    plan, result, _ = _run(tmp_path, rosters=rosters)

    assert plan.current_week == 0, "the plan did not target week 0"
    assert result.withheld is None, result.withheld
    assert len(result.pages) == 1
    assert result.pages[0].week == 0
    assert result.weeks_published == [0]


def test_the_published_page_carries_all_eighteen_teams(tmp_path: Path) -> None:
    rosters = write_rosters_csv(tmp_path / "rosters.csv")
    _, result, _ = _run(tmp_path, rosters=rosters)
    html = result.pages[0].html
    assert html.count('class="move move-new"') == config.TEAM_COUNT


def test_team_names_come_from_the_roster_capture(tmp_path: Path) -> None:
    """Week 0 has no scoreboard, so names can only come from the capture.

    Without them every row would read `t.01`, which is correct and useless.
    """
    path = tmp_path / "rosters.csv"
    rows = ["team_id,player_id,name,positions,status,team_name"]
    for index in range(1, config.TEAM_COUNT + 1):
        team_id = f"t.{index:02d}"
        team_name = "Keyboard Cats" if index == 1 else f"Team {index:02d}"
        for i in range(config.DRAFT_ROSTER_SIZE):
            positions = ("PG", "SG", "SF", "PF", "C", "SG")[i % 6]
            rows.append(
                f"{team_id},nba.p.{team_id}.{i:02d},Player {team_id}-{i:02d},"
                f"{positions},,{team_name}"
            )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    _, result, _ = _run(tmp_path, rosters=path)
    assert "Keyboard Cats" in result.pages[0].html


def test_an_undrafted_league_withholds_through_the_scheduled_route(
    tmp_path: Path,
) -> None:
    """The quiet outcome must survive the real planning path too.

    No roster file at all is how a pre-draft league looks: FR-002 defines the
    state as "rosters do not exist or are incomplete", so this is normal rather
    than a failure.
    """
    plan, result, _ = _run(tmp_path, rosters=None)

    assert plan.current_week == 0
    assert result.withheld is not None
    assert result.withheld.state is LifecycleState.PRE_DRAFT
    assert not result.pages
    assert not result.notification.has_content


def test_a_partially_captured_league_withholds(tmp_path: Path) -> None:
    """Half a capture must not publish half a ranking.

    All-play is undefined without the full grid, so an incomplete capture is
    indistinguishable from an incomplete draft and is treated the same way.
    """
    rosters = write_rosters_csv(tmp_path / "rosters.csv", teams=9)
    _, result, _ = _run(tmp_path, rosters=rosters)

    assert result.withheld is not None
    assert "9 of 18" in result.withheld.reason
    assert not result.pages


def test_the_scheduled_run_archives_the_week_zero_entry(tmp_path: Path) -> None:
    """Replay depends on it, and so does the next run's gap detection."""
    rosters = write_rosters_csv(tmp_path / "rosters.csv")
    _, _, store = _run(tmp_path, rosters=rosters)

    assert store.has_week(SEASON, 0)
    entry_id = store.latest_entry_id(SEASON, 0)
    snapshot = store.entry(SEASON, 0, entry_id)
    assert snapshot.week == 0
    assert len(snapshot.rosters) == config.TEAM_COUNT
    # Zero, not missing: no game has been played, so every total really is zero.
    assert all(line.pts == 0 for line in snapshot.category_totals.values())
    assert store.read_projections(SEASON, 0, entry_id) is not None


def test_once_a_week_completes_the_scheduled_run_leaves_week_zero_alone(
    tmp_path: Path,
) -> None:
    """The in-season route must not regress to the week-0 path.

    Asserts the PLAN only. Executing here would need the in-season scoreboard
    doubles, and the claim under test is purely about which week is targeted.
    """
    plan = build_plan(
        ArchiveStore(tmp_path / "archive"),
        SEASON,
        SEASON_START,
        clock=datetime(2026, 10, 28, 9, 0, tzinfo=UTC),
    )
    assert plan.current_week == 1
    assert 0 not in plan.weeks_to_publish


@pytest.mark.parametrize("short", [1, 2, 18])
def test_any_short_roster_withholds(tmp_path: Path, short: int) -> None:
    rosters = write_rosters_csv(tmp_path / "rosters.csv", short_teams=short)
    _, result, _ = _run(tmp_path, rosters=rosters)
    assert result.withheld is not None
    assert result.withheld.state is LifecycleState.PRE_DRAFT
