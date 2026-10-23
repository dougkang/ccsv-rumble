# ccsv-rumble

Weekly power rankings and write-up generator for an 18-team head-to-head 9-category
fantasy basketball league.

Once a week it pulls the full league grid from Yahoo, computes power rankings with the
all-play algorithm in [`docs/rankings-algorithm-v1.md`](docs/rankings-algorithm-v1.md),
asks Claude to write a short column about the week, renders static HTML, and pushes it
to the `pages` branch.

**Live site:** <https://dgkng.io/ccsv-rumble/>

## Repository layout

| Branch | Contents |
|---|---|
| `main` | Generator code, specs, docs, and the archive |
| `pages` | Generated website (orphan branch; GitHub Pages source) |

Publishing targets a branch of this same repository, so GitHub Actions' built-in
`GITHUB_TOKEN` is sufficient — there is no stored personal access token to rotate.

## Quick start

```bash
uv sync                                    # Python 3.14 + dependencies
uv run pytest                              # 355 tests, all offline
uv run ccsv-rumble dry-run --week 1        # fetch and render, publish nothing
```

## Commands

| Command | What it does |
|---|---|
| `run` | The weekly job: detect gaps and corrections, acquire, rank, write, render, push once |
| `dry-run` | Everything except publishing. `--from-archive` skips network and model entirely |
| `replay --week N` | Rebuild a past week from the archive. No network, no model |
| `verify --week N --against PATH` | Confirm a replay matches what is published, byte for byte |

Useful flags: `--no-backfill` (current week only), `--recheck-weeks N` (correction
window; `0` disables), `--entry ID` / `--latest` on replay.

## Configuration

All secrets come from the environment; none may be passed as arguments.

| Variable | Required | Purpose |
|---|---|---|
| `YAHOO_CLIENT_ID` | yes | OAuth2 app credential |
| `YAHOO_CLIENT_SECRET` | yes | OAuth2 app credential |
| `YAHOO_REFRESH_TOKEN` | yes | Long-lived; access tokens derived per run |
| `YAHOO_LEAGUE_KEY` | yes | e.g. `454.l.XXXXXX` |
| `ANTHROPIC_API_KEY` | no | Absent → rankings-only page, which is a complete page |
| `GITHUB_TOKEN` | in CI | Supplied automatically by Actions |
| `GITHUB_REPOSITORY` | in CI | Supplied automatically by Actions |

### One-time setup

1. **Yahoo OAuth app** — create one at <https://developer.yahoo.com/apps/>.

   **The app must be granted Fantasy Sports → Read.** This is the single most likely
   setup failure, and it does not look like a permission problem: every fantasy
   endpoint returns `403 Forbidden` with *"This application is not authorized to
   perform this action"* — including `game/nba`, which involves no league at all. The
   token refresh still succeeds with `200 OK`, so auth appears healthy right up until
   the first real request.

   Two tells that the permission is missing: the token response carries no `scope`
   field and no `xoauth_yahoo_guid`.

   **Changing app permissions does not upgrade existing tokens.** After granting
   Fantasy Sports access, re-run the consent flow to mint a *new* refresh token; the
   old one keeps its original (empty) grant forever.

   Then confirm the account can see the league, and get its exact key:

   ```bash
   uv run ccsv-rumble leagues
   ```

   League keys are `{game_key}.l.{league_id}` where `game_key` is a season-specific
   **number** (e.g. `466.l.194131`). The sport code form — `nba.l.194131` — also
   returns 403, which is easy to mistake for the permission problem above.

   Finally, store the four `YAHOO_*` values as Actions secrets. Everything after that
   is unattended.
2. **`ANTHROPIC_API_KEY`** — optional. Without it the page publishes rankings and events
   with no write-up.
3. **GitHub Pages** — already enabled on the `pages` branch at `/`.
4. **Enforce HTTPS** once GitHub provisions the certificate:
   ```bash
   gh api repos/dougkang/ccsv-rumble/pages --jq '.https_certificate.state'   # wait for non-null
   gh api -X PUT repos/dougkang/ccsv-rumble/pages -F 'https_enforced=true'
   ```

### `data/rosters.csv`

Who is on which team. **League** data, and a separate input from projections.

Required for the week-0 draft ranking, and it is what supplies the in-season roster prior. Nothing
acquires rosters automatically yet — the Yahoo app is gated behind Yahoo's review — so capture them
from the league pages in a browser:

```
1. Open a team's roster page.
2. Paste tools/yahoo_roster_capture.js into the DevTools console.
3. __roster.grab()        for each team, navigating between calls
4. __roster.status()      shows which teams are still missing
5. __roster.save()        downloads rosters.csv
```

```csv
team_id,player_id,name,positions,status,team_name
t.01,nba.p.1234,A. Player,"PG,SG",,Keyboard Cats
```

`positions` uses the provider's raw eligibility; `team_name` and `status` are optional. Gitignored.

**Why this is not folded into `projections.csv`.** It looks like one file would do, and it would be
wrong. FR-025 requires that a rostered player with *no* projection be counted rather than dropped —
and a projections file omits exactly those players by construction. The two inputs disagree about
who exists, which is why both are needed.

**Before the draft there is nothing to capture, and that is fine.** With no roster file the run
publishes nothing, exits zero, and sends no notification: an undrafted league is a normal state.
The reason is logged every run, because that log line is the only signal a deliberately silent
outcome has.

### `data/draft-results.csv`

The draft board, pick by pick. **League** data, and needed only by the week-0 recap — the
ranking never reads it.

```
1. Open https://basketball.fantasysports.yahoo.com/nba/<league-id>/draftresults
2. Paste tools/yahoo_draft_capture.js into the DevTools console.
3. __draft.save()         downloads draft-results.csv
```

```csv
round,pick_in_round,overall,player_id,player_name,nba_team,positions,team_name
1,1,1,nba.p.5352,Nikola Jokić,DEN,FC,🥭 smoothie's team
```

`team_name` is the display name, which is all the page offers; it is resolved against
`rosters.csv` to get the `t.NN` id every other stage uses. **Both files must come from the
same league** — a team named here but not there makes the board unusable rather than
silently dropping a team from the recap. Gitignored.

**Capture after the draft finishes, not during.** A board with a gap, a missing team, or a
partial round is treated as *unavailable*: the page publishes its ranking and omits the
article entirely. A recap written from half a draft would confidently describe a draft that
did not happen, and unlike a missing article, a wrong one looks fine to a reader.

**Without the file the page still publishes** — ranking table, no article section, no
placeholder, and a notification if `ANTHROPIC_API_KEY` is set. On a rankings-only
deployment there is no notification, because no recap was ever going to be written.

### Getting the data files: the whole loop

```bash
# 1. Rosters — paste tools/yahoo_roster_capture.js on a Yahoo team page
#    __roster.grab() on each of the 18 teams, then __roster.save()
#    → data/rosters.csv

# 2. Projections + schedule — paste tools/espn_projections.js on fantasy.espn.com
await __espn.projections()                      # → espn-projections.csv
await __espn.schedule("20261020", "20261026")   # → games.json

# 3. Draft board (week 0 recap only) — paste tools/yahoo_draft_capture.js
#    on the league's draftresults page, then __draft.save()
#    → data/draft-results.csv

# 4. Join the projections onto your Yahoo player ids
uv run python tools/merge_projections.py \
    --projections ~/Downloads/espn-projections.csv \
    --games-json  ~/Downloads/games.json
    # → data/projections.csv

# 5. Publish
uv run ccsv-rumble dry-run --out /tmp/site
```

**Why ESPN rather than a paid source.** Its projections table shows `FG%`/`FT%`
with no attempts — the one shape the ranking genuinely cannot use, since neither
makes nor attempts can be recovered from a percentage alone. But its API carries
raw `FGM/FGA/FTM/FTA`, which is what `espn_projections.js` reads. Free, and no
third party's numbers are republished: strict disclosure means only rank reaches
the page.

**Two traps worth knowing**, both found by hitting them:

- ESPN's games figure is **season** games (65–72). Using it as the week's games
  credits a player with a whole season of production in one week, so
  `--games-json` supplies the real per-club schedule instead. The spread is
  real: in a typical week some clubs play 4 and some play 2.
- Yahoo and ESPN disagree on six club abbreviations (`GSW`/`GS`, `NOP`/`NO`,
  `NYK`/`NY`, `SAS`/`SA`, `UTA`/`UTAH`, `WAS`/`WSH`). The merge tool maps them;
  without that those six clubs get zero games, which reads as "did not play" and
  quietly drops their players out of every lineup.

### `data/projections.csv`

Per-player, per-game projections for all nine categories. Required for the week-0 draft
ranking; optional in-season, where it supplies the forward-looking term.

> **The format changed in `002`.** The old single-value schema — `player_id,value` — is now
> **rejected at ingest**, not silently accepted. One pre-aggregated number cannot produce a
> category profile, which is the main reason a week-0 page is worth publishing at all.

```csv
player_id,name,positions,projected_games,pts,reb,ast,stl,blk,tpm,to,fgm,fga,ftm,fta
nba.p.1234,A. Player,"PG,SG",4,24.1,4.2,6.8,1.1,0.4,2.9,2.4,8.6,18.8,4.1,4.7
```

- **FG and FT must be makes and attempts, never a percentage.** A source publishing `FG%`
  is refused with an explicit error rather than partially used: `.458` is consistent with
  `11/24` and with `22/48`, which aggregate into a team week differently, so the attempts
  cannot be recovered. This is a go/no-go on any projection source.
- `projected_games` is that player's real-schedule games for the target week, per player —
  not a league-average constant.
- `positions` uses the provider's raw eligibility. This league's lineup is `2G, 3FC, 1 Util`,
  so a guard fills `G`, a forward or centre fills `FC`, and anyone fills `UTIL`. A player
  with no positions listed is eligible for `UTIL` only.
- Values are per-game and fractional. They are summed across the week and rounded **once**,
  at the end.
- The file is gitignored. See
  [`specs/002-draft-ranking-week-0/contracts/projection-source.md`](specs/002-draft-ranking-week-0/contracts/projection-source.md)
  for the full contract.

**Coverage floors.** A team must be able to fill at least 80% of its six active slots from
projected players, and the league at least 95% of all 108. Below either, the run publishes
nothing, exits non-zero, and notifies — a ranking built from mostly-missing inputs is a
broken page, not a degraded one. The two floors catch different failures: one unrankable
team trips the first, while every team missing one slot trips only the second.

**When it is absent in-season**, week 1 publishes with a **provisional** badge and a note
saying a single week moves the numbers a long way. The ranking is still computed — by week 1
there are real results, and 153 category comparisons per team is not nothing — but the page
says plainly that it is thin.

**Before the draft**, the run publishes nothing, **exits zero, and sends no notification**.
An undrafted league is a normal state, not a failure. The reason is always logged, because
that log line is the only signal a deliberately silent outcome has.

## How it works

```
1. resolve target week; detect archived gaps                  (FR-037)
2. acquire correction window: re-fetch last 3 weeks           (FR-045)
3. acquire gap weeks                                          (FR-038)
4. archive — new entry for changed weeks, first entry for gaps (FR-046)
5. for each gap week, ascending: rank → report → article → render → buffer
6. current week: rank over corrected history → … → buffer
7. render index                                               (FR-040)
8. diff buffer against published; if changed, ONE atomic push (FR-042)
9. notify: weeks backfilled, corrections found, articles failed
```

Steps 2–3 must complete before any ranking is computed: a correction to week 5 changes
the recency-weighted history that week 6's ranking is built from.

### Design properties worth knowing

- **The ranking never leaves the archive.** `PublishableReport` has no field that can
  hold a power score, so the page shows rank and movement and nothing else derived from
  the computation. Insights like schedule luck reach the page as prose, never figures.
- **The article is an acquisition step.** A language model is not reproducible, so its
  output is archived like fetched data and replayed from there. Rendering stays
  deterministic; regeneration never calls a model.
- **A week can hold several archive entries.** Corrections append `entry-002` rather
  than overwriting `entry-001`, and each published page records which entry it used — so
  a corrected week feeds future rankings while its published page stays as published.
- **An article failure degrades one page, not the run.** A rankings-only page is defined
  as complete. The page gives no sign the article is missing, which makes the
  notification channel the only signal — a failed notification is therefore treated as a
  failed run.

## Project documents

| Document | Purpose |
|---|---|
| [`.specify/memory/constitution.md`](.specify/memory/constitution.md) | Governance: determinism, archiving, accessibility, secrets |
| [`docs/rankings-algorithm-v1.md`](docs/rankings-algorithm-v1.md) | The all-play algorithm and why it beats win-loss record |
| [`specs/001-power-ranking-article/`](specs/001-power-ranking-article/) | Spec, plan, research, data model, contracts, tasks |
| [`docs/design-philosophy.md`](docs/design-philosophy.md) | Visual style: newspaper meets nutrition label, with project amendments |
| [`specs/003-newspaper-style-alignment/`](specs/003-newspaper-style-alignment/) | Spec, plan, research, data model, contracts, tasks |

## Development

```bash
uv run pytest                                        # full suite
uv run ruff check src/ tests/                        # lint
uv run ccsv-rumble dry-run --from-archive --week 4   # pre-merge gate
```

Changing a ranking constant in `config.py` means bumping `ALGORITHM_VERSION` and
attaching a before/after rank comparison on archived weeks to the PR. Replay the
affected weeks under both sets of constants and diff the result.
