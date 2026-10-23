"""Projection ingest, and the rejection the whole feature depends on.

FR-010 makes a percentage-only source a REJECTION rather than a degradation. The
worst available outcome here is a silent success: it would corrupt exactly the
two categories the week-0 category profile is published for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ccsv_rumble.fetch.projection_provider import ProjectionError
from ccsv_rumble.fetch.projections import (
    LocalFileProjectionProvider,
    acquire,
    parse_positions,
    parse_rows,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def _provider(name: str) -> LocalFileProjectionProvider:
    return LocalFileProjectionProvider(FIXTURES / name, source_id="test-source")


def test_valid_source_normalizes_with_provenance() -> None:
    snapshot = acquire(_provider("projections-valid.csv"), "2026-27", 0, now=NOW)
    assert len(snapshot.projections) == 180
    # FR-011: source identity and retrieval time archived WITH the numbers.
    assert snapshot.source_id == "test-source"
    assert snapshot.retrieved_at == NOW
    assert snapshot.target_week == 0


def test_valid_source_keeps_per_game_values_fractional() -> None:
    """The precision CategoryLine's int fields would have destroyed."""
    snapshot = acquire(_provider("projections-valid.csv"), "2026-27", 0, now=NOW)
    fgms = [p.per_game.fgm for p in snapshot.projections]
    assert any(v != int(v) for v in fgms), (
        "every fgm is a whole number -- per-game precision was lost at ingest"
    )


def test_percentage_only_source_is_rejected() -> None:
    """The go/no-go on any projection source (FR-010)."""
    with pytest.raises(ProjectionError) as excinfo:
        acquire(_provider("projections-percent-only.csv"), "2026-27", 0, now=NOW)
    message = str(excinfo.value)
    assert "fg_pct" in message
    # The message must name the fix, not merely refuse.
    assert "fgm" in message and "fga" in message


def test_percentage_rejection_happens_before_any_row_is_parsed() -> None:
    """Fail on the header, so one bad column cannot be half-ingested."""
    with pytest.raises(ProjectionError):
        parse_rows([{"fg_pct": ".458", "player_id": "p1"}])


def test_missing_projected_games_is_rejected() -> None:
    """FR-017: a real per-player schedule count, never a league-average constant."""
    row = {
        "player_id": "p1", "pts": "10", "reb": "4", "ast": "2", "stl": "1",
        "blk": "0.5", "tpm": "1", "to": "1",
        "fgm": "4", "fga": "9", "ftm": "2", "fta": "3",
    }
    with pytest.raises(ProjectionError, match="projected_games"):
        parse_rows([row])


def _good_row(**overrides: str) -> dict[str, str]:
    row = {
        "player_id": "p1", "name": "A", "positions": "PG", "projected_games": "4",
        "pts": "10", "reb": "4", "ast": "2", "stl": "1", "blk": "0.5",
        "tpm": "1", "to": "1", "fgm": "4", "fga": "9", "ftm": "2", "fta": "3",
    }
    row.update(overrides)
    return row


def test_attempts_below_makes_is_rejected_and_names_the_player() -> None:
    """A bare invariant message is not actionable against a 180-row file."""
    with pytest.raises(ProjectionError, match="p1"):
        parse_rows([_good_row(fgm="9", fga="4")])


def test_negative_value_is_rejected() -> None:
    with pytest.raises(ProjectionError, match="p1"):
        parse_rows([_good_row(pts="-1")])


def test_fractional_games_is_rejected() -> None:
    """Games played is a count; 3.5 means the source is not what it claims."""
    with pytest.raises(ProjectionError, match="whole number"):
        parse_rows([_good_row(projected_games="3.5")])


def test_duplicate_player_is_rejected() -> None:
    with pytest.raises(ProjectionError, match="duplicate"):
        parse_rows([_good_row(), _good_row()])


def test_empty_source_is_rejected() -> None:
    with pytest.raises(ProjectionError, match="no rows"):
        parse_rows([])


def test_missing_file_names_the_contract() -> None:
    provider = LocalFileProjectionProvider(FIXTURES / "does-not-exist.csv")
    with pytest.raises(ProjectionError, match="projection-source.md"):
        provider.fetch_projections("2026-27", 0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("PG,SG", ("PG", "SG")), ("pg, sf", ("PG", "SF")), ("", ()), (None, ())],
)
def test_parse_positions(raw: str, expected: tuple[str, ...]) -> None:
    assert parse_positions(raw) == expected
