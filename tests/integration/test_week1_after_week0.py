"""Week 1 published on top of an archived week 0 (FR-019 to FR-022).

Week 0 is a projection with all-zero totals. Before this was fixed, it sat in the
ranking history as if it were a played week: `completed` counted 2 at week 1, the
zero totals -- every category a tie -- were averaged into EMW and CAW, and week 1's
movement was measured against a ranking of those zeros instead of the draft
ranking readers actually saw. Every existing week-1 test missed it because none
had a week 0 in the archive.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ccsv_rumble import config
from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.cli import _render_archived
from ccsv_rumble.pipeline import execute
from ccsv_rumble.rank.score import build_ranking, performance_weight
from ccsv_rumble.schedule import RunPlan
from tests.conftest import make_roster, make_snapshot, write_rosters_csv
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"
VALID = Path("tests/fixtures/projections-valid.csv")


def _publishable(store: ArchiveStore, week: int) -> dict:
    entry_id = store.latest_entry_id(SEASON, week)
    return store.read_publishable_raw(SEASON, week, entry_id) or {}


def _archive_week0_then_week1(tmp_path: Path) -> tuple[ArchiveStore, object]:
    store = ArchiveStore(tmp_path / "archive")
    rosters = write_rosters_csv(tmp_path / "rosters.csv")
    week0 = execute(
        RunPlan(SEASON, (), (), 0),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-22",
        projections_path=VALID,
        rosters_path=rosters,
    )
    assert week0.weeks_published == [0]

    # No projections for week 1: with no roster prior, week 1's ranking is
    # exactly `build_ranking([week 1])`, which makes (a) a clean comparison.
    week1 = execute(
        RunPlan(SEASON, (), (), 1),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=tmp_path / "missing.csv",
    )
    assert week1.weeks_published == [1]
    return store, week1


def test_week1_ranks_over_played_weeks_only(tmp_path: Path, fake_snapshot_builder) -> None:
    """FR-019: week 0 is neither a completed week nor averaged into results."""
    store, _ = _archive_week0_then_week1(tmp_path)

    # Compared on the INTERNAL figures, not rank order: a week of all ties
    # shifts every team by the same amount, so the order survives the bug and
    # only the scores reveal it.
    expected = {e.team_id: e for e in build_ranking([make_snapshot(1)]).entries}
    internal = json.loads(
        store.paths(SEASON, 1, store.latest_entry_id(SEASON, 1)).internal.read_text(
            encoding="utf-8"
        )
    )
    for entry in internal["ranking"]["entries"]:
        want = expected[entry["team_id"]]
        assert entry["rank"] == want.rank
        assert entry["emw"] == want.emw
        assert entry["caw"] == want.caw
        assert entry["performance_weight"] == performance_weight(1) == 0.25


def test_week1_movement_is_against_the_published_week0_ranking(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-020: not against a ranking recomputed from week 0's zero totals."""
    store, _ = _archive_week0_then_week1(tmp_path)

    week0_ranks = {t["team_id"]: t["rank"] for t in _publishable(store, 0)["teams"]}
    week1_previous = {
        t["team_id"]: t["previous_rank"] for t in _publishable(store, 1)["teams"]
    }
    assert week1_previous == week0_ranks


def test_week1_labels_count_played_weeks(tmp_path: Path, fake_snapshot_builder) -> None:
    """FR-021: one played week with no prior is provisional, not settled."""
    store, _ = _archive_week0_then_week1(tmp_path)

    flags = _publishable(store, 1)
    assert flags["is_provisional"] is True
    assert flags["is_projection"] is False


def test_week1_replay_matches_the_published_page(
    tmp_path: Path, fake_snapshot_builder
) -> None:
    """FR-022: replay applies the same history rule as the live run."""
    store, week1 = _archive_week0_then_week1(tmp_path)

    replayed = _render_archived(store, SEASON, 1, "2026-10-27", None)
    assert replayed.html == week1.pages[0].html


def test_week0_publishable_is_what_week1_reads(tmp_path: Path, fake_snapshot_builder) -> None:
    """Guards the fixture: the ranks compared above must come from a real file."""
    store, _ = _archive_week0_then_week1(tmp_path)
    path = store.paths(SEASON, 0, store.latest_entry_id(SEASON, 0)).publishable
    teams = json.loads(path.read_text(encoding="utf-8"))["teams"]
    assert sorted(t["rank"] for t in teams) == list(range(1, 19))


def test_week2_movement_is_against_the_published_week1_ranking(tmp_path: Path) -> None:
    """FR-020, one week on. Week 1 was published WITH the roster prior; a
    recomputation without it gives a different order, which no reader saw.

    Uses the capture source so the snapshots carry rosters and the prior is on.
    """
    from datetime import date

    from ccsv_rumble.fetch.captured import CapturedProvider
    from ccsv_rumble.pipeline import capture_source
    from tests.conftest import capture_rows_from_snapshot, read_matchup_rows, write_matchups_csv

    store = ArchiveStore(tmp_path / "archive")
    rosters = write_rosters_csv(tmp_path / "rosters.csv")
    execute(
        RunPlan(SEASON, (), (), 0), store=store, anthropic_client=None,
        generated_at="2026-10-22", projections_path=VALID, rosters_path=rosters,
    )
    week2 = capture_rows_from_snapshot(
        make_snapshot(2), captured_at="2026-11-02T09:00:00-08:00",
        week_start="2026-10-26", week_end="2026-11-01",
    )
    matchups = write_matchups_csv(tmp_path / "matchups.csv", read_matchup_rows() + week2)
    source = capture_source(CapturedProvider(matchups, rosters, season_start=date(2026, 10, 20)))

    results = {
        week: execute(
            RunPlan(SEASON, (), (), week), source=source, store=store, anthropic_client=None,
            generated_at="2026-11-03", projections_path=VALID, rosters_path=rosters,
        )
        for week in (1, 2)
    }

    week1_ranks = {t["team_id"]: t["rank"] for t in _publishable(store, 1)["teams"]}
    unprimed = {e.team_id: e.rank for e in build_ranking([store.latest_entry(SEASON, 1)]).entries}
    assert week1_ranks != unprimed, "fixture must make the prior matter"

    week2_previous = {t["team_id"]: t["previous_rank"] for t in _publishable(store, 2)["teams"]}
    assert week2_previous == week1_ranks

    replayed = _render_archived(store, SEASON, 2, "2026-11-03", None)
    assert replayed.html == results[2].pages[0].html



def test_week1_with_projections_is_provisional_not_a_projection(
    tmp_path: Path, monkeypatch
) -> None:
    """Week 1 has played games: a roster prior must not relabel it a projection."""

    def _build(*, entry_id, acquired_at, season, week, scoreboard, stat_map,
               supersedes=None, raw_source="raw-yahoo.json"):
        snapshot = make_snapshot(
            week, entry_id=entry_id, season=season, supersedes=supersedes
        )
        rosters = {
            t.team_id: make_roster(t.team_id, config.DRAFT_ROSTER_SIZE)
            for t in snapshot.teams
        }
        return replace(snapshot, rosters=rosters)

    monkeypatch.setattr("ccsv_rumble.pipeline.build_snapshot", _build)
    store = ArchiveStore(tmp_path / "archive")
    week1 = execute(
        RunPlan(SEASON, (), (), 1),
        provider=FakeProvider(),
        store=store,
        anthropic_client=None,
        generated_at="2026-10-27",
        projections_path=VALID,
    )
    assert week1.weeks_published == [1]

    # The prior must actually be in play, or this proves nothing.
    internal = json.loads(
        store.paths(SEASON, 1, store.latest_entry_id(SEASON, 1)).internal.read_text(
            encoding="utf-8"
        )
    )
    assert any(e.get("roster_prior") is not None for e in internal["ranking"]["entries"])

    flags = _publishable(store, 1)
    assert flags["is_projection"] is False
    assert flags["is_provisional"] is True
