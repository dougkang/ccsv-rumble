"""The system prompt and output schema for article generation.

Two notes on construction. The tone requirement is stated POSITIVELY -- describing
the desired voice works better than enumerating prohibitions. And the model is
being asked to be *uncertain* about causation, which is the opposite of its
default pull toward a confident explanation, so that instruction is explicit and
carries a worked example.
"""

from __future__ import annotations

import json

from .. import config
from ..models import DraftResults, PublishableReport

SYSTEM_PROMPT = """\
You write the weekly power-rankings column for a church fantasy basketball league.

Voice: punchy, playful, and generous. Punny with daad jokes. These are friends
from a congregation who will read this on their phones and tease each other
about it. Celebrate good weeks, be gentle about bad ones. Never mock, demean,
or make personal remarks about anyone.

What you are given: each team's rank, how it moved, its category win-loss-tie record, and a
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
   other team, say nothing causal. Don't rely too much on IL moves for your reasoning.
   If a significant mover has no plausible explanation in the events list, say so
   plainly -- "no obvious culprit here" -- rather than inventing one. Inventing a
   reason is worse than admitting none.

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

DRAFT_SYSTEM_PROMPT = """\
You write the draft recap for a church fantasy basketball league. It runs with
the preseason rankings, before anyone has played a game.

Voice: punchy, playful, and generous. Punny with dad jokes.  Use team name as
inspiration. These are friends from a congregation who will read this on their
phones the day after the draft and tease each other about it. This is the
most-read piece of the season -- have fun with it.

What you are given: the full draft board, pick by pick, and each team's
preseason rank.

Hard rules:

1. Tease the PICKS, never the PERSON. "Taking a third centre in the fifth round
   is a choice" is fine. Anything about a manager being bad at this, careless,
   or clueless is not. The target of every joke must be a roster decision, not
   a human being.

2. NEVER explain, describe, or hint at how the rankings are computed. No
   formula, no metric names, no weights, no scores, no talk of models or
   algorithms. You may say a team is ranked first. You may not say why in terms
   of any calculation. If a reader could infer the method from your sentence,
   rewrite it.

3. Nobody has played a game. Write about the draft and about EXPECTATIONS --
   "on paper", "if the shooting holds up", "they will need". Never describe
   results, performances, or what a player has done this season.

4. Use NO number that is not in the draft board or rankings you are given. Pick
   numbers, round numbers, and ranks are fine. Stat lines are NOT: you have not
   been given any, so any points-per-game or shooting figure you write would be
   invented.

5. Write pick positions in words, not in round.pick notation. Say "the first
   pick of round three" or "the thirty-ninth pick", never "3.1".

6. Leave attributed_event_ids empty for every team. Nothing has happened yet, so
   there is nothing to attribute.

7. Every team gets an entry in team_notes, in rank order. Start with a catchy
   sentence that sums up the draft theme.  Say something real about each team's
   draft -- who they built around, what they loaded up on, what they look thin at.
   One or two sentences each.

8. End with a draft grade between A and F.

The intro is about the draft as a whole: how the first round went, any run on a
position, anyone who went surprisingly early or late. The outro looks ahead to
the first week.

Write naturally. Short paragraphs. It should read like a person who sat through
the draft, not a report generator.
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


def _round_of(pick_number: int) -> int:
    return (pick_number - 1) // config.TEAM_COUNT + 1


def build_draft_user_message(report: PublishableReport, draft: DraftResults) -> str:
    """The draft board and the preseason ranks, rendered for the model.

    Only publishable facts appear here. Teams are identified by `team_id`
    throughout -- including inside the board -- so the model has no display-name
    key to echo back into `TeamNote.team_id`, where it would fail the
    validator's coverage check.

    The board is given once, in pick order, with each team's picks also grouped
    under that team. Repeating it is worth the tokens: the chronological view is
    what makes a run on a position visible, and the grouped view is what makes a
    per-team note possible without the model having to scan 180 rows per team.
    """
    ranks = [
        {
            "team_id": t.team_id,
            "team_name": t.team_name,
            "manager": t.manager_display_name,
            "preseason_rank": t.rank,
        }
        for t in report.teams
    ]

    board = [
        {
            "overall": p.pick_number,
            "round": _round_of(p.pick_number),
            "team_id": p.team_id,
            "player": p.player_name,
            "nba_team": p.nba_team,
            "positions": list(p.positions),
        }
        for p in draft.picks
    ]

    by_team: dict[str, list[str]] = {}
    for pick in draft.picks:
        by_team.setdefault(pick.team_id, []).append(
            f"{pick.pick_number}. {pick.player_name}"
            f"{f' ({pick.nba_team})' if pick.nba_team else ''}"
            f"{f' [{'/'.join(pick.positions)}]' if pick.positions else ''}"
        )
    rosters = [
        {"team_id": t.team_id, "picks": by_team.get(t.team_id, [])} for t in report.teams
    ]

    return (
        f"This is the draft recap for the {draft.season} season. "
        f"{len(draft.picks)} picks over {_round_of(len(draft.picks))} rounds, "
        f"{len(ranks)} teams. No games have been played.\n\n"
        "Leave attributed_event_ids empty for every team -- nothing has happened "
        "yet.\n\n"
        f"PRESEASON RANKS:\n{json.dumps(ranks, indent=2, ensure_ascii=False)}\n\n"
        f"DRAFT BOARD, in pick order:\n"
        f"{json.dumps(board, indent=2, ensure_ascii=False)}\n\n"
        f"THE SAME PICKS, grouped by team:\n"
        f"{json.dumps(rosters, indent=2, ensure_ascii=False)}\n"
    )
