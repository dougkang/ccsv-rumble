"""FR-017: the same league data gives the same output from either source.

"Same" is defined in research R12. The two snapshots legitimately differ in team
ids, managers, the stat map and rosters, so the comparison normalizes those and
then demands equality of everything the ranking reads.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from ccsv_rumble.fetch.captured import build_capture_snapshot, load_week
from ccsv_rumble.fetch.normalize import build_snapshot
from ccsv_rumble.fetch.rosters import RosterCapture
from ccsv_rumble.fetch.yahoo import parse_stat_category_map
from ccsv_rumble.models import CategoryLine
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_page
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from ccsv_rumble.schedule import week_range
from tests.conftest import capture_rows_from_snapshot, make_snapshot
from tests.unit.test_render_deterministic import GOLDEN

AT = datetime(2026, 10, 27, 16, 0, tzinfo=UTC)


def _text(rows: list[dict[str, str]]) -> str:
    import csv
    import io

    out = io.StringIO()
    writer = csv.DictWriter(out, list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _from_capture(rows, managers: dict[str, str]):
    ids = {r["team_id"] for r in rows}
    capture = load_week(
        _text(rows),
        week=1,
        team_ids=ids,
        tz="America/Los_Angeles",
        calendar=lambda w: week_range(date(2026, 10, 20), w),
    )
    return build_capture_snapshot(
        capture,
        roster_capture=RosterCapture(rosters={}, team_names={}, managers=managers),
        existing=None,
        entry_id="entry-001",
        acquired_at=AT,
        season="2026-27",
        supersedes=None,
    )


def _no_games(line: CategoryLine) -> CategoryLine:
    # The capture carries no games played (spec Assumptions); nothing ranked
    # reads it, so it is normalized away rather than compared.
    return replace(line, games_played=0)


def test_yahoo_fixture_and_its_capture_agree(yahoo_week, yahoo_settings) -> None:
    api = build_snapshot(
        entry_id="entry-001",
        acquired_at=AT,
        season="2026-27",
        week=1,
        scoreboard=yahoo_week,
        stat_map=parse_stat_category_map(yahoo_settings),
    )
    id_map = {t.team_id: f"t.{i:02d}" for i, t in enumerate(api.teams, start=1)}
    captured = _from_capture(capture_rows_from_snapshot(api, id_map), managers={})

    assert [id_map[t.team_id] for t in api.teams] == [t.team_id for t in captured.teams]
    assert [t.name for t in api.teams] == [t.name for t in captured.teams]
    assert {id_map[k]: _no_games(v) for k, v in api.category_totals.items()} == {
        k: _no_games(v) for k, v in captured.category_totals.items()
    }
    assert sorted(
        tuple(sorted((id_map[m.home_team_id], id_map[m.away_team_id]))) for m in api.matchups
    ) == [(m.home_team_id, m.away_team_id) for m in captured.matchups]


def test_a_capture_renders_the_golden_week1_page() -> None:
    """Without projections neither source has a prior, so the pages must match."""
    original = make_snapshot(1)
    captured = _from_capture(
        capture_rows_from_snapshot(original),
        managers={t.team_id: t.manager_display_name for t in original.teams},
    )
    ranking = build_ranking([captured])
    report = internal_report.build(
        season="2026-27",
        week=1,
        entry_id="entry-001",
        ranking=ranking,
        events=derive_events(captured),
    )
    public = publishable_report.build(internal=report, history=[captured], is_projection=False)
    html = render_page(report=public, entry_id="entry-001", generated_at="2026-10-27").html
    assert html == GOLDEN.read_text(encoding="utf-8")
