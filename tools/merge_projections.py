#!/usr/bin/env python3
"""Join any projections export onto your roster's Yahoo player ids.

This is the piece every projection source needs, whatever the source is.
Projection providers key on player NAMES; `data/rosters.csv` keys on Yahoo ids
like `nba.p.5473`. Nothing downstream can match them up, and a silent mismatch
is the worst outcome available: an unmatched player reads as "no projection",
the coverage floor rejects his team, and the run refuses to publish for a reason
that looks like missing data rather than a failed join.

So this reports every unmatched player on both sides, loudly, and refuses to
write a file that would fail the coverage floor unless told otherwise.

    uv run python tools/merge_projections.py \\
        --rosters data/rosters.csv \\
        --projections ~/Downloads/bbm-weekly.csv \\
        --out data/projections.csv

Column names are detected rather than hardcoded, because every provider spells
them differently ("FGM", "fgm", "FG Made", "FGM/A"). Use --map to override when
detection guesses wrong:

    --map fgm=FGMade --map fga=FGAtt
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

#: Target schema, in the order `fetch/projections.py` expects.
TARGET = (
    "player_id", "name", "positions", "projected_games",
    "pts", "reb", "ast", "stl", "blk", "tpm", "to",
    "fgm", "fga", "ftm", "fta",
)

#: Header spellings seen in the wild, per target column. First match wins.
ALIASES: dict[str, tuple[str, ...]] = {
    # Per-game spellings ("p/g", "r/g") are Basketball Monster's; the bare forms
    # are everyone else's.
    "name": ("name", "player", "playername", "player name"),
    "projected_games": ("games", "gp", "g", "projectedgames", "gamesplayed"),
    "pts": ("pts", "points", "p", "p/g", "pg"),
    "reb": ("reb", "rebounds", "trb", "r", "r/g", "rg"),
    "ast": ("ast", "assists", "a", "a/g", "ag"),
    "stl": ("stl", "steals", "st", "s", "s/g", "sg"),
    "blk": ("blk", "blocks", "bk", "b", "b/g", "bg"),
    "tpm": ("tpm", "3pm", "3ptm", "threes", "3s", "fg3m", "3/g", "3g"),
    # "to/g" FIRST: Basketball Monster also ships "toV", a z-score, and
    # matching that instead would feed standardized values into a counting
    # category -- wrong in a way that still produces a plausible-looking table.
    "to": ("to/g", "tog", "to", "turnovers", "tov"),
    "fgm": ("fgm", "fgmade", "fgm/g", "fg made"),
    "fga": ("fga", "fgatt", "fgattempted", "fg att", "fga/g", "fgag"),
    "ftm": ("ftm", "ftmade", "ft made"),
    "fta": ("fta", "ftatt", "ftattempted", "ft att", "fta/g", "ftag"),
    # Only usable WITH attempts -- see `derive_makes`.
    "fg_pct": ("fg%", "fgpct", "fgp"),
    "ft_pct": ("ft%", "ftpct", "ftp"),
}

#: Target columns that are not part of the output schema.
_DERIVED_ONLY = ("fg_pct", "ft_pct")

#: Clubs that two sources spell differently. ESPN's schedule uses the left
#: form; Yahoo's roster pages use the right. 24 of 30 already agree, and these
#: six would otherwise silently get zero games -- which reads as "did not play"
#: and quietly drops six teams' worth of players out of every lineup.
CLUB_ALIASES: dict[str, str] = {
    "GS": "GSW", "NO": "NOP", "NY": "NYK",
    "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
    # and the reverse, so either direction resolves
    "GSW": "GSW", "NOP": "NOP", "NYK": "NYK", "SAS": "SAS", "UTA": "UTA", "WAS": "WAS",
}


#: Z-score / "value" columns, which sit beside the real ones and look just like
#: them to a header match. Basketball Monster ships pV, 3V, rV, aV, sV, bV, toV,
#: fg%V and ft%V next to p/g, 3/g, r/g and the rest.
_VALUE_COLUMN = re.compile(r"^(?:p|3|r|a|s|b|to|fg%|ft%)v$", re.I)

#: Suffixes that differ between sources for the same human being.
_SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize(name: str) -> str:
    """A name key robust to the ways two sources spell the same player.

    Accents (Doncic/Dončić), punctuation (C.J./CJ), and generational suffixes
    (Jaren Jackson Jr.) are all real differences between real exports.
    """
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = _SUFFIXES.sub(" ", text)
    return " ".join(text.split())


def initial_key(name: str) -> str:
    """`j smith` from `jabari smith` -- a second pass for abbreviated firsts.

    Yahoo abbreviates some names ("N. Alexander-Walker") where a projection
    source writes them out.
    """
    parts = normalize(name).split()
    if len(parts) < 2:
        return ""
    return f"{parts[0][0]} {' '.join(parts[1:])}"


def value(row: dict, cols: dict[str, str], col: str, default: float = 0.0) -> float:
    """One numeric cell, defaulting rather than raising on a blank or a dash.

    Module level rather than a closure over the loop variable: a nested
    function capturing `hit` is fine while it is called immediately, and wrong
    the moment anyone defers it.
    """
    raw = str(row.get(cols.get(col, ""), "")).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def derive_makes(row: dict, cols: dict[str, str], kind: str) -> float | None:
    """Makes from a percentage AND attempts. `kind` is "fg" or "ft".

    This is NOT the inference FR-010 forbids, and the direction is what makes
    the difference.

    FR-010 refuses to invent ATTEMPTS from a percentage, because `.458` is
    consistent with 11/24 and with 22/48 and those aggregate into a team week
    differently -- the information is genuinely gone. Here attempts are GIVEN
    and only makes are computed, which is exact arithmetic on two supplied
    numbers rather than a guess at a missing one.

    Verified against Basketball Monster's export: `fg% x fga/g` returned whole
    numbers for every row, because their percentage is the exact ratio rather
    than a rounded display value.
    """
    pct_col, att_col = f"{kind}_pct", f"{kind}a"
    if pct_col not in cols or att_col not in cols:
        return None
    return value(row, cols, pct_col) * value(row, cols, att_col)


def detect(headers: list[str], overrides: dict[str, str]) -> dict[str, str]:
    """Map each target column to a header in the source file."""
    lowered = {
        h.strip().lower().replace("_", "").replace(" ", ""): h
        for h in headers
        if not _VALUE_COLUMN.match(h.strip())
    }

    found: dict[str, str] = {}
    for target, names in ALIASES.items():
        if target in overrides:
            found[target] = overrides[target]
            continue
        for alias in names:
            key = alias.replace("_", "").replace(" ", "")
            if key in lowered:
                found[target] = lowered[key]
                break
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rosters", type=Path, default=Path("data/rosters.csv"))
    ap.add_argument("--projections", type=Path, required=True,
                    help="whatever your source exported")
    ap.add_argument("--out", type=Path, default=Path("data/projections.csv"))
    ap.add_argument("--map", action="append", default=[], metavar="col=header",
                    help="override a detected column, e.g. --map fgm=FGMade")
    ap.add_argument("--games-json", type=Path, default=None, metavar="FILE",
                    help='{"PHX": 4, "MEM": 3, ...} -- games each NBA club plays '
                         "in the TARGET WEEK, keyed by the roster's nba_team. This "
                         "is what FR-017 asks for; an export's own games column is "
                         "usually SEASON games and would credit a player with a "
                         "whole season of production in one week")
    ap.add_argument("--games", type=int, default=None,
                    help="fallback games per player when the export has none. "
                         "A constant is a POOR substitute -- FR-017 wants the "
                         "real schedule -- so this warns when used")
    ap.add_argument("--force", action="store_true",
                    help="write the file even if coverage would fail")
    args = ap.parse_args()

    overrides = dict(pair.split("=", 1) for pair in args.map)

    week_games: dict[str, int] = {}
    if args.games_json:
        import json
        week_games = {
            CLUB_ALIASES.get(k.upper(), k.upper()): int(v)
            for k, v in json.loads(args.games_json.read_text()).items()
        }
        print(f"schedule: {len(week_games)} clubs, "
              f"{min(week_games.values())}-{max(week_games.values())} games this week")

    roster = list(csv.DictReader(args.rosters.open(encoding="utf-8")))
    if not roster:
        raise SystemExit(f"{args.rosters} is empty")

    source = list(csv.DictReader(args.projections.open(encoding="utf-8")))
    if not source:
        raise SystemExit(f"{args.projections} is empty")

    cols = detect(list(source[0].keys()), overrides)

    # Makes may be supplied directly, or derived from percentage x attempts.
    derivable = {
        kind: (f"{kind}_pct" in cols and f"{kind}a" in cols) for kind in ("fg", "ft")
    }
    for kind, ok in derivable.items():
        if f"{kind}m" not in cols and ok:
            print(f"  deriving {kind}m from {cols[f'{kind}_pct']} x {cols[f'{kind}a']}")

    required = ["name", "pts", "reb", "ast"]
    for kind in ("fg", "ft"):
        required.append(f"{kind}a")
        if f"{kind}m" not in cols and not derivable[kind]:
            required.append(f"{kind}m")
    missing = [c for c in required if c not in cols]
    if missing:
        raise SystemExit(
            f"Could not find these columns in the export: {missing}\n"
            f"Headers present: {list(source[0].keys())}\n"
            "Use --map col=header to point them at the right ones."
        )
    print(f"detected columns: { {k: v for k, v in sorted(cols.items())} }\n")

    # Index the export by exact name, then by first-initial as a second pass.
    by_name: dict[str, dict] = {}
    by_initial: dict[str, dict] = {}
    for row in source:
        raw = row.get(cols["name"], "")
        by_name.setdefault(normalize(raw), row)
        key = initial_key(raw)
        if key:
            by_initial.setdefault(key, row)

    out_rows, unmatched = [], []
    unknown_clubs: set[str] = set()
    for player in roster:
        key = normalize(player["name"])
        hit = by_name.get(key) or by_initial.get(initial_key(player["name"])) \
            or by_initial.get(key)
        if hit is None:
            unmatched.append(player)
            continue

        # The real schedule wins over anything in the export, which is almost
        # always SEASON games rather than games in the target week.
        club = CLUB_ALIASES.get(
            (player.get("nba_team") or "").upper(), (player.get("nba_team") or "").upper()
        )
        if week_games:
            games = float(week_games.get(club, 0))
            if club and club not in week_games:
                unknown_clubs.add(club)
        elif "projected_games" in cols:
            games = value(hit, cols, "projected_games")
        else:
            games = 0.0
        if not games and args.games:
            games = float(args.games)

        made = {}
        for kind in ("fg", "ft"):
            direct = value(hit, cols, f"{kind}m") if f"{kind}m" in cols else None
            made[f"{kind}m"] = (
                direct if direct is not None else (derive_makes(hit, cols, kind) or 0.0)
            )

        out_rows.append({
            "player_id": player["player_id"],
            "name": player["name"],
            "positions": player.get("positions", ""),
            "projected_games": int(round(games)),
            **{c: round(value(hit, cols, c), 3) for c in
               ("pts", "reb", "ast", "stl", "blk", "tpm", "to", "fga", "fta")},
            **{k: round(v, 3) for k, v in made.items()},
        })

    # Report before writing. An unmatched player is NOT a rounding error: he
    # reads as unprojected, which can take his whole team under the floor.
    # Catch a wrong-column match generally rather than per provider: a counting
    # category cannot be negative, and a standardized value routinely is.
    for col in ("pts", "reb", "ast", "stl", "blk", "tpm", "to", "fga", "fta"):
        negatives = sum(1 for r in out_rows if r[col] < 0)
        if negatives:
            raise SystemExit(
                f"{negatives} of {len(out_rows)} values in '{col}' are negative, "
                f"read from column {cols.get(col)!r}. A counting category cannot "
                "be negative -- that column is almost certainly a z-score rather "
                f"than a per-game total. Use --map {col}=<header> to correct it."
            )

    print(f"matched {len(out_rows)} of {len(roster)} rostered players")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) -- these will count as unprojected:")
        for p in unmatched:
            print(f"  {p['team_id']}  {p['name']}  ({p.get('nba_team','')})")
        print("\nFix by adding them to the export, or correct the spelling there.")

    if unknown_clubs:
        print(f"\nCLUBS NOT IN THE SCHEDULE FILE: {sorted(unknown_clubs)}")
        print("Those players get zero games and are excluded from lineups. "
              "Usually an abbreviation mismatch between the roster and the schedule.")

    if args.games:
        print(f"\nWARNING: projected_games defaulted to {args.games} where the "
              "export had none. FR-017 wants the real per-player schedule; a "
              "constant flattens the 3-game/4-game spread that decides close weeks.")

    per_team: dict[str, int] = {}
    for p in roster:
        per_team.setdefault(p["team_id"], 0)
    for r in out_rows:
        owner = next(p["team_id"] for p in roster if p["player_id"] == r["player_id"])
        per_team[owner] += 1
    thin = {t: n for t, n in sorted(per_team.items()) if n < 6}
    if thin:
        print(f"\nTEAMS THAT CANNOT FIELD SIX PROJECTED PLAYERS: {thin}")
        print("The run will refuse to publish until these are covered.")
        if not args.force:
            print("\nNot writing. Re-run with --force to write anyway.")
            return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(TARGET))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"\nwrote {len(out_rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
