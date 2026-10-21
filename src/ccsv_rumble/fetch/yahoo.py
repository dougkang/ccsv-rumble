"""Yahoo Fantasy Sports API v2 provider.

Two traps specific to Yahoo, both load-bearing:

1. Shooting stats are COMPOSITE STRINGS. stat_id 9004003 carries "FGM/FGA" and
   9007006 carries "FTM/FTA" as a single "made/attempted" value. A parser that
   assumes numeric stat values fails on exactly the two categories whose
   information cannot be reconstructed later.

2. stat_id values are NOT hardcoded. They come from community sources, are not
   authoritative, and change between seasons or re-created leagues. The mapping is
   read from league settings every run and all nine categories must resolve or the
   run fails loudly.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .. import config
from .provider import ProviderError

API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

#: Yahoo stat names (from league settings) mapped to our canonical keys.
#: Matched case-insensitively against the `display_name`/`name` in settings.
_NAME_TO_CATEGORY: dict[str, str] = {
    "pts": "pts",
    "points": "pts",
    "reb": "reb",
    "rebounds": "reb",
    "ast": "ast",
    "assists": "ast",
    "st": "stl",
    "stl": "stl",
    "steals": "stl",
    "blk": "blk",
    "blocks": "blk",
    "3ptm": "tpm",
    "3pm": "tpm",
    "to": "to",
    "turnovers": "to",
    "fgm/fga": "fg_pct",
    "fg%": "fg_pct",
    "ftm/fta": "ft_pct",
    "ft%": "ft_pct",
}


# --- Pure parsing helpers (unit-testable without network) ---------------------


def split_made_attempted(value: Any) -> tuple[int, int]:
    """Split Yahoo's composite "made/attempted" shooting value.

    Handles the empty and "-" cases explicitly -- a team with no attempts that
    week -- rather than letting them raise. Returns (0, 0) for those.
    """
    if value is None:
        return (0, 0)
    text = str(value).strip()
    if text in {"", "-", "-/-", "0/0"}:
        return (0, 0)
    if "/" not in text:
        raise ProviderError(
            f"expected a composite 'made/attempted' value, got {text!r}; "
            "Yahoo returns FG and FT as a single string, not a number"
        )
    made_text, _, att_text = text.partition("/")
    try:
        made = int(float(made_text.strip() or 0))
        attempted = int(float(att_text.strip() or 0))
    except ValueError as exc:
        raise ProviderError(f"unparseable shooting value {text!r}") from exc
    if made > attempted:
        raise ProviderError(f"made {made} exceeds attempted {attempted} in {text!r}")
    return (made, attempted)


def parse_stat_category_map(settings_payload: dict[str, Any]) -> dict[str, str]:
    """Build stat_id -> canonical category from a league settings payload.

    Fails loudly unless all nine expected categories resolve.
    """
    mapping: dict[str, str] = {}
    for stat in _iter_stats(settings_payload):
        stat_id = str(stat.get("stat_id", "")).strip()
        if not stat_id:
            continue
        for key in ("display_name", "abbr", "name"):
            raw = str(stat.get(key, "")).strip().lower()
            if raw in _NAME_TO_CATEGORY:
                mapping[stat_id] = _NAME_TO_CATEGORY[raw]
                break

    resolved = set(mapping.values())
    missing = sorted(set(config.CATEGORIES) - resolved)
    if missing:
        raise ProviderError(
            f"league settings did not resolve these categories: {missing}. "
            "stat_id values are league-specific and must not be hardcoded -- "
            "check the league's scoring settings."
        )
    return mapping


def _iter_stats(payload: Any) -> list[dict[str, Any]]:
    """Walk Yahoo's deeply nested settings payload collecting `stat` objects."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "stat_id" in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def parse_team_stats(
    team_node: dict[str, Any], stat_map: dict[str, str]
) -> dict[str, Any]:
    """Extract one team's category totals from a scoreboard team node.

    Returns a dict of canonical-category -> value, with ratio categories
    expanded into their made/attempted components.
    """
    out: dict[str, Any] = {}
    for stat in _iter_stats(team_node):
        stat_id = str(stat.get("stat_id", "")).strip()
        category = stat_map.get(stat_id)
        if category is None or "value" not in stat:
            continue
        raw = stat["value"]
        if category in config.RATIO_CATEGORIES:
            made_field, att_field = config.RATIO_FIELDS[category]
            made, attempted = split_made_attempted(raw)
            out[made_field] = made
            out[att_field] = attempted
        else:
            try:
                out[category] = int(float(str(raw).strip() or 0))
            except ValueError:
                out[category] = 0
    return out


# --- Provider -----------------------------------------------------------------


class YahooProvider:
    """Live Yahoo client. Network access is confined to this class."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        league_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._league_key = league_key
        self._access_token: str | None = None
        self._http = client or httpx.Client(
            timeout=config.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": config.USER_AGENT},
        )

    # -- auth ------------------------------------------------------------------

    def _ensure_token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        if response.status_code != 200:
            raise ProviderError(
                f"Yahoo token refresh failed with {response.status_code}. "
                "The refresh token may have been revoked; re-run the consent flow."
            )
        token = response.json().get("access_token")
        if not token:
            raise ProviderError("Yahoo token response contained no access_token")
        self._access_token = token
        return token

    # -- transport -------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        """GET with an explicit timeout and a BOUNDED retry count.

        Exhausted retries are a Principle II failure: report and publish nothing.
        Never retry indefinitely.
        """
        token = self._ensure_token()
        url = f"{API_BASE}/{path}"
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}format=json"

        last_error: str = ""
        for attempt in range(config.HTTP_MAX_RETRIES):
            if attempt:
                time.sleep(config.HTTP_PACING_SECONDS * (2**attempt))
            try:
                response = self._http.get(url, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                continue
            if response.status_code == 200:
                time.sleep(config.HTTP_PACING_SECONDS)
                return response.json()
            if response.status_code in (401, 403):
                # Token may have expired mid-run; refresh once then retry.
                self._access_token = None
                token = self._ensure_token()
                last_error = f"auth error {response.status_code}"
                continue
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"status {response.status_code}"
                continue
            raise ProviderError(f"Yahoo returned {response.status_code} for {path}")

        raise ProviderError(
            f"Yahoo request to {path} failed after {config.HTTP_MAX_RETRIES} "
            f"attempts ({last_error})"
        )

    # -- provider protocol ------------------------------------------------------

    def fetch_stat_category_map(self, season: str) -> dict[str, str]:
        return parse_stat_category_map(self._get(f"league/{self._league_key}/settings"))

    def fetch_week(self, season: str, week: int) -> dict[str, Any]:
        # One request yields team_stats for every matchup -- the full grid.
        return self._get(f"league/{self._league_key}/scoreboard;week={week}")

    def fetch_rosters(self, season: str, week: int) -> dict[str, Any]:
        return self._get(f"league/{self._league_key}/teams/roster;week={week}")

    def fetch_transactions(self, season: str, week: int) -> dict[str, Any]:
        return self._get(f"league/{self._league_key}/transactions")
