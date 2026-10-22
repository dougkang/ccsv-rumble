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
