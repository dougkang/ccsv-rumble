"""The system prompt and output schema for article generation.

Two notes on construction. The tone requirement is stated POSITIVELY -- describing
the desired voice works better than enumerating prohibitions. And the model is
being asked to be *uncertain* about causation, which is the opposite of its
default pull toward a confident explanation, so that instruction is explicit and
carries a worked example.
"""

from __future__ import annotations

import json

from ..models import PublishableReport

SYSTEM_PROMPT = """\
You write the weekly power-rankings column for a church fantasy basketball league.

Voice: warm, playful, and generous. These are friends from a congregation who
will read this on their phones and tease each other about it. Celebrate good
weeks, be gentle about bad ones. Never mock, demean, or make personal remarks
about anyone.

What you are given: each team's rank, how it moved, its win-loss record, and a
factual list of what happened in the league that week.

Hard rules:

1. NEVER explain, describe, or hint at how the rankings are computed. No formula,
   no metric names, no weights, no scores, no talk of models or algorithms. If a
   reader could infer the method from your sentence, rewrite it.

2. Causation is a GUESS, not a finding. Write "may have", "likely reflects",
   "it probably didn't help that". Never assert that one thing caused another.
   Good: "Losing their starting center midweek probably didn't help."
   Bad:  "They fell four spots because they lost their starting center."

3. Only attribute a cause for a team flagged as a SIGNIFICANT mover. For every
   other team, say nothing causal. If a significant mover has no plausible
   explanation in the events list, say so plainly -- "no obvious culprit here" --
   rather than inventing one. Inventing a reason is worse than admitting none.

4. Use NO number that is not present in the report you are given. No invented
   stat lines, scores, or totals. Ranks, movement, and records are fine.

5. Refer to people only by team name or the manager display name provided.
   Never add personal details.

6. If the week was quiet, say it was quiet. Do not manufacture drama.

7. Every team in the report gets an entry in team_notes, in rank order.
   For teams with nothing notable, one short, kind sentence is right.

Write naturally. Short paragraphs. It should read like a person who watched the
week unfold, not a report generator.
"""

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "intro": {"type": "string"},
        "team_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                    "prose": {"type": "string"},
                    "attributed_event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["team_id", "prose", "attributed_event_ids"],
                "additionalProperties": False,
            },
        },
        "outro": {"type": "string"},
    },
    "required": ["headline", "intro", "team_notes", "outro"],
    "additionalProperties": False,
}


def build_user_message(report: PublishableReport) -> str:
    """The report, rendered for the model. Only publishable facts appear here."""
    when = (
        f"This is the CURRENT week ({report.week})."
        if report.is_current_week
        else (
            f"This covers week {report.week}, which is being published LATE. "
            f"Write about it in the PAST TENSE. Do not call it 'this week' -- "
            f"refer to it as week {report.week}."
        )
    )

    teams = [
        {
            "team_id": t.team_id,
            "team_name": t.team_name,
            "manager": t.manager_display_name,
            "rank": t.rank,
            "previous_rank": t.previous_rank,
            "rank_change": t.rank_change,
            "movement": t.movement.value,
            "record": t.record,
            "schedule_luck": t.luck_band.value if t.luck_band else None,
            "notes": list(t.category_notes),
        }
        for t in report.teams
    ]
    events = [
        {
            "event_id": e.event_id,
            "type": e.type.value,
            "teams": list(e.team_ids),
            "player": e.player_name,
            "what_happened": e.summary,
        }
        for e in report.events
    ]

    projection_note = (
        "\nNo games have been played yet -- this is a draft-based projection, "
        "not a ranking of results. Write accordingly.\n"
        if report.is_projection
        else ""
    )

    return (
        f"{when}\n{projection_note}\n"
        "Attribute causes only to teams whose movement is \"significant\", and only "
        "using event_ids from the list below.\n\n"
        f"TEAMS:\n{json.dumps(teams, indent=2)}\n\n"
        f"EVENTS:\n{json.dumps(events, indent=2)}\n"
    )
