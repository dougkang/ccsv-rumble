"""Test doubles for the integration suite. Nothing here touches the network."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.conftest import make_snapshot


class FakeProvider:
    """Serves prebuilt snapshots as if they were raw Yahoo payloads."""

    def __init__(self) -> None:
        self.fetched: list[int] = []
        self.fail_weeks: set[int] = set()

    def fetch_stat_category_map(self, season: str) -> dict[str, str]:
        return {"12": "pts"}

    def fetch_week(self, season: str, week: int) -> dict[str, Any]:
        from ccsv_rumble.fetch.provider import ProviderError

        self.fetched.append(week)
        if week in self.fail_weeks:
            raise ProviderError(f"simulated upstream failure for week {week}")
        return {"week": week}

    def fetch_rosters(self, season: str, week: int) -> dict[str, Any]:
        return {}

    def fetch_transactions(self, season: str, week: int) -> dict[str, Any]:
        return {}


@pytest.fixture
def fake_snapshot_builder(monkeypatch):
    """Make `build_snapshot` return a deterministic fixture per week.

    `seed_shift[week] = n` simulates an upstream correction: the same week comes
    back with different numbers on a later fetch.
    """
    state: dict[str, dict[int, int]] = {"seed_shift": {}}

    def _build(*, entry_id, acquired_at, season, week, scoreboard, stat_map,
               supersedes=None, raw_source="raw-yahoo.json"):
        return make_snapshot(
            week,
            entry_id=entry_id,
            season=season,
            seed_offset=state["seed_shift"].get(week, 0),
            supersedes=supersedes,
        )

    monkeypatch.setattr("ccsv_rumble.pipeline.build_snapshot", _build)
    return state


# --- Article client double ----------------------------------------------------


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _Response:
    stop_reason: str
    content: list
    model: str = "claude-opus-5"
    stop_details: Any = None


class FakeAnthropic:
    """Stands in for the SDK client.

    Recovers the teams and week from the real prompt rather than being handed
    them, so the prompt-building path is exercised too.
    """

    def __init__(
        self,
        behavior: str = "ok",
        fail_weeks: set[int] | None = None,
    ) -> None:
        self.behavior = behavior
        self.fail_weeks = fail_weeks or set()
        self.calls: list[int] = []
        self.beta = self  # client.beta.messages.create(...)
        self.messages = self

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _parse_prompt(kwargs) -> tuple[int, list[dict]]:
        message = kwargs["messages"][0]["content"]
        # The prompt says "CURRENT week (5)" or "covers week 5"; match both.
        week_match = re.search(r"week \(?(\d+)\)?", message, re.IGNORECASE)
        week = int(week_match.group(1)) if week_match else 0
        teams_blob = message.split("TEAMS:\n", 1)[1].split("\n\nEVENTS:", 1)[0]
        return week, json.loads(teams_blob)

    # -- the SDK surface the code under test uses ------------------------------

    def create(self, **kwargs):
        from ccsv_rumble.fetch.provider import ProviderError

        week, teams = self._parse_prompt(kwargs)
        self.calls.append(week)

        behavior = self.behavior
        if week in self.fail_weeks:
            behavior = "raise"

        if behavior == "raise":
            raise ProviderError("simulated model outage")
        if behavior == "refusal":
            return _Response(stop_reason="refusal", content=[])
        if behavior == "max_tokens":
            return _Response(stop_reason="max_tokens", content=[])

        if behavior == "fabricate":
            payload = {
                "headline": f"Week {week} in review",
                "intro": "Big news.",
                "outro": "See you next week.",
                "team_notes": [
                    {
                        "team_id": teams[0]["team_id"],
                        "prose": "A blockbuster trade reshaped the roster.",
                        "attributed_event_ids": ["evt-99-trade-doesnotexist"],
                    }
                ]
                + [
                    {"team_id": t["team_id"], "prose": "Quiet week.",
                     "attributed_event_ids": []}
                    for t in teams[1:]
                ],
            }
        else:
            payload = {
                "headline": f"Week {week} in review",
                "intro": "A busy week around the league.",
                "outro": "Back next week.",
                "team_notes": [
                    {"team_id": t["team_id"], "prose": "Steady as they go.",
                     "attributed_event_ids": []}
                    for t in teams
                ],
            }

        return _Response(
            stop_reason="end_turn", content=[_TextBlock(json.dumps(payload))]
        )


@dataclass
class RecordingNotifier:
    """Captures notifications instead of sending them."""

    sent: list = field(default_factory=list)
    should_fail: bool = False

    def send(self, notification) -> None:
        from ccsv_rumble.notify import NotifyError

        if self.should_fail:
            raise NotifyError("simulated notification outage")
        self.sent.append(notification)
