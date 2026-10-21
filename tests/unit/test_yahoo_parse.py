"""Yahoo parsing, especially the two traps that silently corrupt data."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from ccsv_rumble.fetch.normalize import build_snapshot
from ccsv_rumble.fetch.provider import ProviderError
from ccsv_rumble.fetch.yahoo import (
    parse_stat_category_map,
    split_made_attempted,
)

# --- Trap 1: shooting stats are composite strings, not numbers ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("205/415", (205, 415)),
        ("0/12", (0, 12)),
        ("  18 / 40 ", (18, 40)),
    ],
)
def test_splits_composite_shooting_values(raw: str, expected: tuple[int, int]) -> None:
    assert split_made_attempted(raw) == expected


@pytest.mark.parametrize("raw", ["", "-", "-/-", "0/0", None])
def test_zero_attempt_cases_are_handled_explicitly(raw) -> None:
    """A team with no attempts that week must not raise."""
    assert split_made_attempted(raw) == (0, 0)


def test_a_bare_number_is_rejected_loudly() -> None:
    """The failure mode this guards: treating FG% as a float silently loses
    the attempts, and attempts cannot be reconstructed afterward."""
    with pytest.raises(ProviderError, match="composite"):
        split_made_attempted("0.494")


def test_impossible_shooting_line_is_rejected() -> None:
    with pytest.raises(ProviderError, match="exceeds"):
        split_made_attempted("50/40")


# --- Trap 2: stat ids are league-specific and must not be hardcoded -----------


def test_stat_map_resolves_all_nine_categories(yahoo_settings: dict) -> None:
    mapping = parse_stat_category_map(yahoo_settings)
    assert set(mapping.values()) == {
        "pts", "reb", "ast", "stl", "blk", "tpm", "to", "fg_pct", "ft_pct",
    }


def test_missing_category_fails_loudly(yahoo_settings: dict) -> None:
    """Silently proceeding would rank on eight categories without anyone noticing."""
    stripped = copy.deepcopy(yahoo_settings)
    stats = stripped["fantasy_content"]["league"][1]["settings"][0]["stat_categories"]["stats"]
    stats[:] = [s for s in stats if s["stat"]["display_name"] != "BLK"]

    with pytest.raises(ProviderError, match="blk"):
        parse_stat_category_map(stripped)


# --- Whole-payload extraction --------------------------------------------------


def test_builds_a_complete_snapshot(yahoo_settings: dict, yahoo_week: dict) -> None:
    mapping = parse_stat_category_map(yahoo_settings)
    snapshot = build_snapshot(
        entry_id="entry-001",
        acquired_at=datetime(2026, 10, 27, tzinfo=UTC),
        season="2026-27",
        week=1,
        scoreboard=yahoo_week,
        stat_map=mapping,
    )
    assert len(snapshot.teams) == 18
    assert len(snapshot.matchups) == 9
    assert all(team.name and team.manager_display_name for team in snapshot.teams)

    line = snapshot.category_totals[snapshot.teams[0].team_id]
    assert line.fga > 0 and line.fgm <= line.fga
    assert line.fta > 0 and line.ftm <= line.fta
    assert line.pts > 0


def test_percentages_are_never_stored(yahoo_settings: dict, yahoo_week: dict) -> None:
    """CategoryLine has makes and attempts only; a rounded percentage would be
    unrecoverable and unaggregatable."""
    import dataclasses

    from ccsv_rumble.models import CategoryLine

    names = {f.name for f in dataclasses.fields(CategoryLine)}
    assert "fg_pct" not in names and "ft_pct" not in names
    assert {"fgm", "fga", "ftm", "fta"} <= names
