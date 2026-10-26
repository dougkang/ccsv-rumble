"""League data from the committed capture, `data/matchups.csv`.

The Yahoo app is gated behind Yahoo's review, so weeks >= 1 are captured from the
maintainer's own browser and committed (specs/004, Decision). This module is how
the unattended run reads that commit. The contract is
specs/005-captured-league-provider/contracts/matchups-capture.md.

ONE THING NOT TO DO, because it is the obvious shortcut and it is wrong:
do not reshape these rows into a Yahoo scoreboard so `normalize.build_snapshot`
can parse them. The archive would then hold a payload Yahoo never sent, and a
parser bug would be diagnosed against invented data (Principle III). The rows
ARE the raw input; they are archived verbatim and normalized here.

Structured like `rosters.py`: pure parsing and validation first, then the I/O.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import config
from ..models import CategoryLine, Matchup, Snapshot, Team, TeamId, ValidationError
from ..rank.allplay import compare_category
from . import rosters as roster_source
from .provider import ProviderError, WeekNotCaptured

#: The counting columns, in contract order.
INT_COLUMNS: tuple[str, ...] = (
    "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "to",
)
REQUIRED_COLUMNS: tuple[str, ...] = (
    "week", "matchup", "team_id", "team_name", "opponent_id",
    *INT_COLUMNS,
    "fg_pct_display", "ft_pct_display", "cat_wins",
    "captured_at", "week_start", "week_end",
)
#: Display columns backing each ratio category, for the checksum only.
_DISPLAY_COLUMNS: dict[str, str] = {"fg_pct": "fg_pct_display", "ft_pct": "ft_pct_display"}
_DISPLAY_PATTERN = re.compile(r"\d?\.\d+")

DEFAULT_PATH = "data/matchups.csv"


@dataclass(frozen=True)
class CaptureRow:
    """One team's side of one matchup."""

    matchup: int
    team_id: TeamId
    team_name: str
    opponent_id: TeamId
    totals: CategoryLine
    #: Yahoo's rounded percentages. A checksum, never an input (R2).
    display: dict[str, str]
    #: Categories won, as the page shows it. May be fractional if the league
    #: counts a tie as half; the checksum accepts either convention.
    cat_wins: float


@dataclass(frozen=True)
class WeekCapture:
    """Every row the capture holds for one week, plus when it was taken."""

    week: int
    captured_at: datetime
    week_start: date
    week_end: date
    rows: tuple[CaptureRow, ...]
    #: The header plus this week's original lines, byte for byte (FR-014).
    raw_text: str


# --- Pure parsing and validation ----------------------------------------------


def _int(row: dict[str, str], column: str, team_id: str) -> int:
    value = (row.get(column) or "").strip()
    if not re.fullmatch(r"\d+", value):
        raise ProviderError(
            f"team {team_id}: column `{column}` is {value!r}, not a whole number. "
            "A column was probably misread; recapture the week."
        )
    return int(value)


def _parse_row(row: dict[str, str]) -> CaptureRow:
    team_id = (row.get("team_id") or "").strip()
    counts = {column: _int(row, column, team_id) for column in INT_COLUMNS}
    try:
        totals = CategoryLine(**counts)
    except ValidationError as exc:
        raise ProviderError(f"team {team_id}: {exc}") from exc
    return CaptureRow(
        matchup=_int(row, "matchup", team_id),
        team_id=team_id,
        team_name=(row.get("team_name") or "").strip(),
        opponent_id=(row.get("opponent_id") or "").strip(),
        totals=totals,
        display={cat: (row.get(col) or "").strip() for cat, col in _DISPLAY_COLUMNS.items()},
        cat_wins=_wins(row, team_id),
    )


def _wins(row: dict[str, str], team_id: str) -> float:
    value = (row.get("cat_wins") or "").strip()
    if not re.fullmatch(r"\d+(\.5)?", value):
        raise ProviderError(
            f"team {team_id}: column `cat_wins` is {value!r}, not a category count"
        )
    return float(value)


def _one_value(rows: list[dict[str, str]], column: str, week: int) -> str:
    values = {(row.get(column) or "").strip() for row in rows}
    if values == {""}:
        raise ProviderError(
            f"week {week} has no `{column}`. Rows written before the capture "
            "recorded it cannot be trusted as final; recapture the week."
        )
    if len(values) != 1:
        raise ProviderError(
            f"week {week} rows disagree on `{column}`: {sorted(values)}. "
            "One capture writes one value per week; recapture the week."
        )
    return values.pop()


def _week_metadata(rows: list[dict[str, str]], week: int) -> tuple[datetime, date, date]:
    raw_at = _one_value(rows, "captured_at", week)
    raw_start = _one_value(rows, "week_start", week)
    raw_end = _one_value(rows, "week_end", week)
    try:
        captured_at = datetime.fromisoformat(raw_at)
        start, end = date.fromisoformat(raw_start), date.fromisoformat(raw_end)
    except ValueError as exc:
        raise ProviderError(f"week {week} metadata is malformed: {exc}") from exc
    if captured_at.tzinfo is None:
        # A naive time cannot be compared to the league's week end: the same
        # string is before midnight in one zone and after it in another.
        raise ProviderError(f"week {week} `captured_at` {raw_at!r} has no UTC offset")
    return captured_at, start, end


def _check_coverage(
    rows: tuple[CaptureRow, ...], week: int, teams: int, team_ids: set[TeamId]
) -> None:
    seen: dict[str, int] = {}
    for row in rows:
        seen[row.team_id] = seen.get(row.team_id, 0) + 1
    twice = sorted(t for t, n in seen.items() if n > 1)
    if twice:
        raise ProviderError(f"week {week} lists {twice} more than once")
    if len(rows) != teams:
        absent = sorted(team_ids - set(seen))
        raise ProviderError(
            f"week {week} has {len(rows)} teams, expected {teams}"
            + (f"; missing {absent}" if absent else "")
            + ". All-play needs the full grid, so a partial week cannot be ranked."
        )
    by_id = {row.team_id: row for row in rows}
    for row in rows:
        other = by_id.get(row.opponent_id)
        if other is None or other.opponent_id != row.team_id or other.matchup != row.matchup:
            raise ProviderError(
                f"week {week}: {row.team_id} lists opponent {row.opponent_id}, "
                "who does not list it back in the same matchup"
            )
    matchups = {row.matchup for row in rows}
    if len(matchups) != teams // 2:
        raise ProviderError(
            f"week {week} has {len(matchups)} matchups, expected {teams // 2}"
        )


def wins_and_ties(a: CaptureRow, b: CaptureRow, *, displayed: bool) -> tuple[int, int]:
    """Categories `a` takes outright from `b`, and categories tied.

    With `displayed`, the ratio categories compare Yahoo's rounded percentages
    instead of made/attempted, falling back to the exact comparison when a
    display value is absent (zero attempts shows "-").
    """
    wins = ties = 0
    for category in config.CATEGORIES:
        shown_a = a.display.get(category, "")
        shown_b = b.display.get(category, "")
        if (
            displayed
            and category in config.RATIO_CATEGORIES
            and _DISPLAY_PATTERN.fullmatch(shown_a)
            and _DISPLAY_PATTERN.fullmatch(shown_b)
        ):
            score = 1.0 if float(shown_a) > float(shown_b) else (
                0.5 if float(shown_a) == float(shown_b) else 0.0
            )
        else:
            score = compare_category(a.totals, b.totals, category)
        wins += score == 1.0
        ties += score == 0.5
    return wins, ties


def acceptable_win_counts(a: CaptureRow, b: CaptureRow) -> set[float]:
    """Every count the page could show for `a` from correctly read totals.

    Two unknowns, so four candidates. Yahoo may compare percentages at display
    precision, which makes .4412 vs .4408 a tie (R2); and it may count a tie as
    half a category or as none. Week 1 settles neither. A misread column still
    moves the true count off every candidate.
    """
    counts: set[float] = set()
    for displayed in (False, True):
        wins, ties = wins_and_ties(a, b, displayed=displayed)
        counts |= {float(wins), wins + ties / 2}
    return counts


def _check_category_wins(rows: tuple[CaptureRow, ...], week: int) -> None:
    """FR-008: the checksum that catches a misread column."""
    by_id = {row.team_id: row for row in rows}
    for row in rows:
        other = by_id[row.opponent_id]
        if row.cat_wins not in acceptable_win_counts(row, other):
            exact, _ = wins_and_ties(row, other, displayed=False)
            raise ProviderError(
                f"week {week}: {row.team_id} vs {other.team_id} records "
                f"{row.cat_wins:g} category wins for {row.team_id}, but the captured "
                f"totals give {exact}. A column was probably misread; recapture."
            )


def load_week(
    text: str,
    *,
    week: int,
    team_ids: set[TeamId],
    tz: str,
    calendar: Callable[[int], tuple[date, date]],
    teams: int = config.TEAM_COUNT,
    source: str = DEFAULT_PATH,
) -> WeekCapture:
    """Parse and validate one week. Pure: the text, rosters and calendar are inputs.

    Checks run cheapest and most specific first, so the first failure names the
    real defect (data-model.md, Validation order).
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ProviderError(f"{source} is empty")
    reader = csv.DictReader(io.StringIO("\n".join(lines) + "\n"))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ProviderError(
            f"{source} is missing columns {missing}. Captures written before "
            "captured_at/week_start/week_end were recorded cannot be trusted as "
            "final; recapture with tools/chrome_capture.py."
        )
    all_rows = list(reader)
    if len(all_rows) != len(lines) - 1:
        raise ProviderError(f"{source} has a row spanning several lines; recapture")

    picked = [
        (line, row)
        for line, row in zip(lines[1:], all_rows, strict=True)
        if (row.get("week") or "").strip() == str(week)
    ]
    if not picked:
        raise WeekNotCaptured(week, source)
    raw_rows = [row for _, row in picked]

    rows = tuple(_parse_row(row) for row in raw_rows)
    captured_at, start, end = _week_metadata(raw_rows, week)
    _check_coverage(rows, week, teams, team_ids)
    unknown = sorted({row.team_id for row in rows} - team_ids)
    if unknown:
        raise ProviderError(
            f"week {week} has team ids {unknown} that are not in the roster "
            "capture. Recapture rosters and matchups together "
            "(`chrome_capture.py dailies`)."
        )
    _check_category_wins(rows, week)

    expected = calendar(week)
    if (start, end) != expected:
        raise ProviderError(
            f"week {week} is {start}..{end} in the capture but "
            f"{expected[0]}..{expected[1]} in the league calendar "
            "(schedule.week_range). If the league changed its week shape -- the "
            "All-Star break does -- the calendar needs updating."
        )
    local = captured_at.astimezone(ZoneInfo(tz))
    if local.date() <= end:
        raise ProviderError(
            f"week {week} was captured {local.isoformat(timespec='minutes')}, "
            f"before it ended ({end}). Games may still have been in progress; "
            f"recapture after {end}."
        )

    return WeekCapture(
        week=week,
        captured_at=captured_at,
        week_start=start,
        week_end=end,
        rows=rows,
        raw_text="\n".join([lines[0], *(line for line, _ in picked)]) + "\n",
    )


def build_capture_snapshot(
    capture: WeekCapture,
    *,
    roster_capture: roster_source.RosterCapture,
    existing: Snapshot | None,
    entry_id: str,
    acquired_at: datetime,
    season: str,
    supersedes: str | None,
) -> Snapshot:
    """WeekCapture -> Snapshot, the same shape `normalize.build_snapshot` builds.

    Rosters come from the archive when the week is already archived, and from
    the roster capture otherwise (R5). `rosters.csv` is the league as of capture
    time: attaching it to a past week would rewrite that week's history, and
    `archive/diff` would then archive every waiver move as a stat correction.
    """
    rows = sorted(capture.rows, key=lambda r: r.team_id)
    teams = tuple(
        Team(
            team_id=row.team_id,
            name=row.team_name or row.team_id,
            manager_display_name=roster_capture.managers.get(row.team_id, ""),
        )
        for row in rows
    )
    pairs = {tuple(sorted((row.team_id, row.opponent_id))) for row in rows}
    return Snapshot(
        entry_id=entry_id,
        acquired_at=acquired_at,
        season=season,
        week=capture.week,
        week_start=capture.week_start,
        week_end=capture.week_end,
        teams=teams,
        category_totals={row.team_id: row.totals for row in rows},
        matchups=tuple(
            Matchup(week=capture.week, home_team_id=home, away_team_id=away)
            for home, away in sorted(pairs)
        ),
        rosters=dict(existing.rosters) if existing is not None else roster_capture.rosters,
        stat_category_map={},
        supersedes=supersedes,
        raw_source="matchups.csv",
    )


# --- I/O ----------------------------------------------------------------------


class CapturedProvider:
    """`LeagueDataProvider` over the committed capture. No network, no credentials."""

    def __init__(
        self,
        matchups_path: Path,
        rosters_path: Path,
        *,
        season_start: date,
        tz: str = config.LEAGUE_TIMEZONE,
    ) -> None:
        self.matchups_path = matchups_path
        self.rosters_path = rosters_path
        self.season_start = season_start
        self.tz = tz
        self._rosters: roster_source.RosterCapture | None = None

    def _roster_capture(self) -> roster_source.RosterCapture:
        if self._rosters is None:
            if not self.rosters_path.is_file():
                raise ProviderError(
                    f"{self.rosters_path} not found. Weeks >= 1 need the roster "
                    "capture for team ids and managers; capture both with "
                    "`chrome_capture.py dailies`."
                )
            self._rosters = roster_source.load(self.rosters_path)
        return self._rosters

    def captured_weeks(self) -> list[int]:
        """Weeks with at least one row, for the run log (FR-004)."""
        if not self.matchups_path.is_file():
            return []
        with self.matchups_path.open(encoding="utf-8", newline="") as handle:
            weeks = {(row.get("week") or "").strip() for row in csv.DictReader(handle)}
        return sorted(int(w) for w in weeks if w.isdigit())

    def fetch_stat_category_map(self, season: str) -> dict[str, str]:
        # The capture is keyed by canonical names already; there are no stat ids.
        return {}

    def fetch_week(self, season: str, week: int) -> dict[str, Any]:
        from ..schedule import week_range

        if not self.matchups_path.is_file():
            raise WeekNotCaptured(week, str(self.matchups_path))
        rosters = self._roster_capture()
        capture = load_week(
            self.matchups_path.read_text(encoding="utf-8"),
            week=week,
            team_ids=set(rosters.rosters) | set(rosters.team_names),
            tz=self.tz,
            calendar=lambda w: week_range(self.season_start, w),
            source=str(self.matchups_path),
        )
        return {"capture": capture, "rosters": rosters, "text": capture.raw_text}

    def fetch_rosters(self, season: str, week: int) -> dict[str, Any]:
        return {}

    def fetch_transactions(self, season: str, week: int) -> dict[str, Any]:
        return {}
