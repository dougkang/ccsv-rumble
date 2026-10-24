#!/usr/bin/env python3
"""Drive the browser captures from the command line, via Chrome.

    uv run python tools/chrome_capture.py draft        -> data/draft-results.csv
    uv run python tools/chrome_capture.py rosters      -> data/rosters.csv
    uv run python tools/chrome_capture.py projections  -> data/projections.csv inputs
    uv run python tools/chrome_capture.py matchups     -> data/matchups.csv
    uv run python tools/chrome_capture.py all

`matchups` captures the week the league scoreboard is showing; pass --week N
for another.

Requires one Chrome setting, once per machine:

    View -> Developer -> Allow JavaScript from Apple Events

Without it every call fails with `Access not allowed. (-1723)`, which this
script detects up front and explains rather than letting it surface as an
AppleScript error thirty lines deep.

WHY THIS EXISTS, GIVEN THE .js FILES ALREADY DID THE WORK

Two reasons, and the second is the one that matters.

1. It is one command instead of eighteen manual navigations. Rosters live one
   team per page, so capturing them by hand means `__roster.grab()` on each of
   18 pages.

2. **It never touches the filesystem from inside the browser.** `execute
   javascript` RETURNS the value to stdout, so the CSV comes back up the pipe
   and Python writes it. The console flow relies on a download into
   `~/Downloads`, which macOS TCC blocks from a terminal-launched process --
   that is a real failure this project already hit, and it cost a manual file
   move to work around. There is no download, no Downloads permission, and no
   file to move here.

The scraping logic is NOT duplicated. Each `tools/*.js` file is read off disk
and evaluated in the page, then its public function is called for its return
value. One implementation, two ways to drive it.

ON THE ESCAPING

The JS is base64'd and evaluated as `eval(atob("..."))`. The scrapers contain
both quote styles, regexes, and template literals, and threading those through
AppleScript's string rules intact is a losing game. base64 is alphanumeric plus
`+/=`, so it passes through untouched.

ON ASYNC

AppleScript cannot await a promise: `execute javascript` returns as soon as the
expression evaluates, so an `async` scraper yields `missing value`. The ESPN
captures therefore stash their result on `window.__capture_result` and are
polled for it. This is a real limitation of the bridge, not a style choice.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent

YAHOO = "https://basketball.fantasysports.yahoo.com"
ESPN_ORIGIN = "https://fantasy.espn.com/basketball/players/projections"


class CaptureError(RuntimeError):
    """A failure the operator can act on. Printed without a traceback."""


# --- the AppleScript bridge ---------------------------------------------------


def _osa(script: str, timeout: int = 120) -> str:
    done = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=timeout
    )
    if done.returncode != 0:
        err = done.stderr.strip()
        if "-1723" in err or "Access not allowed" in err:
            raise CaptureError(
                "Chrome returned 'Access not allowed' (-1723).\n"
                "Usually the one-time setting:  View -> Developer -> Allow "
                "JavaScript from Apple Events\n"
                "But if that is ALREADY enabled, suspect the AppleScript "
                "instead: a misordered `execute` command returns this exact "
                "code. See the note in run_js()."
            )
        if "-1728" in err or "Invalid index" in err:
            raise CaptureError("Chrome has no open window. Open one and retry.")
        raise CaptureError(f"osascript failed: {err}")
    return done.stdout.rstrip("\n")


def run_js(js: str, *, timeout: int = 120) -> str:
    """Evaluate JS in Chrome's active tab and return its value as text.

    Note the argument order. Chrome's `scripting.sdef` declares

        <command name="execute">
          <direct-parameter type="specifier">   <- the TAB
          <parameter name="javascript">         <- the CODE

    so the tab is the DIRECT parameter and the code is the named one:
    `execute (active tab of front window) javascript "..."`.

    Writing it the other way round -- `execute javascript "..." in active tab
    of front window` -- does not fail as a syntax error. AppleScript instead
    parses it as an attempt to GET the reference `"..." in active tab of front
    window`, and that returns `Access not allowed. (-1723)`: the very same code
    Chrome returns when the Apple-Events toggle is off. The error therefore
    points straight at a setting that is already correct.
    """
    payload = base64.b64encode(js.encode("utf-8")).decode("ascii")
    return _osa(
        'tell application "Google Chrome" to execute '
        f'(active tab of front window) javascript "eval(atob(\\"{payload}\\"))"',
        timeout=timeout,
    )


def navigate(url: str, *, ready_js: str = "true", label: str = "") -> None:
    """Point the active tab at `url` and wait until the page is usable.

    `ready_js` must evaluate truthy only once the content being scraped exists.
    Waiting on `readyState` alone is not enough on these pages: the document
    completes well before the roster table is populated, and scraping in that
    window silently yields zero rows -- which looks like an empty team rather
    than a race.
    """
    _osa(
        'tell application "Google Chrome" to set URL of active tab of front '
        f'window to "{url}"'
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(0.6)
        try:
            state = run_js("document.readyState", timeout=30)
            if state != "complete":
                continue
            if run_js(f"String(Boolean({ready_js}))", timeout=30) == "true":
                return
        except CaptureError:
            # A navigation in flight can briefly refuse evaluation; keep waiting.
            continue
    raise CaptureError(f"timed out waiting for {label or url}")


def preflight() -> None:
    windows = _osa('tell application "Google Chrome" to return (count of windows)')
    if windows.strip() in {"", "0"}:
        raise CaptureError("Chrome has no open window. Open one and retry.")
    # Round-trips a value, which is the only way to prove the toggle is on.
    if run_js('"ok"') != "ok":
        raise CaptureError("Chrome did not return a value from JavaScript.")


def _script(name: str) -> str:
    path = TOOLS / name
    if not path.is_file():
        raise CaptureError(f"missing scraper: {path}")
    return path.read_text(encoding="utf-8")


def _await_result(kickoff: str, *, label: str, timeout: int = 180) -> str:
    """Run an async capture and poll for its result.

    See the module docstring: the bridge cannot await a promise, so the scraper
    parks its output on `window.__capture_result` and we wait for it.
    """
    run_js(
        "window.__capture_result = null; window.__capture_error = null;\n"
        f"{kickoff}\n'started'"
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        err = run_js("String(window.__capture_error || '')")
        if err:
            raise CaptureError(f"{label} failed in the page: {err}")
        if run_js("String(typeof window.__capture_result)") == "string":
            return run_js("window.__capture_result")
    raise CaptureError(f"{label} did not finish within {timeout}s")


# --- league discovery ---------------------------------------------------------


def current_league() -> str | None:
    url = _osa(
        'tell application "Google Chrome" to return URL of active tab of front window'
    )
    found = re.search(r"/nba/(\d+)\b", url)
    return found.group(1) if found else None


def resolve_league(given: str | None) -> str:
    """`--league`, then `$YAHOO_LEAGUE_ID`, then whatever tab is open.

    Tab discovery is last because it is the least stable of the three: the
    captures navigate the tab themselves, so by the time a second capture runs
    the tab may be showing ESPN and discovery fails on a league it already knew.
    """
    league = given or os.environ.get("YAHOO_LEAGUE_ID") or current_league()
    if not league:
        raise CaptureError(
            "could not tell which league to capture. Pass --league <id>, set "
            "YAHOO_LEAGUE_ID, or open a Yahoo league page in Chrome. The id is "
            "the number in the league URL, e.g. .../nba/91825/..."
        )
    return league


# --- the captures -------------------------------------------------------------


def capture_draft(league: str) -> str:
    navigate(
        f"{YAHOO}/nba/{league}/draftresults",
        # Must be the SAME thing the scraper keys on -- a "Round N" header --
        # not merely "a table exists". The page carries layout tables before the
        # board renders, so the looser check passes early and the capture comes
        # back with zero picks: a race that reads as "the draft has not
        # happened". Observed, not hypothetical.
        ready_js=(
            '[...document.querySelectorAll("th")]'
            '.some(e => /^Round \\d+$/.test((e.textContent||"").trim()))'
        ),
        label="draft results",
    )
    csv = run_js(_script("yahoo_draft_capture.js") + "\n__draft.csv()")
    rows = csv.count("\n")
    if rows < 2:
        raise CaptureError(
            "the draft page yielded no picks. Has the draft happened, and is "
            "the board fully loaded?"
        )
    print(f"[capture] draft: {rows} picks", file=sys.stderr)
    return csv


def capture_rosters(league: str, teams: int = 18) -> str:
    """Visit each team page in turn, accumulating in the page's localStorage.

    The accumulator is deliberately in `localStorage` rather than in this
    process: it survives the navigation between teams, which an in-page closure
    does not. That exact bug produced a one-team capture once already.
    """
    # Clear first. The accumulator lives in the page's localStorage and
    # outlives the run, so without this a second capture finds all 18 teams
    # already present, skips every one, and hands back the PREVIOUS run's
    # rosters as if they were fresh -- wrong in exactly the way that does not
    # look wrong.
    navigate(
        f"{YAHOO}/nba/{league}/1",
        ready_js='document.querySelectorAll("table tr").length > 3',
        label="team 1",
    )
    run_js(_script("yahoo_roster_capture.js") + "\n__roster.reset()")
    for team in range(1, teams + 1):
        navigate(
            f"{YAHOO}/nba/{league}/{team}",
            ready_js='document.querySelectorAll("table tr").length > 3',
            label=f"team {team}",
        )
        got = run_js(_script("yahoo_roster_capture.js") + "\n__roster.grab()")
        print(f"[capture] team {team}/{teams}: {got}", file=sys.stderr)

    csv = run_js(_script("yahoo_roster_capture.js") + "\n__roster.csv()")
    if csv.count("\n") < teams:
        raise CaptureError(f"rosters look short:\n{csv[:400]}")
    print(f"[capture] rosters: {csv.count(chr(10))} rows", file=sys.stderr)
    return csv


#: data/matchups.csv columns. One row per team per matchup -- each side of a
#: matchup gets its own row, so a team's line never has to be split out of a
#: pair. Shooting is makes and attempts; the percentages are Yahoo's rounded
#: display values, kept only as a checksum (see the CategoryLine docstring).
MATCHUP_FIELDS = (
    "week", "matchup", "team_id", "team_name", "opponent_id",
    "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "to",
    "fg_pct_display", "ft_pct_display", "cat_wins",
)
_MATCHUP_INTS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "to")


def _check_pct(row: dict, made: str, att: str, shown: str, label: str) -> None:
    """Yahoo's displayed percentage must agree with the makes and attempts.

    A mismatch means a column was misread, not that Yahoo rounds oddly: the
    tolerance is half a unit in the third decimal place, which is exactly the
    rounding the display applies.
    """
    if int(row[att]) == 0 or not re.fullmatch(r"\d?\.\d+", row[shown]):
        return
    if abs(int(row[made]) / int(row[att]) - float(row[shown])) > 0.0005 + 1e-9:
        raise CaptureError(
            f"{label}: {row['team_id']} {made}/{att} {row[made]}/{row[att]} "
            f"does not match the displayed {row[shown]}"
        )


def capture_matchups(league: str, week: int | None = None, teams: int = 18) -> str:
    """Every matchup of `week`, with each side's category totals.

    Pairings are read off the scoreboard rather than built from a URL pattern,
    then each matchup page is visited for its team table. A week in progress
    yields partial totals; the `week` column is what keeps them distinguishable.

    With no `week`, the scoreboard's own default -- the current week -- is
    used, read from its matchup links rather than computed from a calendar.
    """
    script = _script("yahoo_matchup_capture.js")
    query = f"matchup_week={week}&module=matchups" if week else "module=matchups"
    navigate(
        f"{YAHOO}/nba/{league}?{query}",
        ready_js=f'document.querySelectorAll(\'a[href*="/matchup?week={week or ""}"]\').length > 0',
        label=f"week {week or '(current)'} scoreboard",
    )
    pairs = json.loads(run_js(script + "\n__matchup.pairs()"))
    if week is None:
        weeks = {p["week"] for p in pairs}
        if len(weeks) != 1:
            raise CaptureError(
                f"the scoreboard links matchups from weeks {sorted(weeks)}; "
                "pass --week N to choose one."
            )
        week = weeks.pop()
    pairs = [p for p in pairs if p["week"] == week]
    if len(pairs) != teams // 2:
        raise CaptureError(
            f"week {week} scoreboard shows {len(pairs)} matchups, expected {teams // 2}"
        )

    headers = ["Team", "FGM/A*", "FG%", "FTM/A*", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
    rows: list[dict] = []
    for index, pair in enumerate(pairs, start=1):
        label = f"matchup {index}/{len(pairs)} ({pair['team_a']} v {pair['team_b']})"
        navigate(
            pair["url"],
            # The same thing grab() keys on: a table headed by every column AND
            # carrying both team rows. A header alone can render before the body.
            ready_js=(
                '[...document.querySelectorAll("table")].some(t => '
                f"{json.dumps(headers)}.every(k => [...t.querySelectorAll(\"thead th\")]"
                '.some(e => e.textContent.trim() === k)) && t.querySelectorAll("tbody tr").length >= 2)'
            ),
            label=label,
        )
        got = json.loads(run_js(script + "\n__matchup.grab()"))
        if got.get("error"):
            raise CaptureError(f"{label}: {got['error']}")
        sides = got["rows"]
        ids = [s["team_id"] for s in sides]
        if sorted(ids) != sorted([pair["team_a"], pair["team_b"]]):
            raise CaptureError(f"{label}: page shows teams {ids}")
        for side in sides:
            for field in _MATCHUP_INTS:
                if not re.fullmatch(r"\d+", side[field]):
                    raise CaptureError(f"{label}: {side['team_id']} {field} is {side[field]!r}")
            if int(side["fgm"]) > int(side["fga"]) or int(side["ftm"]) > int(side["fta"]):
                raise CaptureError(f"{label}: {side['team_id']} makes exceed attempts")
            _check_pct(side, "fgm", "fga", "fg_pct_display", label)
            _check_pct(side, "ftm", "fta", "ft_pct_display", label)
            other = ids[1] if side["team_id"] == ids[0] else ids[0]
            rows.append({**side, "week": week, "matchup": index, "opponent_id": other})
        print(
            f"[capture] {label}: "
            + " v ".join(f"{s['team_name']} {s['pts']} pts" for s in sides),
            file=sys.stderr,
        )

    seen = sorted(r["team_id"] for r in rows)
    expected = [f"t.{n:02d}" for n in range(1, teams + 1)]
    if seen != expected:
        raise CaptureError(f"week {week} matchups do not cover each team once: {seen}")

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=MATCHUP_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    print(f"[capture] matchups: week {week}, {len(rows)} team rows", file=sys.stderr)
    return out.getvalue()


def capture_espn(start: str, end: str) -> tuple[str, str]:
    """ESPN projections plus the real per-club game counts for the week."""
    navigate(
        ESPN_ORIGIN,
        ready_js="true",
        label="ESPN projections",
    )
    projections = _await_result(
        _script("espn_projections.js")
        + "\n__espn.projections()"
        "  .then(v => { window.__capture_result = v; })"
        "  .catch(e => { window.__capture_error = String(e); });",
        label="ESPN projections",
    )
    games = _await_result(
        _script("espn_projections.js")
        + f'\n__espn.schedule("{start}", "{end}")'
        "  .then(v => { window.__capture_result = JSON.stringify(v, null, 2); })"
        "  .catch(e => { window.__capture_error = String(e); });",
        label="ESPN schedule",
    )
    print(
        f"[capture] espn: {projections.count(chr(10))} players, "
        f"{len(json.loads(games))} clubs",
        file=sys.stderr,
    )
    return projections, games


# --- cli ----------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    print(f"[capture] wrote {path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chrome_capture",
        description="Capture league and projection data through Chrome.",
    )
    parser.add_argument(
        "what",
        choices=("draft", "rosters", "projections", "matchups", "all"),
        help="which capture to run",
    )
    parser.add_argument("--league", help="Yahoo league id; inferred from the open tab")
    parser.add_argument("--teams", type=int, default=18)
    parser.add_argument("--data", type=Path, default=REPO / "data")
    parser.add_argument(
        "--week", type=int, help="matchup week, for matchups; defaults to the current one"
    )
    parser.add_argument("--week-start", help="YYYYMMDD, for the ESPN schedule")
    parser.add_argument("--week-end", help="YYYYMMDD, for the ESPN schedule")
    args = parser.parse_args(argv)

    try:
        preflight()
        wants = (
            ("draft", "rosters", "matchups", "projections")
            if args.what == "all"
            else (args.what,)
        )

        if "projections" in wants and not (args.week_start and args.week_end):
            raise CaptureError(
                "projections need the target week: pass --week-start and "
                "--week-end as YYYYMMDD. ESPN's own games figure is SEASON "
                "games, so the real per-club schedule has to be fetched "
                "separately -- using the season figure as a week would credit "
                "a player with a whole season in one week."
            )

        league = (
            resolve_league(args.league)
            if {"draft", "rosters", "matchups"} & set(wants)
            else ""
        )
        if league:
            print(f"[capture] league {league}", file=sys.stderr)

        if "draft" in wants:
            _write(args.data / "draft-results.csv", capture_draft(league))
        if "rosters" in wants:
            _write(args.data / "rosters.csv", capture_rosters(league, args.teams))
        if "matchups" in wants:
            _write(
                args.data / "matchups.csv",
                capture_matchups(league, args.week, args.teams),
            )
        if "projections" in wants:
            projections, games = capture_espn(args.week_start, args.week_end)
            _write(args.data / "espn-projections.csv", projections)
            _write(args.data / "games.json", games)
            print(
                "[capture] now join them onto Yahoo ids:\n"
                "  uv run python tools/merge_projections.py "
                f"--projections {args.data / 'espn-projections.csv'} "
                f"--games-json {args.data / 'games.json'}",
                file=sys.stderr,
            )
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("error: Chrome stopped responding.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
