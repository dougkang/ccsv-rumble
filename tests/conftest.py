"""Shared test fixtures.

Snapshots are built by hand rather than fetched, so every test runs offline.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ccsv_rumble import config
from ccsv_rumble.models import CategoryLine, Matchup, PlayerSlot, Snapshot, Team

FIXTURES = Path(__file__).parent / "fixtures"
TEAM_COUNT = 18


def make_line(seed: int) -> CategoryLine:
    rng = random.Random(seed)
    fga = rng.randint(300, 420)
    fgm = int(fga * rng.uniform(0.42, 0.52))
    fta = rng.randint(80, 150)
    ftm = int(fta * rng.uniform(0.70, 0.88))
    return CategoryLine(
        pts=rng.randint(480, 620),
        reb=rng.randint(170, 250),
        ast=rng.randint(90, 170),
        stl=rng.randint(25, 55),
        blk=rng.randint(15, 45),
        tpm=rng.randint(40, 85),
        to=rng.randint(45, 90),
        fgm=fgm,
        fga=fga,
        ftm=ftm,
        fta=fta,
        games_played=rng.randint(28, 40),
    )


def make_snapshot(
    week: int,
    *,
    entry_id: str = "entry-001",
    season: str = "2026-27",
    seed_offset: int = 0,
    supersedes: str | None = None,
) -> Snapshot:
    teams = tuple(
        Team(
            team_id=f"t.{i:02d}",
            name=f"Team {i:02d}",
            manager_display_name=f"Manager{i:02d}",
        )
        for i in range(1, TEAM_COUNT + 1)
    )
    totals = {
        team.team_id: make_line(week * 1000 + index + seed_offset)
        for index, team in enumerate(teams)
    }
    matchups = tuple(
        Matchup(
            week=week,
            home_team_id=teams[i].team_id,
            away_team_id=teams[i + 1].team_id,
        )
        for i in range(0, TEAM_COUNT, 2)
    )
    return Snapshot(
        entry_id=entry_id,
        acquired_at=datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
        season=season,
        week=week,
        week_start=date(2026, 10, 20),
        week_end=date(2026, 10, 26),
        teams=teams,
        category_totals=totals,
        matchups=matchups,
        stat_category_map={"12": "pts"},
        supersedes=supersedes,
    )


#: Positions cycled over a roster so every team can fill 2G + 3FC + 1 UTIL.
#: Index 0-1 guards, 2-4 forward/centre, then a dual-eligible swing player, then
#: bench depth. Deliberately not all-flex: a roster of pure guards could not fill
#: three FC slots, and a test built from one would never exercise eligibility.
_ROSTER_POSITIONS: tuple[tuple[str, ...], ...] = (
    ("PG",), ("SG",), ("SF",), ("PF",), ("C",),
    ("SG", "SF"), ("PG",), ("C",), ("PF",), ("SF",),
    ("SG",), ("C",),
)


def make_roster(
    team_id: str, size: int, *, with_positions: bool = True
) -> tuple[PlayerSlot, ...]:
    """A roster of `size` players for one team.

    `size` is what a DRAFT fills, so pass `config.DRAFT_ROSTER_SIZE` (10) for a
    drafted team -- the two IL slots start empty and are not part of it.
    """
    return tuple(
        PlayerSlot(
            player_id=f"nba.p.{team_id}.{i:02d}",
            name=f"Player {team_id}-{i:02d}",
            team_id=team_id,
            positions=_ROSTER_POSITIONS[i % len(_ROSTER_POSITIONS)]
            if with_positions
            else (),
        )
        for i in range(size)
    )


def make_post_draft_snapshot(
    *,
    roster_size: int = config.DRAFT_ROSTER_SIZE,
    short_teams: int = 0,
    completed_scored_weeks: int = 0,
    with_positions: bool = True,
) -> Snapshot:
    """A drafted league with no scored week: the week-0 state.

    Rosters hold `DRAFT_ROSTER_SIZE` (10) players and **IL is empty**, which is
    what a real completed draft looks like. A fixture built at 12 would make the
    lifecycle guard test pass for the wrong reason.
    """
    base = make_snapshot(0)
    rosters = {}
    for index, team in enumerate(base.teams):
        size = roster_size - 1 if index < short_teams else roster_size
        rosters[team.team_id] = make_roster(
            team.team_id, size, with_positions=with_positions
        )
    return replace(
        base,
        rosters=rosters,
        completed_scored_weeks=completed_scored_weeks,
    )


def write_rosters_csv(
    path: Path,
    *,
    roster_size: int = config.DRAFT_ROSTER_SIZE,
    short_teams: int = 0,
    with_positions: bool = True,
    teams: int = TEAM_COUNT,
    team_names: dict[str, str] | None = None,
    managers: dict[str, str] | None = None,
) -> Path:
    """Write the roster CSV `fetch/rosters.py` reads.

    Week 0 is acquired from this file rather than a scoreboard, so tests that
    exercise the week-0 route need a real one -- monkeypatching `build_snapshot`
    no longer reaches it.
    """
    header = "team_id,player_id,name,positions,status"
    if team_names is not None:
        header += ",team_name"
    if managers is not None:
        header += ",manager"
    rows = [header]
    for index in range(1, teams + 1):
        team_id = f"t.{index:02d}"
        size = roster_size - 1 if index <= short_teams else roster_size
        suffix = f",{team_names[team_id]}" if team_names is not None else ""
        if managers is not None:
            suffix += f",{managers.get(team_id, '')}"
        for slot in make_roster(team_id, size, with_positions=with_positions):
            positions = ",".join(slot.positions)
            quoted = f'"{positions}"' if "," in positions else positions
            rows.append(f"{team_id},{slot.player_id},{slot.name},{quoted},{suffix}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


#: The committed week-1 capture, in the matchups contract's 22-column format.
#: Real totals with scrubbed names; they pass the category-win checksum.
MATCHUPS_WEEK1 = FIXTURES / "matchups-week1.csv"


def read_matchup_rows(path: Path = MATCHUPS_WEEK1) -> list[dict[str, str]]:
    """The fixture's rows as dicts, for tests that edit one field and rewrite."""
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_matchups_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    captured_at: str | None = None,
    week_start: str | None = None,
    week_end: str | None = None,
) -> Path:
    """Write `data/matchups.csv`, optionally overriding the week metadata."""
    import csv

    overrides = {
        key: value
        for key, value in (
            ("captured_at", captured_at),
            ("week_start", week_start),
            ("week_end", week_end),
        )
        if value is not None
    }
    fields = list(rows[0]) if rows else list(read_matchup_rows()[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **overrides})
    return path


def capture_rows_from_snapshot(
    snapshot: Snapshot,
    id_map: dict[str, str] | None = None,
    *,
    captured_at: str = "2026-10-26T09:00:00-07:00",
    week_start: str = "2026-10-20",
    week_end: str = "2026-10-25",
) -> list[dict[str, str]]:
    """The matchups capture a browser would have produced for this snapshot.

    `cat_wins` is computed, so the result passes the checksum by construction.
    """
    from ccsv_rumble.rank.allplay import compare_category

    def pct(made: int, att: int) -> str:
        return f"{made / att:.3f}".lstrip("0") if att else "-"

    ids = id_map or {t.team_id: t.team_id for t in snapshot.teams}
    names = {t.team_id: t.name for t in snapshot.teams}
    rows: list[dict[str, str]] = []
    for index, matchup in enumerate(snapshot.matchups, start=1):
        for team, other in (
            (matchup.home_team_id, matchup.away_team_id),
            (matchup.away_team_id, matchup.home_team_id),
        ):
            line = snapshot.category_totals[team]
            versus = snapshot.category_totals[other]
            wins = sum(
                compare_category(line, versus, c) == 1.0 for c in config.CATEGORIES
            )
            rows.append(
                {
                    "week": str(snapshot.week),
                    "matchup": str(index),
                    "team_id": ids[team],
                    "team_name": names[team],
                    "opponent_id": ids[other],
                    **{
                        c: str(getattr(line, c))
                        for c in ("fgm", "fga", "ftm", "fta", "tpm", "pts",
                                  "reb", "ast", "stl", "blk", "to")
                    },
                    "fg_pct_display": pct(line.fgm, line.fga),
                    "ft_pct_display": pct(line.ftm, line.fta),
                    "cat_wins": str(wins),
                    "captured_at": captured_at,
                    "week_start": week_start,
                    "week_end": week_end,
                }
            )
    return rows


#: Display names in the shape the real league uses -- emoji, apostrophes, a
#: leading "#". The draft board names teams this way while every other stage
#: keys on `t.01`, so a test that uses ids for both would not exercise the
#: resolution step at all.
DISPLAY_NAMES = {
    f"t.{i:02d}": name
    for i, name in enumerate(
        [
            "Keyboard Cats", "Elsie’s World", "Triton Aggies",
            "#14th Scariest Team", "🥭 smoothie’s team",
            "The Lou Whoppers", "Sunday Best", "Potluck Heroes",
            "Narthex Narwhals", "Coffee Hour", "The Doxologists",
            "Fellowship Hall", "Pew Crew", "Vespers", "Hymn & Her",
            "Choir Loft", "Second Service", "Benediction",
        ],
        start=1,
    )
}


def write_draft_csv(
    path: Path,
    *,
    team_names: dict[str, str],
    rounds: int = 10,
    teams: int = TEAM_COUNT,
    drop_picks: tuple[int, ...] = (),
) -> Path:
    """Write the draft board `fetch/draft.py` reads, as a snake draft.

    `drop_picks` removes picks by overall number, which is how a test produces
    the partial board FR-049 treats as unavailable.
    """
    rows = ["round,pick_in_round,overall,player_id,player_name,nba_team,positions,team_name"]
    for rnd in range(1, rounds + 1):
        order = list(range(1, teams + 1))
        if rnd % 2 == 0:
            order.reverse()
        for slot, team_index in enumerate(order, start=1):
            overall = (rnd - 1) * teams + slot
            if overall in drop_picks:
                continue
            team_id = f"t.{team_index:02d}"
            rows.append(
                f"{rnd},{slot},{overall},nba.p.{1000 + overall},"
                f"Player {overall},LAL,G,{team_names[team_id]}"
            )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def post_draft_snapshot() -> Snapshot:
    return make_post_draft_snapshot()


@pytest.fixture
def snapshot() -> Snapshot:
    return make_snapshot(1)


@pytest.fixture
def history() -> list[Snapshot]:
    return [make_snapshot(week) for week in (1, 2, 3)]


@pytest.fixture
def yahoo_settings() -> dict:
    return json.loads((FIXTURES / "yahoo_settings.json").read_text())


@pytest.fixture
def yahoo_week() -> dict:
    return json.loads((FIXTURES / "yahoo_week.json").read_text())
