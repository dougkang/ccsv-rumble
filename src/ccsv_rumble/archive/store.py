"""Append-only archive, one directory per league week, many entries per week.

The `entry-NNN` level is what makes two constitutional requirements compatible:
Principle III says corrections are added as new entries and history is not
rewritten, while FR-045 requires re-checking recent weeks for corrections. Under
a one-snapshot-per-week layout those are mutually exclusive.

Two accessors exist on purpose and neither has a default:

    latest_entry(season, week)      -- what ranking computes from (FR-047)
    entry(season, week, entry_id)   -- what replay renders from   (FR-049)

Conflating them silently breaks either SC-005 or FR-047, so the caller is forced
to say which one it means.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..models import Article, Snapshot
from . import scrub, serde

_ENTRY_RE = re.compile(r"^entry-(\d{3})$")


class ArchiveError(RuntimeError):
    """Raised on a layout violation or an attempted overwrite."""


@dataclass(frozen=True)
class EntryPaths:
    root: Path
    entry_id: str

    @property
    def raw(self) -> Path:
        return self.root / "raw-yahoo.json"

    @property
    def snapshot(self) -> Path:
        return self.root / "snapshot.json"

    @property
    def internal(self) -> Path:
        return self.root / "internal.json"

    @property
    def publishable(self) -> Path:
        return self.root / "publishable.json"

    @property
    def article(self) -> Path:
        return self.root / "article.json"


class ArchiveStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- layout ---------------------------------------------------------------

    def week_dir(self, season: str, week: int) -> Path:
        return self.root / season / f"week-{week:02d}"

    def list_entry_ids(self, season: str, week: int) -> list[str]:
        wd = self.week_dir(season, week)
        if not wd.is_dir():
            return []
        ids = [p.name for p in wd.iterdir() if p.is_dir() and _ENTRY_RE.match(p.name)]
        return sorted(ids)

    def has_week(self, season: str, week: int) -> bool:
        return bool(self.list_entry_ids(season, week))

    def archived_weeks(self, season: str) -> list[int]:
        season_dir = self.root / season
        if not season_dir.is_dir():
            return []
        weeks = []
        for p in sorted(season_dir.iterdir()):
            if p.is_dir() and p.name.startswith("week-"):
                try:
                    weeks.append(int(p.name.removeprefix("week-")))
                except ValueError:
                    continue
        return sorted(weeks)

    def next_entry_id(self, season: str, week: int) -> str:
        existing = self.list_entry_ids(season, week)
        nxt = len(existing) + 1
        return f"entry-{nxt:03d}"

    def paths(self, season: str, week: int, entry_id: str) -> EntryPaths:
        return EntryPaths(self.week_dir(season, week) / entry_id, entry_id)

    # --- writes ---------------------------------------------------------------

    def create_entry(self, season: str, week: int, entry_id: str) -> EntryPaths:
        """Create a new entry directory. Raises if it already exists.

        The store creates; it never opens an existing entry for write.
        """
        p = self.paths(season, week, entry_id)
        if p.root.exists():
            raise ArchiveError(
                f"{season} week {week} {entry_id} already exists; "
                "archive entries are append-only and never overwritten"
            )
        p.root.mkdir(parents=True)
        return p

    def _write(self, path: Path, payload: object) -> None:
        # Scrubbing happens here, on the write path, so no call site can skip it.
        text = serde.dumps(scrub.scrub(serde.to_jsonable(payload)))
        path.write_text(text, encoding="utf-8")

    def write_raw(self, paths: EntryPaths, raw: object) -> None:
        self._write(paths.raw, raw)

    def write_snapshot(self, paths: EntryPaths, snapshot: Snapshot) -> None:
        self._write(paths.snapshot, snapshot)

    def write_internal(self, paths: EntryPaths, report: object) -> None:
        self._write(paths.internal, report)

    def write_publishable(self, paths: EntryPaths, report: object) -> None:
        self._write(paths.publishable, report)

    def write_article(self, paths: EntryPaths, article: Article) -> None:
        """Archive the article -- including a rejected one, with its reasons (FR-027)."""
        self._write(paths.article, article)

    # --- reads ----------------------------------------------------------------

    def latest_entry_id(self, season: str, week: int) -> str:
        ids = self.list_entry_ids(season, week)
        if not ids:
            raise ArchiveError(f"no archived entry for {season} week {week}")
        return ids[-1]

    def latest_entry(self, season: str, week: int) -> Snapshot:
        """The newest entry -- what ranking computes from, so corrections apply
        to current and future rankings (FR-047)."""
        return self.entry(season, week, self.latest_entry_id(season, week))

    def entry(self, season: str, week: int, entry_id: str) -> Snapshot:
        """One specific entry -- what replay renders from, so a published page
        reproduces rather than being regenerated from a correction (FR-049)."""
        path = self.paths(season, week, entry_id).snapshot
        if not path.is_file():
            raise ArchiveError(f"missing snapshot for {season} week {week} {entry_id}")
        return serde.snapshot_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def read_article(self, season: str, week: int, entry_id: str) -> Article | None:
        path = self.paths(season, week, entry_id).article
        if not path.is_file():
            return None
        return serde.article_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def read_publishable_raw(self, season: str, week: int, entry_id: str) -> dict | None:
        path = self.paths(season, week, entry_id).publishable
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
