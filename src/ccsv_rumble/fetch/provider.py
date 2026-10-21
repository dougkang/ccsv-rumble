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
