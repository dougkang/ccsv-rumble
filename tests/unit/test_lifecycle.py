"""The gate that decides whether a ranking is publishable at all (FR-002).

This is the most consequential module to get right in the feature, because
PRE_DRAFT publishes nothing, exits ZERO, and sends no notification. A gate that
wrongly reports pre-draft produces no page every week while reporting success,
with no alarm anywhere -- so these tests exist to prove the classification is
load-bearing, not merely that it runs.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ccsv_rumble import config
from ccsv_rumble.lifecycle import classify
from ccsv_rumble.models import LifecycleState

from ..conftest import make_post_draft_snapshot


def test_no_rosters_is_pre_draft() -> None:
    snap = replace(make_post_draft_snapshot(), rosters={})
    verdict = classify(snap)
    assert verdict.state is LifecycleState.PRE_DRAFT
    assert "has not drafted" in verdict.reason


def test_short_rosters_are_pre_draft_with_a_debuggable_reason() -> None:
    """FR-008: the reason is the only signal a silent outcome has."""
    verdict = classify(make_post_draft_snapshot(short_teams=2))
    assert verdict.state is LifecycleState.PRE_DRAFT
    # "pre-draft" alone is undebuggable three weeks later; the count must be named.
    assert "2 of 18" in verdict.reason
    assert str(config.DRAFT_ROSTER_SIZE) in verdict.reason


def test_a_drafted_league_classifies_as_post_draft(post_draft_snapshot) -> None:
    """The whole feature hangs off this returning POST_DRAFT.

    Rosters hold 10 players and IL is empty, which is what a real completed
    draft looks like.
    """
    verdict = classify(post_draft_snapshot)
    assert verdict.state is LifecycleState.POST_DRAFT, verdict.reason
    assert "no scored week" in verdict.reason


def test_the_roster_size_constant_is_load_bearing(
    post_draft_snapshot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard for the silent-failure path (quickstart 1a).

    A drafted league holds 10 of 12 roster spots, because the two IL slots start
    empty. Had the completeness check used MAX_ROSTER_SIZE, every team would read
    incomplete forever and every run would classify PRE_DRAFT -- publishing
    nothing, exiting zero, notifying no one, indefinitely.

    This asserts the fixture is genuinely discriminating: at 10 it is POST_DRAFT,
    at 12 it collapses to PRE_DRAFT. A test that passed at both values would
    prove nothing at all.
    """
    assert classify(post_draft_snapshot).state is LifecycleState.POST_DRAFT

    monkeypatch.setattr(config, "DRAFT_ROSTER_SIZE", config.MAX_ROSTER_SIZE)
    assert classify(post_draft_snapshot).state is LifecycleState.PRE_DRAFT, (
        "the fixture is not discriminating: it classifies the same way at 10 and "
        "12, so it cannot catch the IL miscount"
    )


def test_one_scored_week_is_in_season(post_draft_snapshot) -> None:
    verdict = classify(replace(post_draft_snapshot, completed_scored_weeks=1))
    assert verdict.state is LifecycleState.IN_SEASON
    assert "1 scored week" in verdict.reason


def test_a_mid_season_roster_dip_is_not_pre_draft() -> None:
    """Order of checks is itself load-bearing.

    A roster legitimately falls below the draft size between a drop and an add.
    Testing draft completeness before season progress would classify a healthy
    December league as undrafted and silently stop publishing.
    """
    snap = make_post_draft_snapshot(short_teams=3, completed_scored_weeks=5)
    assert classify(snap).state is LifecycleState.IN_SEASON


def test_a_team_with_no_roster_entry_is_pre_draft() -> None:
    snap = make_post_draft_snapshot()
    rosters = dict(snap.rosters)
    del rosters[snap.teams[0].team_id]
    verdict = classify(replace(snap, rosters=rosters))
    assert verdict.state is LifecycleState.PRE_DRAFT
    assert "no roster" in verdict.reason


def test_classification_is_pure() -> None:
    """No clock, no filesystem -- same snapshot, same verdict, always."""
    snap = make_post_draft_snapshot()
    first = classify(snap)
    second = classify(snap)
    assert first == second
