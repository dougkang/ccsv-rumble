"""The publishable report: the ONLY input to article generation and rendering.

This is where strict disclosure is enforced. The internal report carries
power scores, EMW, CAW, roster priors, weights, per-category rates, and a numeric
schedule-luck figure. None of them can cross into `PublishableTeam`, because that
class has no field to hold them (FR-032).

What does cross: rank, movement, the real win-loss record (a league fact, not a
ranking output), a qualitative luck BAND, and qualitative category phrases.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import (
    InternalReport,
    PublishableEvent,
    PublishableReport,
    PublishableTeam,
    Snapshot,
)
from ..rank.score import category_notes, record_string


def _notes_for(entry) -> tuple[str, ...]:
    """Category notes, plus the projection-coverage caveat when there is one.

    The unprojected count is published as PROSE, never as a table figure
    (FR-025). It survives FR-028 because it does not originate from the ranking
    computation at all -- it is an input-coverage fact, knowable before any
    scoring happens, and the design document calls hiding it "the kind of quiet
    degradation Principle II exists to prevent".

    Distinct from active-slot coverage, which gates publication: a team can have
    four unprojected bench players and still field a complete projected lineup.
    """
    notes = list(category_notes(entry.category_profile))
    count = entry.unprojected_count
    if count:
        # Deliberately NO numeral. These notes feed the article prompt, and
        # `permitted_numbers` does not include unprojected counts -- so a digit
        # here would be a foreign numeral the moment the article repeated it,
        # rejecting an otherwise fine piece. The reader gets the count from the
        # page-level `coverage_note`, which no numeral screen applies to.
        plural = "players" if count > 1 else "a player"
        notes.append(
            f"had {plural} with no projection, so this placement rests on a "
            "thinner picture than the others"
        )
    return tuple(notes)


def build(
    *,
    internal: InternalReport,
    history: Sequence[Snapshot],
    is_projection: bool,
    is_current_week: bool = True,
    is_provisional: bool = False,
) -> PublishableReport:
    current = history[-1]
    names = {team.team_id: team for team in current.teams}

    teams: list[PublishableTeam] = []
    for entry in internal.ranking.entries:
        team = names.get(entry.team_id)
        teams.append(
            PublishableTeam(
                team_id=entry.team_id,
                team_name=team.name if team else entry.team_id,
                manager_display_name=team.manager_display_name if team else "",
                rank=entry.rank,
                previous_rank=entry.previous_rank,
                rank_change=entry.rank_change,
                movement=entry.movement,
                record=record_string(history, entry.team_id),
                luck_band=entry.luck_band,
                category_notes=_notes_for(entry),
            )
        )

    events = tuple(
        PublishableEvent(
            event_id=event.event_id,
            type=event.type,
            team_ids=event.team_ids,
            summary=event.summary,
            occurred_on=event.occurred_on,
            player_name=event.player_name,
        )
        for event in internal.events
    )

    return PublishableReport(
        season=internal.season,
        week=internal.week,
        is_projection=is_projection,
        teams=tuple(teams),
        events=events,
        is_current_week=is_current_week,
        is_provisional=is_provisional,
        coverage_note=_coverage_note(internal),
    )


def _coverage_note(internal: InternalReport) -> str:
    """Page-level prose when projection coverage was incomplete (FR-025).

    Names how many TEAMS were affected rather than which players, and carries no
    figure from the computation. Silent when coverage was complete, so the common
    case adds nothing to the page.
    """
    affected = sum(1 for e in internal.ranking.entries if e.unprojected_count)
    if not affected:
        return ""
    if affected == 1:
        return (
            "One team had a player with no projection, so its placement rests on "
            "a slightly thinner picture than the rest."
        )
    return (
        f"{affected} teams had at least one player with no projection, so those "
        "placements rest on a slightly thinner picture than the rest."
    )


def permitted_numbers(report: PublishableReport) -> set[str]:
    """Every number the article is allowed to use, as strings.

    `record` is decomposed into its components: prose will naturally read
    "at 6-4 they..." and a naive numerals scan would flag both halves as
    foreign. This false positive is guaranteed, not hypothetical.
    """
    allowed: set[str] = set()
    for team in report.teams:
        allowed.add(str(team.rank))
        if team.previous_rank is not None:
            allowed.add(str(team.previous_rank))
        if team.rank_change is not None:
            allowed.add(str(abs(team.rank_change)))
        for part in team.record.split("-"):
            if part.strip().isdigit():
                allowed.add(part.strip())
    allowed.add(str(report.week))
    for event in report.events:
        for token in event.summary.replace("-", " ").split():
            cleaned = token.strip(".,;:()%").replace(".", "")
            if cleaned.isdigit():
                allowed.add(cleaned)
        allowed.add(str(event.occurred_on.day))
        allowed.add(str(event.occurred_on.year))
    return allowed
