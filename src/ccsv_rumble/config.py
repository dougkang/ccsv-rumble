"""Every declared constant for the generator, in one module.

Constitution Principle I requires the ranking constants to live in a single declared
place rather than scattered as literals, because changing any of them bumps the
algorithm version and triggers a before/after comparison on archived data.

Nothing in this module may be computed at import time from the environment or the
clock -- these are declarations, not configuration lookups. Runtime configuration
(credentials, repository names) is read in `cli.py` and passed down explicitly.
"""

from __future__ import annotations

from typing import Final

# --- Algorithm identity -------------------------------------------------------
# Bumping this REQUIRES a before/after rank comparison on archived data in the PR.
ALGORITHM_VERSION: Final[str] = "v1"

# --- League shape -------------------------------------------------------------
TEAM_COUNT: Final[int] = 18
CATEGORY_COUNT: Final[int] = 9

#: Canonical category keys. Order is fixed and load-bearing: it determines
#: iteration order everywhere, which is part of what makes rendering deterministic.
CATEGORIES: Final[tuple[str, ...]] = (
    "pts",
    "reb",
    "ast",
    "stl",
    "blk",
    "tpm",
    "fg_pct",
    "ft_pct",
    "to",
)

#: Categories where a LOWER value wins.
INVERTED_CATEGORIES: Final[frozenset[str]] = frozenset({"to"})

#: Categories compared as made/attempted rather than as a stored number.
RATIO_CATEGORIES: Final[frozenset[str]] = frozenset({"fg_pct", "ft_pct"})

#: made/attempted field pairs backing each ratio category.
RATIO_FIELDS: Final[dict[str, tuple[str, str]]] = {
    "fg_pct": ("fgm", "fga"),
    "ft_pct": ("ftm", "fta"),
}

#: Minimum categories needed to win a head-to-head matchup (>= 5 of 9).
MATCHUP_WIN_THRESHOLD: Final[float] = 5.0

# --- Power score composition --------------------------------------------------
#: Expected Matchup Win% weight. EMW is the objective; CAW is the variance reducer.
EMW_WEIGHT: Final[float] = 0.65
#: Category All-Play Win% weight.
CAW_WEIGHT: Final[float] = 0.35
#: Shrinkage constant: w = n / (n + SHRINKAGE_K). Realized play overtakes the
#: roster prior partway through week 3.
SHRINKAGE_K: Final[int] = 3
#: Recency half-life in weeks: week w of n is weighted 0.5 ** ((n - w) / H).
RECENCY_HALF_LIFE_WEEKS: Final[int] = 4

# --- Movement significance ----------------------------------------------------
#: A rank change of strictly fewer than this many places is "within normal
#: variation". In an 18-team league with recency weighting most small moves are
#: noise, and attributing a cause to every team is how the article reads as filler.
SIGNIFICANT_RANK_CHANGE: Final[int] = 3

# --- Standout performance -----------------------------------------------------
#: A player's week is a standout when any category exceeds their own season
#: baseline by this multiple.
STANDOUT_BASELINE_MULTIPLE: Final[float] = 1.5
#: Games below this floor are excluded, to keep small samples out.
STANDOUT_MIN_GAMES: Final[int] = 2

# --- Schedule luck banding ----------------------------------------------------
#: Lower bounds for (actual_win_pct - emw), descending. Published only as a label.
LUCK_BAND_THRESHOLDS: Final[tuple[tuple[float, str], ...]] = (
    (0.20, "VERY_LUCKY"),
    (0.08, "LUCKY"),
    (-0.08, "NEUTRAL"),
    (-0.20, "UNLUCKY"),
)
LUCK_BAND_FLOOR: Final[str] = "VERY_UNLUCKY"

# --- Acquisition --------------------------------------------------------------
#: How many completed weeks to re-fetch each run looking for upstream corrections.
#: Fantasy stat corrections land within days; three weeks is generous and costs
#: three extra requests regardless of season length.
RECHECK_WEEKS: Final[int] = 3
HTTP_TIMEOUT_SECONDS: Final[float] = 20.0
HTTP_MAX_RETRIES: Final[int] = 3
#: Seconds between sequential requests, so a long-outage backfill does not become
#: a burst that gets rate-limited.
HTTP_PACING_SECONDS: Final[float] = 0.5
USER_AGENT: Final[str] = "ccsv-rumble/0.1 (league power rankings; contact via repo)"

# --- Timekeeping --------------------------------------------------------------
#: The run's weekly boundary must align with the league's matchup week, and all
#: displayed dates use this zone -- never the host's local time.
LEAGUE_TIMEZONE: Final[str] = "America/Los_Angeles"

# --- Publishing ---------------------------------------------------------------
PUBLISH_BRANCH_DEFAULT: Final[str] = "pages"
#: Per page, not per site.
PAGE_WEIGHT_BUDGET_BYTES: Final[int] = 500_000

# --- Article generation -------------------------------------------------------
ARTICLE_MODEL: Final[str] = "claude-opus-5"
ARTICLE_MAX_TOKENS: Final[int] = 16_000
ARTICLE_FALLBACK_BETA: Final[str] = "server-side-fallback-2026-07-01"

#: Substrings that would disclose the ranking method if they reached the page.
#: Matched case-insensitively against generated prose.
DISCLOSURE_TERMS: Final[tuple[str, ...]] = (
    "emw",
    "caw",
    "all-play",
    "allplay",
    "power score",
    "powerscore",
    "roster prior",
    "recency",
    "half-life",
    "shrinkage",
    "z-score",
    "zscore",
    "weighting",
    "weighted average",
    "algorithm",
    "formula",
    "coefficient",
    "regression",
)

#: Language that would breach the tone requirement for a church league.
DISALLOWED_TONE_TERMS: Final[tuple[str, ...]] = (
    "pathetic",
    "embarrassing",
    "humiliating",
    "clueless",
    "idiot",
    "stupid",
    "garbage",
    "worthless",
    "disgrace",
    # FR-046 draws the line at a person's competence or character rather than at
    # humour itself: teasing a pick is the point of a draft recap. These are
    # terms that cannot land on a roster decision -- only on the human who made
    # it. Chosen for that property, which is also why obvious candidates like
    # "hopeless" are absent: "their centre rotation is hopeless" is about the
    # roster, and rejecting the whole article over it would cost the page an
    # article to no one's benefit.
    "incompetent",
    "moron",
    "laughingstock",
    "braindead",
    "brain-dead",
    "amateur hour",
)

# --- Draft ranking (week 0) ---------------------------------------------------
# Declared version for the draft algorithm, INDEPENDENT of ALGORITHM_VERSION.
# Both are recorded per run: PowerScore depends on both for the whole season, so
# a rank cannot be traced by citing one of them (draft algorithm doc s8).
DRAFT_ALGORITHM_VERSION: Final[str] = "draft-v1"

#: Shrink toward even odds: DraftScore = 0.5 + s * (AllPlay_proj - 0.5).
#: All-play over POINT projections is overconfident -- a team projected to edge
#: five categories by a hair wins every simulated matchup and scores 1.000, a
#: claim no honest forecast can make. A judgment call, not a fitted value; first
#: refit target after one season of archived weeks.
DRAFT_SHRINK: Final[float] = 0.6

#: The league's active lineup: 2G, 3FC, 1 Util. SIX slots, so one missing
#: projection is 17% of a team's week rather than 10%.
#: Order is load-bearing -- narrowest eligibility first, so a dual-eligible
#: player lands where he is needed and UTIL mops up. Filling UTIL first could
#: consume the best guard and leave a G slot unfillable.
ACTIVE_SLOTS: Final[tuple[str, ...]] = ("G", "G", "FC", "FC", "FC", "UTIL")

#: Which eligibility tokens satisfy each slot. UTIL accepts anyone.
#:
#: Yahoo renders eligibility in terms of THIS league's slot classes, not the
#: usual nine-slot vocabulary: the roster page shows "PHX - G", "MIA - FC",
#: "ORL - G,FC". So the collapsed tokens `G` and `FC` are the common case and
#: must be accepted directly.
#:
#: Missing `FC` was a live bug: every player read as UTIL-only, three of six
#: active slots were unfillable, coverage sat at 0.5 against a 0.80 floor, and
#: the run would have refused to publish for every team, forever. The granular
#: tokens are kept so a league that reports them still works.
SLOT_ELIGIBILITY: Final[dict[str, frozenset[str]]] = {
    "G": frozenset({"G", "PG", "SG", "GF", "G/F"}),
    "FC": frozenset({"FC", "F", "C", "SF", "PF", "F/C", "GF", "G/F"}),
}

BENCH_SLOTS: Final[int] = 4
IL_SLOTS: Final[int] = 2

#: Players a completed draft puts on each roster: active + bench. EXCLUDES IL,
#: which starts empty and fills only on injury.
#:
#: Using MAX_ROSTER_SIZE here would mark every team incomplete forever, classify
#: every run pre-draft, and -- because pre-draft publishes nothing, exits ZERO
#: and does not notify -- produce no page indefinitely with no alarm anywhere.
DRAFT_ROSTER_SIZE: Final[int] = 10

#: Active lineup size, derived rather than restated so the two cannot diverge.
ACTIVE_SLOT_COUNT: Final[int] = len(ACTIVE_SLOTS)

#: Active + bench + IL. The ceiling, not what a draft fills.
MAX_ROSTER_SIZE: Final[int] = 12

#: Minimum share of a team's ACTIVE SLOTS fillable by a projected player.
#: 0.80 of six slots permits exactly one unfillable slot.
#: This is NOT the unprojected-player count: an unprojected player has no value
#: so slot filling never selects him, and a team with six projected starters and
#: four unprojected bench players has full coverage.
DRAFT_MIN_TEAM_COVERAGE: Final[float] = 0.80

#: Minimum share across all 108 active slots. Catches a systemic source failure
#: spread thinly enough to clear every per-team check: eighteen teams each
#: missing one slot passes per-team at 0.833 and is refused here.
DRAFT_MIN_LEAGUE_COVERAGE: Final[float] = 0.95

#: Machine identifiers for ranking-derived figures, screened against the whole
#: rendered page -- markup comments, data attributes, alt text and tooltips
#: included (FR-029).
#:
#: Deliberately identifiers rather than words. DISCLOSURE_TERMS is matched
#: against generated PROSE, where "caw" and "emw" are safe to look for. Matching
#: those as substrings across an entire page would reject a surname like
#: "Cawthorne" -- which in an 18-team church league is somebody's actual name,
#: and rejecting the page over it would be a self-inflicted outage.
DRAFT_INTERNAL_IDENTIFIERS: Final[tuple[str, ...]] = (
    "draft_score",
    "draftscore",
    "emw_proj",
    "caw_proj",
    "power_score",
    "powerscore",
    "roster_prior",
    "category_profile",
    "performance_weight",
    "schedule_luck",
)
