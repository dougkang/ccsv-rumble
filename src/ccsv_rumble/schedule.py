"""Which weeks a run must process.

Resolves the target week in the league timezone (never the host's local time),
detects gaps in the archive (FR-037), and returns the correction re-check window
(FR-045).

The ordering this produces is load-bearing: corrections must be acquired before
any ranking is computed, because a correction to week 5 changes the
recency-weighted history that week 6's ranking is built from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .archive.store import ArchiveStore


@dataclass(frozen=True)
class RunPlan:
    """What one run will do, decided before any network call."""

    season: str
    #: Weeks absent from the archive, ascending. Each gets its own published page.
    gap_weeks: tuple[int, ...]
    #: Completed weeks to re-fetch looking for upstream corrections.
    recheck_weeks: tuple[int, ...]
    #: The week this run is primarily publishing.
    current_week: int

    @property
    def weeks_to_publish(self) -> tuple[int, ...]:
        """Gaps ascending, then the current week (FR-039)."""
        ordered = [w for w in self.gap_weeks if w != self.current_week]
        return (*ordered, self.current_week)


def now_in_league_tz(clock: datetime | None = None) -> datetime:
    tz = ZoneInfo(config.LEAGUE_TIMEZONE)
    if clock is not None:
        return clock.astimezone(tz) if clock.tzinfo else clock.replace(tzinfo=tz)
    return datetime.now(tz)


def _week_one_end(season_start: date) -> date:
    """The first Sunday on or after opening day."""
    return season_start + timedelta(days=(6 - season_start.weekday()) % 7)


def week_for_date(season_start: date, when: date) -> int:
    """League matchup week containing `when`, 1-indexed.

    Week 1 runs from opening day through the first Sunday; every later week runs
    Monday through Sunday. Counting seven-day weeks from opening day instead puts
    each boundary a day late -- a Monday run then treats the week that ended the
    night before as still in progress (research R10).

    Known break: Yahoo merges the All-Star break into one long week, which no
    formula of this shape reproduces. Capture-sourced weeks record the league's
    own dates and are checked against `week_range`, so that break surfaces as a
    named failure rather than a silently shifted calendar.
    """
    if when < season_start:
        return 0
    first_end = _week_one_end(season_start)
    if when <= first_end:
        return 1
    return 2 + (when - first_end - timedelta(days=1)).days // 7


def week_range(season_start: date, week: int) -> tuple[date, date]:
    """First and last scoring day of `week` (>= 1); the inverse of `week_for_date`."""
    if week < 1:
        raise ValueError(f"week {week} has no scoring days")
    first_end = _week_one_end(season_start)
    if week == 1:
        return season_start, first_end
    start = first_end + timedelta(days=1 + 7 * (week - 2))
    return start, start + timedelta(days=6)


def build_plan(
    store: ArchiveStore,
    season: str,
    season_start: date,
    *,
    explicit_week: int | None = None,
    backfill: bool = True,
    recheck_weeks: int | None = None,
    clock: datetime | None = None,
) -> RunPlan:
    today = now_in_league_tz(clock).date()
    completed = max(0, week_for_date(season_start, today) - 1)

    if explicit_week is not None:
        # --week skips gap detection entirely: the deliberate single-week escape hatch.
        return RunPlan(
            season=season,
            gap_weeks=(),
            recheck_weeks=(),
            current_week=explicit_week,
        )

    archived = set(store.archived_weeks(season))
    gaps = tuple(w for w in range(1, completed + 1) if w not in archived)

    window = config.RECHECK_WEEKS if recheck_weeks is None else recheck_weeks
    recheck = tuple(
        w
        for w in range(max(1, completed - window + 1), completed + 1)
        if w in archived
    )

    # Before any week has completed, target WEEK 0 -- the post-draft projection
    # page -- rather than week 1.
    #
    # This used to return 1, which made the week-0 path unreachable from the
    # scheduled job: `build_plan` never produced 0, so only an explicit
    # `--week 0` could get there. Week 1 is also the wrong target before any
    # games are scored, since there are no results to rank.
    #
    # Week 0 is not published unconditionally: the lifecycle gate still decides.
    # An undrafted league classifies PRE_DRAFT and publishes nothing, exiting
    # zero without notifying.
    current = completed if completed >= 1 else 0
    return RunPlan(
        season=season,
        gap_weeks=gaps if backfill else (),
        recheck_weeks=recheck,
        current_week=current,
    )
