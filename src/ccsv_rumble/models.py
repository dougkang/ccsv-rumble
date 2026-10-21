"""Typed data structures. Declarative only -- no behavior beyond validation.

The single most important property here: `PublishableTeam` has no field capable of
holding a ranking-derived number other than rank and movement. Spec FR-032 is
therefore enforced by the type, not by remembering to leave numbers out of a
template. If a power score cannot be represented, it cannot leak onto the page or
into the article prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from . import config

TeamId = str


class Movement(StrEnum):
    SIGNIFICANT = "significant"
    WITHIN_NOISE = "within_noise"
    UNAVAILABLE = "unavailable"


class LuckBand(StrEnum):
    VERY_LUCKY = "VERY_LUCKY"
    LUCKY = "LUCKY"
    NEUTRAL = "NEUTRAL"
    UNLUCKY = "UNLUCKY"
    VERY_UNLUCKY = "VERY_UNLUCKY"


class EventType(StrEnum):
    INJURY_STATUS = "injury_status"
    TRADE = "trade"
    ADD = "add"
    DROP = "drop"
    STANDOUT_PERFORMANCE = "standout_performance"


class ValidationError(ValueError):
    """Raised when a model violates a documented invariant."""


# --- Snapshot ----------------------------------------------------------------


@dataclass(frozen=True)
class CategoryLine:
    """One team's totals for one week.

    No percentage fields exist. `fg_pct` is computed at comparison time from
    `fgm`/`fga` and never stored: a stored percentage cannot be re-aggregated or
    compared at the right granularity once rounded, and the information is
    unrecoverable afterward.
    """

    pts: int = 0
    reb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tpm: int = 0
    to: int = 0
    fgm: int = 0
    fga: int = 0
    ftm: int = 0
    fta: int = 0
    games_played: int = 0

    def __post_init__(self) -> None:
        # "fgm <= fga, ftm <= fta, all values non-negative" (data-model.md s2)
        if self.fgm > self.fga:
            raise ValidationError(f"fgm {self.fgm} exceeds fga {self.fga}")
        if self.ftm > self.fta:
            raise ValidationError(f"ftm {self.ftm} exceeds fta {self.fta}")
        for name in (
            "pts", "reb", "ast", "stl", "blk", "tpm", "to",
            "fgm", "fga", "ftm", "fta", "games_played",
        ):
            if getattr(self, name) < 0:
                raise ValidationError(f"{name} is negative: {getattr(self, name)}")


@dataclass(frozen=True)
class Team:
    team_id: TeamId
    name: str
    manager_display_name: str


@dataclass(frozen=True)
class Matchup:
    week: int
    home_team_id: TeamId
    away_team_id: TeamId


@dataclass(frozen=True)
class PlayerSlot:
    player_id: str
    name: str
    team_id: TeamId
    status: str = ""


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    type: EventType
    occurred_on: date
    team_ids: tuple[TeamId, ...]
    player_name: str | None = None


@dataclass(frozen=True)
class PlayerWeek:
    player_id: str
    name: str
    team_id: TeamId
    week: int
    line: CategoryLine


@dataclass(frozen=True)
class Snapshot:
    """Everything one run acquired for one week.

    A week may have several snapshots over time -- the original plus any
    corrections -- distinguished by `entry_id`.
    """

    entry_id: str
    acquired_at: datetime
    season: str
    week: int
    week_start: date
    week_end: date
    teams: tuple[Team, ...]
    category_totals: dict[TeamId, CategoryLine]
    matchups: tuple[Matchup, ...] = ()
    rosters: dict[TeamId, tuple[PlayerSlot, ...]] = field(default_factory=dict)
    transactions: tuple[Transaction, ...] = ()
    player_weeks: tuple[PlayerWeek, ...] = ()
    stat_category_map: dict[str, str] = field(default_factory=dict)
    supersedes: str | None = None
    raw_source: str = ""

    def __post_init__(self) -> None:
        # "len(teams) == 18; every team present in category_totals" (data-model.md s1)
        if len(self.teams) != config.TEAM_COUNT:
            raise ValidationError(
                f"expected {config.TEAM_COUNT} teams, got {len(self.teams)}"
            )
        missing = [t.team_id for t in self.teams if t.team_id not in self.category_totals]
        if missing:
            raise ValidationError(f"teams missing category totals: {sorted(missing)}")


# --- Ranking -----------------------------------------------------------------


@dataclass(frozen=True)
class RankingEntry:
    team_id: TeamId
    rank: int
    previous_rank: int | None
    rank_change: int | None
    movement: Movement
    # Internal only -- never published.
    power_score: float = 0.0
    emw: float = 0.0
    caw: float = 0.0
    roster_prior: float | None = None
    performance_weight: float = 0.0
    category_profile: dict[str, float] = field(default_factory=dict)
    actual_win_pct: float | None = None
    schedule_luck: float | None = None
    luck_band: LuckBand | None = None

    def __post_init__(self) -> None:
        # "movement is UNAVAILABLE if and only if previous_rank is None"
        unavailable = self.movement is Movement.UNAVAILABLE
        if unavailable != (self.previous_rank is None):
            raise ValidationError(
                f"team {self.team_id}: movement={self.movement.value} but "
                f"previous_rank={self.previous_rank}; these must agree"
            )


@dataclass(frozen=True)
class Ranking:
    algorithm_version: str
    week: int
    entries: tuple[RankingEntry, ...]

    def __post_init__(self) -> None:
        # "ranks are exactly 1..18 with no gaps or duplicates" (data-model.md s3)
        ranks = sorted(e.rank for e in self.entries)
        if ranks != list(range(1, len(self.entries) + 1)):
            raise ValidationError(f"ranks are not a clean 1..N sequence: {ranks}")


# --- Events ------------------------------------------------------------------


@dataclass(frozen=True)
class NotableEvent:
    event_id: str
    type: EventType
    team_ids: tuple[TeamId, ...]
    summary: str
    occurred_on: date
    player_name: str | None = None
    detail: dict[str, str | int] = field(default_factory=dict)


# --- Reports -----------------------------------------------------------------


@dataclass(frozen=True)
class InternalReport:
    """Full ranking detail. Archived, never published."""

    season: str
    week: int
    entry_id: str
    algorithm_version: str
    ranking: Ranking
    events: tuple[NotableEvent, ...]
    constants: dict[str, float]


@dataclass(frozen=True)
class PublishableTeam:
    """Deliberately absent: power_score, emw, caw, roster_prior,
    performance_weight, category_profile, schedule_luck.

    There is no field to put them in. That is the enforcement mechanism for
    FR-032, and it is why this class must never grow a numeric metric field.
    """

    team_id: TeamId
    team_name: str
    manager_display_name: str
    rank: int
    previous_rank: int | None
    rank_change: int | None
    movement: Movement
    record: str
    luck_band: LuckBand | None = None
    category_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublishableEvent:
    event_id: str
    type: EventType
    team_ids: tuple[TeamId, ...]
    summary: str
    occurred_on: date
    player_name: str | None = None


@dataclass(frozen=True)
class PublishableReport:
    """The only input to article generation and rendering."""

    season: str
    week: int
    is_projection: bool
    teams: tuple[PublishableTeam, ...]
    events: tuple[PublishableEvent, ...]
    is_current_week: bool = True


# --- Article -----------------------------------------------------------------


@dataclass(frozen=True)
class TeamNote:
    team_id: TeamId
    prose: str
    attributed_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArticleContent:
    headline: str
    intro: str
    team_notes: tuple[TeamNote, ...]
    outro: str


@dataclass(frozen=True)
class ValidationFailure:
    check: str
    message: str


@dataclass(frozen=True)
class ValidationOutcome:
    passed: bool
    checked_at: datetime
    failures: tuple[ValidationFailure, ...] = ()


@dataclass(frozen=True)
class Article:
    week: int
    model: str
    generated_at: datetime
    content: ArticleContent | None
    validation: ValidationOutcome

    @property
    def is_publishable(self) -> bool:
        return self.content is not None and self.validation.passed


# --- Published page ----------------------------------------------------------


@dataclass(frozen=True)
class PublishedPage:
    season: str
    week: int
    entry_id: str
    algorithm_version: str
    has_article: bool
    path: str
    html: str
