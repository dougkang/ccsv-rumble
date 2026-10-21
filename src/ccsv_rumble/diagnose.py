"""Setup diagnostics: find the right league key, and explain Yahoo's 403s.

Yahoo's league keys are `{game_key}.l.{league_id}`, where `game_key` is a
SEASON-SPECIFIC NUMBER (e.g. `466`), not the sport code. `nba.l.194131` looks
plausible and is accepted by some endpoints, but league resources return
403 Forbidden for it -- which reads like a permissions problem and is actually
a malformed key.

This asks Yahoo which leagues the authenticated user actually has, so the key
comes from the source of truth rather than from guessing.
"""

from __future__ import annotations

from typing import Any

from .fetch.yahoo import YahooProvider


def _walk(payload: Any, marker: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if marker in node:
                found.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return found


def list_leagues(provider: YahooProvider) -> list[dict[str, str]]:
    """Every NBA league the authenticated user belongs to, newest season first."""
    payload = provider._get(  # noqa: SLF001 -- diagnostic reaches into the client
        "users;use_login=1/games;game_codes=nba/leagues"
    )

    leagues: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in _walk(payload, "league_key"):
        key = str(node.get("league_key", "")).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        leagues.append(
            {
                "league_key": key,
                "name": str(node.get("name", "")).strip(),
                "season": str(node.get("season", "")).strip(),
                "teams": str(node.get("num_teams", "")).strip(),
                "scoring": str(node.get("scoring_type", "")).strip(),
            }
        )
    leagues.sort(key=lambda row: row["season"], reverse=True)
    return leagues


def explain_403(league_key: str, leagues: list[dict[str, str]]) -> list[str]:
    """Why a league request might be refused, most likely cause first."""
    notes: list[str] = []
    game_key = league_key.split(".", 1)[0] if "." in league_key else ""

    if game_key and not game_key.isdigit():
        notes.append(
            f"`{league_key}` uses the sport code `{game_key}` as the game key. "
            "League resources need the season-specific NUMERIC game key "
            "(e.g. `466.l.194131`). This alone causes a 403."
        )
    if leagues and league_key not in {row["league_key"] for row in leagues}:
        notes.append(
            "The configured key is not among the leagues this account can see. "
            "Either the key is wrong or the refresh token belongs to a different "
            "Yahoo account than the one in the league."
        )
    if not leagues:
        notes.append(
            "Yahoo returned no NBA leagues for this account at all. Check that "
            "the consent flow was completed with the Yahoo account that is IN "
            "the league, and that the app requests Fantasy Sports read access."
        )
    return notes
