"""Which of three states a run is operating in. PURE -- no I/O, no clock.

This is the switch that decides whether a ranking is computable and publishable
at all (FR-002), and it is the most dangerous module in the feature, because
PRE_DRAFT is the one outcome that publishes nothing, exits ZERO, and sends no
notification. A gate that wrongly says "pre-draft" produces no page, every week,
reporting success, with no alarm anywhere.

Two decisions exist specifically to prevent that:

1. **Completed scored weeks are checked FIRST.** A roster legitimately dips below
   the draft size mid-season, between a drop and an add. Testing draft
   completeness before season progress would classify a healthy December league
   as undrafted. Draft completeness is only consulted when no week has been
   scored yet.

2. **The threshold is `DRAFT_ROSTER_SIZE` (active + bench), not `MAX_ROSTER_SIZE`.**
   The league's two IL slots start empty and fill only on injury, so a fully
   drafted team holds 10 of 12 possible players. Using the maximum would mark
   every team incomplete forever -- see `config.DRAFT_ROSTER_SIZE`.

`completed_scored_weeks` is supplied by acquisition rather than inferred here.
Deriving it from the calendar would be wrong: a week in progress looks finished
to a clock, and that is exactly the window this feature targets.
"""

from __future__ import annotations

from . import config
from .models import LifecycleState, LifecycleVerdict, PlayerSlot, Snapshot, TeamId


def classify_rosters(
    rosters: dict[TeamId, tuple[PlayerSlot, ...]],
    team_count: int = config.TEAM_COUNT,
) -> LifecycleVerdict | None:
    """Pre-draft check from rosters ALONE, before a snapshot exists.

    Week 0 is acquired from rosters rather than a scoreboard, and a `Snapshot`
    cannot be built at all without all 18 teams -- so the pre-draft decision has
    to be made from the roster input first.

    Returns a PRE_DRAFT verdict, or None when the league looks drafted and
    acquisition should proceed.

    Absent rosters are PRE_DRAFT, not a failure. FR-002 defines the state as
    "rosters do not exist or are incomplete", and before draft night there is
    genuinely nothing to capture -- so failing here would report a normal state
    as broken, which FR-004 forbids.
    """
    if not rosters:
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT, "no rosters available; league has not drafted"
        )
    if len(rosters) < team_count:
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT,
            f"rosters for only {len(rosters)} of {team_count} teams; "
            "draft incomplete or capture unfinished",
        )
    short = sorted(
        (team_id, len(slots))
        for team_id, slots in rosters.items()
        if len(slots) < config.DRAFT_ROSTER_SIZE
    )
    if short:
        detail = ", ".join(f"{tid}={n}" for tid, n in short[:3])
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT,
            f"{len(short)} of {team_count} rosters below "
            f"{config.DRAFT_ROSTER_SIZE} ({detail}"
            f"{', …' if len(short) > 3 else ''}); draft incomplete",
        )
    return None


def classify(
    snapshot: Snapshot, *, completed_scored_weeks: int | None = None
) -> LifecycleVerdict:
    """Classify the run's lifecycle state, with the reason FR-008 requires.

    `completed_scored_weeks` is passed explicitly by the caller when it knows
    better than the snapshot does -- the archive knows how many weeks have been
    scored, and a single snapshot does not. Relying on the snapshot field alone
    was a bug: it defaults to 0, so a mid-season week with real results but no
    roster data classified as PRE_DRAFT and silently stopped publishing.

    A snapshot for week >= 1 is in-season by definition. Games have been played,
    so whatever the roster data looks like, the draft is not pending.
    """
    scored = (
        snapshot.completed_scored_weeks
        if completed_scored_weeks is None
        else completed_scored_weeks
    )
    if scored > 0:
        return LifecycleVerdict(
            LifecycleState.IN_SEASON, f"{scored} scored week(s) completed"
        )
    if snapshot.week > 0:
        return LifecycleVerdict(
            LifecycleState.IN_SEASON,
            f"week {snapshot.week} is under way, so the draft is not pending",
        )

    rosters = snapshot.rosters
    if not rosters:
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT, "no rosters acquired; league has not drafted"
        )

    missing = [t.team_id for t in snapshot.teams if t.team_id not in rosters]
    if missing:
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT,
            f"{len(missing)} of {len(snapshot.teams)} teams have no roster "
            f"(first: {sorted(missing)[0]})",
        )

    short = sorted(
        (team.team_id, len(rosters[team.team_id]))
        for team in snapshot.teams
        if len(rosters[team.team_id]) < config.DRAFT_ROSTER_SIZE
    )
    if short:
        detail = ", ".join(f"{tid}={n}" for tid, n in short[:3])
        return LifecycleVerdict(
            LifecycleState.PRE_DRAFT,
            f"{len(short)} of {len(snapshot.teams)} rosters below "
            f"{config.DRAFT_ROSTER_SIZE} ({detail}"
            f"{', …' if len(short) > 3 else ''}); draft incomplete",
        )

    return LifecycleVerdict(
        LifecycleState.POST_DRAFT,
        f"all {len(snapshot.teams)} rosters at {config.DRAFT_ROSTER_SIZE}+ "
        "with no scored week completed",
    )
