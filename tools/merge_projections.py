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
    "name": ("name", "player", "playername", "player name"),
    "projected_games": ("games", "gp", "g", "projectedgames", "gamesplayed"),
    "pts": ("pts", "points", "p"),
    "reb": ("reb", "rebounds", "trb", "r"),
    "ast": ("ast", "assists", "a"),
    "stl": ("stl", "steals", "st", "s"),
    "blk": ("blk", "blocks", "bk", "b"),
    "tpm": ("tpm", "3pm", "3ptm", "threes", "3s", "fg3m"),
    "to": ("to", "tov", "turnovers"),
    "fgm": ("fgm", "fgmade", "fgm/g", "fg made"),
    "fga": ("fga", "fgatt", "fgattempted", "fg att"),
    "ftm": ("ftm", "ftmade", "ft made"),
    "fta": ("fta", "ftatt", "ftattempted", "ft att"),
}

#: Spellings that mean the source gave a PERCENTAGE instead of makes/attempts.
PERCENTAGE_HEADERS = ("fg%", "fgpct", "fg_pct", "ft%", "ftpct", "ft_pct", "fgp", "ftp")

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


def detect(headers: list[str], overrides: dict[str, str]) -> dict[str, str]:
    """Map each target column to a header in the source file."""
    lowered = {h.strip().lower().replace("_", "").replace(" ", ""): h for h in headers}

    offending = [h for h in lowered if h in [p.replace("_", "").replace(" ", "") for p in PERCENTAGE_HEADERS]]
    if offending and not any(
        a.replace("_", "") in lowered for a in ("fgm", "fga")
    ):
        raise SystemExit(
            f"This export gives percentages ({offending}) and no makes/attempts.\n"
            "A percentage cannot be turned back into attempts -- '.458' is "
            "consistent with 11/24 and 22/48, which aggregate differently -- so "
            "the ranking cannot use it. Pick an export with FGM/FGA and FTM/FTA."
        )

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
    ap.add_argument("--games", type=int, default=None,
                    help="fallback games per player when the export has none. "
                         "A constant is a POOR substitute -- FR-017 wants the "
                         "real schedule -- so this warns when used")
    ap.add_argument("--force", action="store_true",
                    help="write the file even if coverage would fail")
    args = ap.parse_args()

    overrides = dict(pair.split("=", 1) for pair in args.map)

    roster = list(csv.DictReader(args.rosters.open(encoding="utf-8")))
    if not roster:
        raise SystemExit(f"{args.rosters} is empty")

    source = list(csv.DictReader(args.projections.open(encoding="utf-8")))
    if not source:
        raise SystemExit(f"{args.projections} is empty")

    cols = detect(list(source[0].keys()), overrides)
    missing = [c for c in ("name", "pts", "reb", "ast", "fgm", "fga", "ftm", "fta")
               if c not in cols]
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
    for player in roster:
        key = normalize(player["name"])
        hit = by_name.get(key) or by_initial.get(initial_key(player["name"])) \
            or by_initial.get(key)
        if hit is None:
            unmatched.append(player)
            continue

        def num(col: str, default: float = 0.0) -> float:
            raw = str(hit.get(cols.get(col, ""), "")).strip()
            try:
                return float(raw)
            except ValueError:
                return default

        games = num("projected_games", 0.0) if "projected_games" in cols else 0.0
        if not games and args.games:
            games = float(args.games)

        out_rows.append({
            "player_id": player["player_id"],
            "name": player["name"],
            "positions": player.get("positions", ""),
            "projected_games": int(round(games)),
            **{c: round(num(c), 2) for c in
               ("pts", "reb", "ast", "stl", "blk", "tpm", "to", "fgm", "fga", "ftm", "fta")},
        })

    # Report before writing. An unmatched player is NOT a rounding error: he
    # reads as unprojected, which can take his whole team under the floor.
    print(f"matched {len(out_rows)} of {len(roster)} rostered players")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) -- these will count as unprojected:")
        for p in unmatched:
            print(f"  {p['team_id']}  {p['name']}  ({p.get('nba_team','')})")
        print("\nFix by adding them to the export, or correct the spelling there.")

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
