"""FR-032 / SC-010: no ranking-derived number may be published.

The point of these tests is that the guarantee is structural. `PublishableTeam`
has no field to hold a power score, so the only way to regress is to add one --
which this test then catches.
"""

from __future__ import annotations

import dataclasses
import re

from ccsv_rumble.models import PublishableTeam
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_page
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_snapshot

#: Anything resembling a component metric. Adding one of these to
#: PublishableTeam is exactly the regression FR-032 forbids.
FORBIDDEN_FIELDS = {
    "power_score",
    "emw",
    "caw",
    "roster_prior",
    "performance_weight",
    "category_profile",
    "schedule_luck",
    "score",
    "rating",
}

PERMITTED_FIELDS = {
    "team_id",
    "team_name",
    "manager_display_name",
    "rank",
    "previous_rank",
    "rank_change",
    "movement",
    "record",
    "luck_band",
    "category_notes",
}


def test_publishable_team_has_no_metric_fields() -> None:
    names = {f.name for f in dataclasses.fields(PublishableTeam)}
    assert not (names & FORBIDDEN_FIELDS), (
        f"PublishableTeam grew metric field(s): {sorted(names & FORBIDDEN_FIELDS)}. "
        "FR-032 is enforced by this class having nowhere to put them."
    )


def test_publishable_team_field_set_is_closed() -> None:
    """A new field is not necessarily wrong, but it must be a deliberate choice."""
    names = {f.name for f in dataclasses.fields(PublishableTeam)}
    assert names == PERMITTED_FIELDS, (
        f"PublishableTeam fields changed: added {sorted(names - PERMITTED_FIELDS)}, "
        f"removed {sorted(PERMITTED_FIELDS - names)}. Confirm the addition cannot "
        "carry a ranking-derived number, then update this test."
    )


def test_rendered_page_contains_no_decimal_figures() -> None:
    """A power score would surface as a decimal. Ranks and records never are."""
    snapshot = make_snapshot(1)
    ranking = build_ranking([snapshot])
    report = internal_report.build(
        season="2026-27", week=1, entry_id="entry-001",
        ranking=ranking, events=derive_events(snapshot),
    )
    public = publishable_report.build(
        internal=report, history=[snapshot], is_projection=False
    )
    html = render_page(
        report=public, entry_id="entry-001", generated_at="2026-10-27"
    ).html

    body = html.split("</head>", 1)[1]
    decimals = re.findall(r"\b\d*\.\d+\b", body)
    assert not decimals, f"page shows decimal figures: {decimals}"


def test_internal_report_does_keep_the_metrics() -> None:
    """The counterpart: detail is retained internally for debugging and replay."""
    snapshot = make_snapshot(1)
    ranking = build_ranking([snapshot])
    entry = ranking.entries[0]
    assert entry.power_score > 0
    assert entry.emw >= 0
    assert entry.caw >= 0
    assert entry.category_profile
