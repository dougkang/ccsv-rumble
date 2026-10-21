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


def build(
    *,
    internal: InternalReport,
    history: Sequence[Snapshot],
    is_projection: bool,
    is_current_week: bool = True,
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
                category_notes=category_notes(entry.category_profile),
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
