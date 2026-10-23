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


class LifecycleState(StrEnum):
    """Which of three states a run is operating in (FR-002).

    The switch that decides whether a ranking is computable and publishable at
    all. PRE_DRAFT is the only outcome in the whole project that publishes
    nothing, exits ZERO, and sends no notification -- an undrafted league is a
    normal state, not a fault.
    """

    PRE_DRAFT = "pre_draft"
    POST_DRAFT = "post_draft"
    IN_SEASON = "in_season"


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
    #: Raw eligibility as the provider reports it, e.g. ("PG", "SG"). Collapsed
    #: to this league's three slot classes by `config.SLOT_ELIGIBILITY`.
    #: Defaulted empty so existing fixtures keep working -- but an empty tuple is
    #: eligible for UTIL only, so a roster with no position data fills one slot
    #: and trips the coverage floor loudly rather than mis-ranking quietly.
    positions: tuple[str, ...] = ()


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
    #: How many scored weeks have FINISHED, supplied by acquisition.
    #: The pure layer must not infer this, and deriving it from the calendar
    #: would be wrong: a week in progress looks finished to a clock.
    completed_scored_weeks: int = 0

    def __post_init__(self) -> None:
        # "len(teams) == 18; every team present in category_totals" (data-model.md s1)
        if len(self.teams) != config.TEAM_COUNT:
            raise ValidationError(
                f"expected {config.TEAM_COUNT} teams, got {len(self.teams)}"
            )
        missing = [t.team_id for t in self.teams if t.team_id not in self.category_totals]
        if missing:
            raise ValidationError(f"teams missing category totals: {sorted(missing)}")


# --- Draft ranking inputs (week 0) -------------------------------------------


@dataclass(frozen=True)
class PerGameLine:
    """A player's per-game expectation. FLOAT fields, unlike CategoryLine.

    CategoryLine cannot be reused here, and the reason is not stylistic: its
    fields are `int`, because an observed week is a whole number of made shots.
    A projection is not -- 8.6 FGM and 18.8 FGA per game are normal values, and
    storing them as ints truncates to 8 and 18 at the SOURCE, before any
    accumulation. That is a 7% error on makes, it biases every ratio category
    downward, and no amount of careful rounding later recovers it.
    """

    pts: float = 0.0
    reb: float = 0.0
    ast: float = 0.0
    stl: float = 0.0
    blk: float = 0.0
    tpm: float = 0.0
    to: float = 0.0
    fgm: float = 0.0
    fga: float = 0.0
    ftm: float = 0.0
    fta: float = 0.0

    def __post_init__(self) -> None:
        # Mirrors CategoryLine's invariants, which cannot be inherited because
        # the field types differ. A source supplying only a percentage is
        # rejected at ingest rather than reaching this type at all (FR-010).
        if self.fgm > self.fga:
            raise ValidationError(f"fgm {self.fgm} exceeds fga {self.fga}")
        if self.ftm > self.fta:
            raise ValidationError(f"ftm {self.ftm} exceeds fta {self.fta}")
        for name in ("pts", "reb", "ast", "stl", "blk", "tpm", "to",
                     "fgm", "fga", "ftm", "fta"):
            if getattr(self, name) < 0:
                raise ValidationError(f"{name} is negative: {getattr(self, name)}")


@dataclass(frozen=True)
class PlayerProjection:
    """One player's expected per-game production, plus games in the target week.

    Ratio categories arrive as makes and attempts, never a percentage: .458 is
    consistent with 11/24 and 22/48, which aggregate differently, so a
    percentage-only source is rejected at ingest (FR-010).
    """

    player_id: str
    name: str
    per_game: PerGameLine
    projected_games: int

    def __post_init__(self) -> None:
        # Only this field needs checking here -- PerGameLine already enforces
        # the makes/attempts and non-negativity invariants at its own boundary.
        if self.projected_games < 0:
            raise ValidationError(
                f"{self.player_id}: projected_games must be >= 0, got {self.projected_games}"
            )


@dataclass(frozen=True)
class ProjectionSnapshot:
    """The archived input that makes a past draft ranking reproducible.

    Without this, editing the projections file silently changes the result of
    replaying a past week (FR-011, FR-012). A later revision by the source never
    alters an already-published ranking -- it becomes a new entry (FR-013).
    """

    source_id: str
    retrieved_at: datetime
    target_week: int
    projections: tuple[PlayerProjection, ...]
    raw_source: str = ""

    def by_player(self) -> dict[str, PlayerProjection]:
        """player_id -> projection. Matching is by id; name is diagnostics only."""
        return {p.player_id: p for p in self.projections}


@dataclass(frozen=True)
class DraftPick:
    pick_number: int
    team_id: TeamId
    player_id: str
    player_name: str
    #: Eligibility as the provider lists it, and the NBA club. Both are league
    #: data the recap may name (FR-047), and both are optional so an archive
    #: written before they existed still decodes.
    positions: tuple[str, ...] = ()
    nba_team: str = ""


@dataclass(frozen=True)
class DraftResults:
    """Pick-by-pick record. Needed ONLY by the recap, never by the ranking.

    That split is load-bearing: the week-0 page ships without draft results, and
    results failing never costs the ranking (FR-049).
    """

    season: str
    picks: tuple[DraftPick, ...] = ()
    #: True only when every pick of a FINISHED draft is present. A partial record
    #: is treated as unavailable, because a recap built from half a draft board
    #: would confidently describe a draft that did not happen.
    is_complete: bool = False


@dataclass(frozen=True)
class LifecycleVerdict:
    """The lifecycle state plus WHY (FR-008).

    A bare enum cannot distinguish "no rosters at all" from "two teams drafted
    short", and those read very differently in a log three weeks later. Because
    PRE_DRAFT is deliberately silent, the reason is the only signal available.
    """

    state: LifecycleState
    reason: str


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
    #: Draft ranking decomposition (FR-034). Internal, like everything above.
    #: DraftScore post-shrink, and the projected all-play components behind it.
    draft_score: float | None = None
    emw_proj: float | None = None
    caw_proj: float | None = None
    #: Rostered players with no projection (FR-025). The ONE value here that may
    #: also reach the page -- as prose, never a figure -- because it is an
    #: input-coverage fact rather than a ranking output, so FR-028 does not reach
    #: it. Distinct from active-slot coverage, which gates publication.
    unprojected_count: int = 0

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
    #: The draft algorithm's declared version, recorded ALONGSIDE the in-season
    #: one (FR-033). PowerScore depends on both for the whole season, so a rank
    #: cannot be traced by citing one of them. Empty when no draft term applies.
    draft_algorithm_version: str = ""

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
    #: Week 1 with no projections: real results exist but only one week of them.
    is_provisional: bool = False
    #: Prose caveat when some rostered players had no projection (FR-025).
    #:
    #: A STRING, not a count, and that is the point: it is prose the reader can
    #: weigh, not a figure that could be mistaken for a ranking output. It is
    #: publishable at all because it describes input coverage rather than
    #: anything the computation produced, so FR-028 does not reach it.
    #:
    #: Needed on the report because `category_notes` reaches only the article
    #: prompt -- on a rankings-only page it would never be seen, and the design
    #: document calls hiding this "the kind of quiet degradation Principle II
    #: exists to prevent".
    coverage_note: str = ""


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
