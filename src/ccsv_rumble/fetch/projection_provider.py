"""The projection provider seam.

The only input in this project that originates outside the league. FR-015
requires it be isolated behind the same kind of interface as league data, so the
source can be replaced without touching ranking or rendering.

Mirrors `provider.py`: raw out, normalization separate and pure.
"""

from __future__ import annotations

from typing import Any, Protocol


class ProjectionProvider(Protocol):
    def source_id(self) -> str:
        """Stable identity of the source, archived with the snapshot (FR-011)."""
        ...

    def fetch_projections(self, season: str, target_week: int) -> list[dict[str, Any]]:
        """RAW, unnormalized rows. Archived verbatim before parsing."""
        ...


class ProjectionError(RuntimeError):
    """Acquisition or validation failure.

    Per FR-038 this means publish nothing, exit non-zero, notify. Never proceed
    with partial projection data -- a ranking computed from mostly-missing inputs
    is a broken page, not a degraded one.
    """
