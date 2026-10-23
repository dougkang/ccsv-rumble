"""Article content validation. PURE -- no network, no model.

Structured output is what makes this tractable. Because the model returns
`attributed_event_ids` as a first-class field, the two highest-risk requirements
become set operations rather than prose parsing:

    FR-022 traceability   attributed_event_ids is a subset of the report's events
    FR-019 noise          non-significant movers carry no attributions

Both are deterministic and immune to phrasing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .. import config
from ..models import (
    ArticleContent,
    DraftResults,
    Movement,
    PublishableReport,
    ValidationFailure,
    ValidationOutcome,
)
from ..report.publishable import permitted_numbers

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
_URL_RE = re.compile(r"https?://|www\.")


def _all_prose(content: ArticleContent) -> str:
    return " ".join(
        [content.headline, content.intro, content.outro]
        + [note.prose for note in content.team_notes]
    )


def validate_article(
    content: ArticleContent,
    report: PublishableReport,
    *,
    extra_numbers: set[str] | None = None,
) -> ValidationOutcome:
    """Screen generated prose against every publishable-content requirement.

    `extra_numbers` widens the numerals allowlist with figures that are facts of
    a companion input rather than of the report -- the draft board's pick and
    round numbers. It never widens the disclosure or tone screens, which apply
    identically to every article the project publishes.
    """
    failures: list[ValidationFailure] = []
    prose = _all_prose(content)
    lowered = prose.lower()

    known_events = {event.event_id for event in report.events}
    teams_by_id = {team.team_id: team for team in report.teams}

    # FR-022 -- every attributed event exists in the report.
    for note in content.team_notes:
        unknown = sorted(set(note.attributed_event_ids) - known_events)
        if unknown:
            failures.append(
                ValidationFailure(
                    check="event_traceability",
                    message=f"team {note.team_id} cites unknown events: {unknown}",
                )
            )

    # FR-019 -- no causal attribution for teams that did not meaningfully move.
    for note in content.team_notes:
        team = teams_by_id.get(note.team_id)
        if team and team.movement is not Movement.SIGNIFICANT and note.attributed_event_ids:
            failures.append(
                ValidationFailure(
                    check="noise_attribution",
                    message=(
                        f"team {note.team_id} is {team.movement.value} but was given "
                        f"{len(note.attributed_event_ids)} causal attribution(s)"
                    ),
                )
            )

    # Coverage -- every team present exactly once, none invented.
    seen = [note.team_id for note in content.team_notes]
    duplicates = sorted({t for t in seen if seen.count(t) > 1})
    unknown_teams = sorted(set(seen) - set(teams_by_id))
    missing_teams = sorted(set(teams_by_id) - set(seen))
    if duplicates:
        failures.append(
            ValidationFailure("team_coverage", f"duplicate team notes: {duplicates}")
        )
    if unknown_teams:
        failures.append(
            ValidationFailure("team_coverage", f"notes for unknown teams: {unknown_teams}")
        )
    if missing_teams:
        failures.append(
            ValidationFailure("team_coverage", f"teams with no note: {missing_teams}")
        )

    # FR-021 -- no disclosure of the ranking method.
    disclosed = sorted({term for term in config.DISCLOSURE_TERMS if term in lowered})
    if disclosed:
        failures.append(
            ValidationFailure("no_disclosure", f"prose discloses method terms: {disclosed}")
        )

    # FR-022 / FR-034 -- no number absent from the report.
    allowed = permitted_numbers(report) | (extra_numbers or set())
    foreign = sorted(
        {
            match
            for match in _NUMBER_RE.findall(prose)
            if match not in allowed and match.lstrip("0") not in allowed
        }
    )
    if foreign:
        failures.append(
            ValidationFailure(
                "no_foreign_numbers",
                f"prose uses numbers absent from the report: {foreign}",
            )
        )

    # FR-024 -- no personal information.
    if _EMAIL_RE.search(prose) or _PHONE_RE.search(prose) or _URL_RE.search(prose):
        failures.append(
            ValidationFailure("no_pii", "prose contains an email, phone number, or URL")
        )

    # FR-023 -- tone.
    harsh = sorted({term for term in config.DISALLOWED_TONE_TERMS if term in lowered})
    if harsh:
        failures.append(ValidationFailure("tone", f"prose uses demeaning language: {harsh}"))

    # Structure.
    if not content.headline.strip():
        failures.append(ValidationFailure("non_empty", "headline is empty"))
    if not content.intro.strip():
        failures.append(ValidationFailure("non_empty", "intro is empty"))
    if not content.outro.strip():
        failures.append(ValidationFailure("non_empty", "outro is empty"))

    return ValidationOutcome(
        passed=not failures,
        checked_at=datetime.now(UTC),
        failures=tuple(failures),
    )


def draft_permitted_numbers(draft: DraftResults) -> set[str]:
    """Numerals the recap may use that the report does not contain.

    Pick numbers, the rounds they fall in, and the totals. Because a complete
    board is a contiguous 1..N, this does admit every integer up to the number
    of picks -- which is honest: each one IS a pick the model was shown.

    What it deliberately does not admit is anything fractional. An invented stat
    line ("28.4 points") is the failure mode that matters here, and it stays
    caught. Round.pick notation ("3.1") is also still caught, which is why the
    prompt asks for pick positions in words.
    """
    allowed = {str(pick.pick_number) for pick in draft.picks}
    allowed |= {
        str((pick.pick_number - 1) // config.TEAM_COUNT + 1) for pick in draft.picks
    }
    allowed.add(str(len(draft.picks)))
    allowed.add(str(config.TEAM_COUNT))
    return allowed


def validate_draft_recap(
    content: ArticleContent, report: PublishableReport, draft: DraftResults
) -> ValidationOutcome:
    """FR-045/FR-046/FR-047 screens for the week-0 recap.

    Intentionally the same function as the weekly column, differing only in the
    numerals allowlist. The disclosure screen, the tone screen, the team
    coverage check, and the PII check are shared rather than reimplemented --
    a second copy would be a second thing to forget to update.
    """
    return validate_article(
        content, report, extra_numbers=draft_permitted_numbers(draft)
    )
