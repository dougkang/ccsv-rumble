"""The provider seam.

The constitution requires the fetch layer be isolated behind an interface so the
provider can be replaced without touching ranking or rendering code. Every method
returns RAW, unnormalized provider data, which is archived verbatim before any
parsing (Principle III). Normalization is a separate, pure step -- so swapping
providers changes this package and the normalizer, and nothing downstream.
"""

from __future__ import annotations

from typing import Any, Protocol


class LeagueDataProvider(Protocol):
    def fetch_stat_category_map(self, season: str) -> dict[str, str]:
        """Yahoo stat_id -> canonical category name, read from league settings."""
        ...

    def fetch_week(self, season: str, week: int) -> dict[str, Any]:
        """Raw scoreboard payload for one week, covering every team."""
        ...

    def fetch_rosters(self, season: str, week: int) -> dict[str, Any]:
        ...

    def fetch_transactions(self, season: str, week: int) -> dict[str, Any]:
        ...


class ProviderError(RuntimeError):
    """Upstream failure. Per Principle II this means report and publish nothing."""


class WeekNotCaptured(ProviderError):
    """The committed capture has no rows for this week.

    Distinct from a defective capture: when re-checking a week the archive
    already holds, this is not a failure -- the archived version stands (research
    R4). For a week being published or backfilled there is nothing to fall back
    on, and it fails like any other acquisition error.
    """

    def __init__(self, week: int, path: str = "data/matchups.csv") -> None:
        self.week = week
        super().__init__(
            f"week {week} is not in {path}. Capture it after the week ends with "
            f"`uv run python tools/chrome_capture.py matchups --week {week}`, "
            "then commit and push."
        )
