"""A payload that fails to parse must leave evidence behind.

Archiving happens after parsing, so a parse failure would otherwise discard the
exact payload needed to diagnose it. The payload most likely to break the parser
is the FIRST real one from Yahoo -- which by definition cannot be reproduced
from a fixture, because the fixture was written from documentation rather than
from a real response.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccsv_rumble.archive.store import ArchiveStore
from ccsv_rumble.fetch.provider import ProviderError
from ccsv_rumble.pipeline import execute
from ccsv_rumble.schedule import RunPlan
from tests.integration.conftest import FakeProvider

SEASON = "2026-27"


@pytest.fixture
def exploding_parser(monkeypatch):
    def _build(**kwargs):
        raise ProviderError("no teams found in the week 1 scoreboard payload")

    monkeypatch.setattr("ccsv_rumble.pipeline.build_snapshot", _build)


def test_unparseable_payload_is_quarantined(
    tmp_path: Path, exploding_parser
) -> None:
    store = ArchiveStore(tmp_path / "archive")

    with pytest.raises(ProviderError):
        execute(
            RunPlan(SEASON, (1,), (), 1),
            provider=FakeProvider(),
            store=store,
            anthropic_client=None,
            generated_at="2026-10-27",
            projections_path=tmp_path / "missing.csv",
        )

    quarantined = sorted((tmp_path / "archive" / "_quarantine" / SEASON).glob("*.json"))
    assert quarantined, "the raw payload was discarded; nothing left to debug with"
    assert json.loads(quarantined[0].read_text()) == {"week": 1}


def test_quarantine_does_not_create_a_half_built_entry(
    tmp_path: Path, exploding_parser
) -> None:
    """The archive invariant: every entry-NNN is complete.

    An entry holding only raw-yahoo.json would still be returned by
    latest_entry, and every later read would fail on the missing snapshot.
    """
    store = ArchiveStore(tmp_path / "archive")

    with pytest.raises(ProviderError):
        execute(
            RunPlan(SEASON, (1,), (), 1),
            provider=FakeProvider(),
            store=store,
            anthropic_client=None,
            generated_at="2026-10-27",
            projections_path=tmp_path / "missing.csv",
        )

    assert store.list_entry_ids(SEASON, 1) == []
    assert not store.has_week(SEASON, 1)


def test_quarantined_payloads_are_still_scrubbed(tmp_path: Path, monkeypatch) -> None:
    """Quarantine is not an exemption from Principle V."""

    def _build(**kwargs):
        raise ProviderError("boom")

    monkeypatch.setattr("ccsv_rumble.pipeline.build_snapshot", _build)

    class LeakyProvider(FakeProvider):
        def fetch_week(self, season: str, week: int) -> dict:
            return {"access_token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}

    store = ArchiveStore(tmp_path / "archive")
    with pytest.raises(ProviderError):
        execute(
            RunPlan(SEASON, (1,), (), 1),
            provider=LeakyProvider(),
            store=store,
            anthropic_client=None,
            generated_at="2026-10-27",
            projections_path=tmp_path / "missing.csv",
        )

    for path in (tmp_path / "archive" / "_quarantine").rglob("*.json"):
        assert "ghp_" not in path.read_text(encoding="utf-8")
