"""Shared test fixtures.

Snapshots are built by hand rather than fetched, so every test runs offline.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ccsv_rumble.models import CategoryLine, Matchup, Snapshot, Team

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
