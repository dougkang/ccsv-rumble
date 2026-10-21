"""Raw Yahoo payloads -> typed `Snapshot`. Pure; no network.

Yahoo's JSON is deeply nested and mixes dicts keyed by stringified integers with
lists, so extraction walks the tree defensively rather than indexing fixed paths.
A fixed-path parser breaks on any shape change; a walker degrades to "team not
found", which the Snapshot validator then reports loudly.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..models import CategoryLine, Matchup, Snapshot, Team
from .provider import ProviderError
from .yahoo import parse_team_stats


def _walk_nodes(payload: Any, marker: str) -> list[dict[str, Any]]:
    """Collect every dict containing `marker` as a key, depth-first."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if marker in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def _flatten_team_node(node: Any) -> dict[str, Any]:
    """Yahoo team nodes are lists of single-key dicts mixed with dicts. Merge."""
    merged: dict[str, Any] = {}

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, value in item.items():
                if key not in merged or not isinstance(value, (dict, list)):
                    merged.setdefault(key, value)
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(node)
    return merged


def _manager_name(team_blob: dict[str, Any]) -> str:
    for manager_node in _walk_nodes(team_blob, "nickname"):
        nickname = str(manager_node.get("nickname", "")).strip()
        if nickname and nickname != "--":
            return nickname
    return ""


def _team_containers(payload: Any) -> list[Any]:
    """Yahoo wraps each team as {"team": <node>}, where <node> is a list mixing
    identity dicts and a team_stats dict.

    Walking for "team_key" instead would find only the innermost single-key dict,
    which carries the id but neither the name nor the stats -- the bug this
    function exists to avoid.
    """
    return [node["team"] for node in _walk_nodes(payload, "team")]


def extract_teams(scoreboard: dict[str, Any], stat_map: dict[str, str]) -> tuple[
    list[Team], dict[str, CategoryLine]
]:
    teams: list[Team] = []
    totals: dict[str, CategoryLine] = {}
    seen: set[str] = set()

    for raw_team in _team_containers(scoreboard):
        flat = _flatten_team_node(raw_team)
        team_id = str(flat.get("team_key", "")).strip()
        if not team_id or team_id in seen:
            continue
        seen.add(team_id)
        teams.append(
            Team(
                team_id=team_id,
                name=str(flat.get("name", "")).strip() or team_id,
                manager_display_name=_manager_name(raw_team),
            )
        )
        stats = parse_team_stats(raw_team, stat_map)
        totals[team_id] = CategoryLine(
            pts=stats.get("pts", 0),
            reb=stats.get("reb", 0),
            ast=stats.get("ast", 0),
            stl=stats.get("stl", 0),
            blk=stats.get("blk", 0),
            tpm=stats.get("tpm", 0),
            to=stats.get("to", 0),
            fgm=stats.get("fgm", 0),
            fga=stats.get("fga", 0),
            ftm=stats.get("ftm", 0),
            fta=stats.get("fta", 0),
            games_played=stats.get("games_played", 0),
        )

    teams.sort(key=lambda t: t.team_id)
    return teams, totals


def extract_matchups(scoreboard: dict[str, Any], week: int) -> list[Matchup]:
    matchups: list[Matchup] = []
    for node in _walk_nodes(scoreboard, "matchup"):
        blob = node.get("matchup")
        team_ids = [
            str(_flatten_team_node(t).get("team_key", "")).strip()
            for t in _walk_nodes(blob, "team_key")
        ]
        unique = sorted({tid for tid in team_ids if tid})
        if len(unique) == 2:
            matchups.append(
                Matchup(week=week, home_team_id=unique[0], away_team_id=unique[1])
            )
    # Deduplicate; the walker can see the same matchup at several depths.
    unique_matchups = {(m.home_team_id, m.away_team_id): m for m in matchups}
    return [unique_matchups[k] for k in sorted(unique_matchups)]


def _week_bounds(scoreboard: dict[str, Any], fallback: date) -> tuple[date, date]:
    starts = _walk_nodes(scoreboard, "week_start")
    ends = _walk_nodes(scoreboard, "week_end")
    try:
        start = date.fromisoformat(str(starts[0]["week_start"]))
        end = date.fromisoformat(str(ends[0]["week_end"]))
        return start, end
    except (IndexError, KeyError, ValueError):
        return fallback, fallback


def build_snapshot(
    *,
    entry_id: str,
    acquired_at: datetime,
    season: str,
    week: int,
    scoreboard: dict[str, Any],
    stat_map: dict[str, str],
    supersedes: str | None = None,
    raw_source: str = "raw-yahoo.json",
) -> Snapshot:
    teams, totals = extract_teams(scoreboard, stat_map)
    if not teams:
        raise ProviderError(
            f"no teams found in the week {week} scoreboard payload; "
            "the response shape may have changed"
        )
    start, end = _week_bounds(scoreboard, acquired_at.date())
    return Snapshot(
        entry_id=entry_id,
        acquired_at=acquired_at,
        season=season,
        week=week,
        week_start=start,
        week_end=end,
        teams=tuple(teams),
        category_totals=totals,
        matchups=tuple(extract_matchups(scoreboard, week)),
        stat_category_map=dict(stat_map),
        supersedes=supersedes,
        raw_source=raw_source,
    )
