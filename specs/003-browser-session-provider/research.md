# Research — Browser-Session Data Source

**Feature**: [`003-browser-session-provider`](spec.md)

**Status**: Options assessed, recommendation made, **three discovery runs completed** — see
"Discovery verdicts" at the end, which is the current state of the gates. G4 is settled (nothing is
fetched; the provider parses markup). G1 is confirmed at player level but **not yet at team level**,
which is the one open question that decides the feature.

> Originally written as `docs/browser-acquisition-options.md` before this feature was specified.
> Relocated here because `docs/` holds algorithm documents, and option assessment is plan-phase
> research belonging to the feature that consumes it.

## Why the OAuth path is blocked

The OAuth path is blocked on a `403` that is a property of the *registered application*,
not of the account: Yahoo refuses every fantasy endpoint, including `game/nba`, until the
app holds Fantasy Sports → Read, and an already-issued refresh token keeps its original
empty grant even after the permission is granted.

A browser session sidesteps that entirely, because the Yahoo Fantasy web app authenticates
**as you**, not as a registered app. There is no app grant in the path, so there is nothing
in the 403's causal chain left to fail.

## What makes this cheap here

The architecture already anticipated a provider swap. `LeagueDataProvider`
(`src/ccsv_rumble/fetch/provider.py`) is a Protocol returning raw payloads; normalization is
a separate pure step; and the provider is constructed in exactly one place
(`cli.py:58 _provider_from_env`). A new provider touches that function, one new module, and
the normalizer — and nothing in `rank`, `report`, `render`, or `publish`.

`data/` is empty, so there is no archived Yahoo JSON to stay compatible with. The raw shape
is a free choice. `Snapshot.raw_source` already records a filename per entry, so a
web-sourced entry distinguishes itself as `raw-yahoo-web.json` with no schema change.

## The options

| | Approach | Unattended? | New deps | Main risk |
|---|---|---|---|---|
| **A** | Get the app approved | yes | none | gated on Yahoo's review — no timeline, may be refused |
| **B** | **Browser-minted cookie + `httpx`** | **yes, until the cookie expires** | **none** | **cookie lifetime** |
| C | Playwright with persisted login | yes | Playwright + Chromium | heavy; login challenges in CI |
| D | Manual weekly capture in-browser | no | none | needs you every week |

### A — Fix the OAuth grant

**Revised after `0d93e14`.** This was first written as "worth one check, because if it works it
costs minutes." That is no longer accurate, and the correction matters enough to state plainly:
**Yahoo reviews every application for Fantasy Sports API access.** The 403 is therefore usually a
*pending approval*, not a setting to toggle — so the honest cost is "submit and wait, with no
committed timeline and no guarantee of approval," not minutes.

Two things remain true and worth doing anyway, because they are free:

- If an application has already been submitted and approved, the consent flow must be re-run.
  A refresh token issued *before* approval keeps its original grant and will keep returning 403
  forever. This is the one case where the fix really is minutes.
- `game/nba` touches no league and 403s in this state too, which distinguishes a permission
  problem from a malformed league key.

This revision is why the browser path is not a workaround for a misconfiguration. It is the only
acquisition path available while approval is pending, and the only one at all if approval never
comes. Option A and this feature should proceed in parallel rather than as alternatives — an
approved application later turns Option B off with a configuration change (spec FR-016).

### B — Browser-minted cookie + `httpx` — recommended

Log in once in your own browser, copy one authenticated request as cURL, store its `Cookie`
header as a secret. The scheduled job then uses the `httpx` client that is already a
dependency. **No browser runs in CI** — the browser's only job is minting the credential.

This fits the constitution rather than straining against it:

- Principle V **names cookies explicitly** as a runtime secret supplied by the environment or
  a secret store. Cookie auth is anticipated here, not a workaround.
- "Dependency restraint" requires a new runtime dependency to be justified against a named
  requirement. Option B adds none. Option C adds a browser engine to satisfy a step that
  happens once, locally.
- The fetch layer stays isolated behind the existing seam.

**The cost, stated plainly:** a Yahoo web session cookie expires on a timescale of days to
weeks, where an OAuth refresh token lasts indefinitely. That collides with the constitution's
requirement that the weekly trigger "MUST require no interactive input or local developer
machine." It does not block the approach, but it converts a fully unattended job into one
with a recurring manual re-mint, and accepting that is your call.

The failure mode is at least safe rather than destructive: Principle II means a dead cookie
fails the run, publishes nothing, leaves the good page up, and notifies. So the cost is
noise and a stale page, not a broken one. Two things make it tolerable:

- `tools/curl_to_env.py --check` verifies a freshly captured cookie authenticates *outside*
  the browser, so re-minting is a 30-second loop with immediate confirmation.
- A dead session answers with a `302` to login, not an error status. The provider must treat
  that redirect as a hard failure, or a login page gets parsed as league data. The `--check`
  helper already detects exactly this case.

### C — Playwright with persisted login

Real browser, `storage_state` saved after one interactive login and replayed. Genuinely more
robust against JS-rendered pages and bot heuristics. But it adds a browser engine to CI to
solve a problem that only exists during the once-per-session login, and the stored state
expires on the same clock as Option B's cookie — so it pays the dependency cost without
removing the recurring re-mint. Reach for it only if discovery shows the data is unreachable
without executing page JavaScript.

### D — Manual weekly capture

A console snippet or bookmarklet dumps the league JSON while you are on the page; you drop
the file in `data/` and the pipeline runs from it. Immune to every auth problem above, and
the archive-replay path that makes this work already exists and is tested. It gives up
unattended operation, which is a stated project goal — reasonable as a stopgap to get a page
published this week, not as the destination.

## Before any provider code: six facts

Two of these can kill a surface outright, and discovering either one in week 3 wastes the
work in between. `tools/yahoo_web_discovery.js` collects all six in one DevTools session.

1. **FG and FT as `18/42`, not `.458`.** Contract requirement 2 calls this unrecoverable if
   lost — a rounded percentage cannot be re-aggregated. If the surface only renders
   percentages it is dead regardless of how good it looks otherwise. **Check this first:** it
   is the cheapest fact that invalidates the most work.

   The tool grades this in two tiers rather than as a yes/no, because it is both the most
   decisive fact and the easiest to get a false positive on: a bare `d/d` scan also matches
   dates, win-loss records, and fractions in copy. `CONFIRMED` means the value was found
   inside a stat object — the `{stat_id, value}` shape `yahoo.py:parse_team_stats` actually
   reads. `UNVERIFIED` means the pattern exists somewhere but not in that shape, and the
   printed samples need your eye before the surface is trusted.
2. **All 18 teams reachable in one acquisition pass**, not only your own matchup. Requirement 1,
   and the contract names it "the first thing to verify against any new provider." Note this is
   about *coverage*, not request count — "one response" was the API's shape, and a page-based
   surface needing nine matchup fetches satisfies it just as well.
3. **`week=N` addressable.** Requirement 6. Without it, FR-038 backfill and the
   `RECHECK_WEEKS=3` correction window both break — two features that are already built.
4. **JSON before HTML.** Filter the Network tab to Fetch/XHR first. If the page hydrates from
   an internal JSON endpoint, that is a far more stable parse target than markup.
5. **Which cookies are actually required**, so the stored secret stays as small as possible.
6. **Which User-Agent the request needs.** `config.USER_AGENT` is the descriptive
   `ccsv-rumble/0.1 (…)` the contract asks for, but a session-cookie request may be rejected
   unless it matches the browser that minted the cookie. If so, that is a real conflict with
   the contract's "descriptive User-Agent on every request" line and should be recorded as a
   Constitution exception rather than quietly changed.

## Procedure

```bash
# 1. Discovery — in the browser, on your league page
#    Paste tools/yahoo_web_discovery.js into the DevTools console, then click
#    Scoreboard → a past week → the league Stats tab.
__ccsv.report()      # everything captured, scored against the requirements
__ccsv.best()        # the strongest candidate and which requirements it meets
__ccsv.probe(3)      # confirm a past week is addressable
__ccsv.save()        # download payloads for offline parser work

# 2. Capture the session — DevTools → Network → right-click a league request
#    → Copy → Copy as cURL
#    Point --check-url at the endpoint step 1 identified: a cookie that
#    authenticates a page navigation does not prove the JSON endpoint you will
#    actually build against accepts it.
pbpaste | uv run python tools/curl_to_env.py --check-url '<__ccsv.best() url>'

# 3. Keep it out of the repo
#    Writes credentials.local.sh, mode 600, matched by the credentials*.sh
#    ignore rule. Cookie values are never printed.
source credentials.local.sh
```

The saved discovery bundle contains real team and manager names. It carries no cookies — JS
cannot read Yahoo's HttpOnly auth cookies, which is why capture goes through cURL — but it
still does not belong in the repository.

## Terms

This reads one league you are a member of, from your own account, at a handful of paced
requests per week. The bounded-retry and `HTTP_PACING_SECONDS` rules the constitution already
imposes keep it well-behaved; nothing here scrapes at volume or touches data you cannot
already see in a browser.

## Discovery verdicts — to be recorded

Phase 0 of the spec's integration plan is complete only when this table is filled in from a live
session. G1 and G2 are blocking: if either fails, the fallback in the spec's Assumptions applies and
no provider is written.

| Gate | Question | Verdict | Evidence |
|---|---|---|---|
| **G1** | Shooting as makes and attempts, not a percentage? | **player: CONFIRMED. team: deferred** | run 4 — no team view is populated until a matchup completes |
| **G2** | All 18 teams in one acquisition pass? | *reachable — 9 matchup views* | run 3 — 2 teams per view, 9 views covers 18 |
| G3 | Historical weeks addressable? | *testable now* | prior season exists on Yahoo |
| G4 | Structured response, or markup only? | **markup only** | run 1 — nothing is fetched |
| G5 | Minimum credential set | *unrecorded* | |
| G6 | Request identity required | *unrecorded* | |

**League state** (confirmed by the maintainer, 2026-10-21): the league ran last season on Yahoo, this
season's draft has completed, and the first games have been played. So rosters exist, the current
week carries partial totals, and a prior season is available — every gate is now testable.

### Run 1 — 2026-10-21, XHR recorder on the league page

Only `https://server.comet.yahoo.com/comet` was captured, and all gates scored NO against it. That
is Yahoo's long-poll push channel, which carries messaging and never league data; it ranked top
purely because it streams continuously. It is now filtered as noise.

**The informative part is the absence.** No league JSON was requested at all, so the page does not
fetch its data and an XHR interceptor cannot find it by construction. Two surfaces remain, in the
order worth trying: inlined page state in a `<script>` tag (`__ccsv.inline()`), then rendered table
markup (`__ccsv.html()`). Both were added after this run.

**A second constraint surfaced with it**: the league has no completed weeks, so this season's
scoreboard holds no category totals to inspect. G1 and G2 are questions about the *shape* of a
shooting value, and an empty grid cannot answer them. They need either a week in which a game has
been played, or a prior season of the same league — which would settle G1, G2 and G3 together.
G3 is recorded as deferred rather than failed: the requirement stands, only its verification waits.

Meanwhile the **roster** surface does not depend on games played and is what `002` needs for a
week-0 page, so it is the one worth confirming first.

### Run 2 — 2026-10-21, markup scan on a team page

**G1 is confirmed, and it is the gate that could have killed the feature.** A table with
`FG%`/`FT%` headers carried both forms at once:

```
made/attempted: ["0/1","0/0","8/9","5/8","2/5","1/4"]
decimals:       [".000",".889",".625",".400",".250"]
```

Yahoo renders the makes-and-attempts pair *alongside* the percentage rather than instead of it, so
attempts are recoverable and FR-002 is satisfiable. The earlier worry — that the web surface would
expose only a rounded percentage, unrecoverably — does not hold.

**G2 is still open because this was the wrong page.** Thirteen rows with `Pos`, `Edit` and `Players`
headers is one team's roster, not the league grid. A roster cannot satisfy G2 regardless of how good
its cells look, since all-play needs every team in one response.

**Two tool defects this run exposed, both now fixed**, because each reported an absence that was an
artifact rather than a finding:

- `teams: 0` on a page plainly showing a team. The team count matched only the API key shape
  (`466.l.194131.t.5`), which never appears in web markup. It now also matches web team links.
- `looseSamples: []` on a page whose cells visibly read `8/9`. The pattern required JSON quoting
  (`"8/9"`); markup values carry none. It now matches the `>8/9<` form too.

Both mattered: an artifact that looks like evidence is how a usable surface gets discarded. The
table-aware check added before this run is what caught G1 at all — the raw-markup scan still
reported `shooting: ABSENT` on the very page that confirmed it.

`html()` now also counts distinct team links per table and flags a grid candidate, so a league grid
is distinguishable from a single roster without reading headers by eye.

### Run 3 — 2026-10-21, markup scan on the matchup view

The nine-category grid is there, with the right headers — `FG%, FT%, 3PTM, PTS, REB, AST, ST, BLK,
TO` — but **every shooting cell is a decimal**: `.609`, `.625`, `.553`, `.636`, and
`made/attempted` was empty in all three tables. Player rows on this view are decimals too.

So G1 does not hold uniformly. It depends on the view:

| View | Granularity | Shooting form |
|---|---|---|
| Roster / team page (run 2) | per player | **`8/9` and `.889`** |
| Matchup page (run 3) | per team, 2 teams | `.609` only |

G2 also looks unmet by this view: the per-table count was `teams=2`, one matchup rather than the
league. The document-level `teams: 18` / `allTeams: true` is **an artifact of the fix made after run
2** — Yahoo's navigation links every team in the league, so the whole-document count reads 18 on a
single-matchup page. The tool now says so in its output. Two artifacts in two runs, in opposite
directions, is the recurring hazard of inferring structure from a text scan.

**What this leaves.** Team-level makes and attempts have not been found yet, and FR-002 needs them
at team level, because FG% for a 9-category week is the team's aggregate ratio and a rounded
per-team percentage cannot be re-aggregated. Three possibilities remain, in descending preference:

1. **A team totals row on the weekly roster page.** If the roster view for team *T*, week *N* ends
   in a `Total` row reading `184/402`, team-level shooting is directly available — 18 requests per
   week, authoritative, no inference. `html()` now detects and prints exactly this row, which it did
   not do during run 2, so run 2's page may already have carried one unnoticed. **Check this first.**
2. **The league Stats tab**, which may present team totals in made/attempted form.
3. **Reconstruction from player rows, verified against the displayed percentage.** Previously
   rejected as liable to diverge on mid-week lineup and injured-reserve changes. That objection is
   weaker than it looked, because Yahoo's own displayed team percentage is a **checksum**: if
   `sum(FGM) / sum(FGA)` over the week's roster does not equal the displayed `.609`, the
   reconstruction is wrong and the run can fail loudly instead of publishing a quiet error. That
   turns a guess into a verified derivation and is worth reconsidering before falling back to
   manual capture.

### Run 4 — 2026-10-21, roster page and league Stats tab

Both candidates for a direct team-level figure came back negative, and the reason is the same for
each: **no team-level view is populated until a matchup completes.**

- **No totals row on the roster page.** The row reported was page chrome — "Subscribe now",
  "Research Assistant", "Sit/start suggestions" — because Yahoo lays out parts of the page with
  tables and the check was taking the last row by position. It now searches for a row *labelled*
  `Total` and drops rows whose cells are prose. Verified against both a real totals row and this
  exact chrome row.
- **The league Stats tab is all zeros**, and per the maintainer it only updates when a matchup
  completes.

The team's record reads `0-0-0`, which confirms it: week 1 is in progress and nothing has been
scored yet. So the team-level half of G1 is **not currently answerable** — not refuted. The
distinction matters, and it is the third time in this investigation that an unanswerable gate could
have been misread as a failed one.

**What is settled:** per-player makes and attempts are available live, mid-week, on the roster page.
That is the input reconstruction needs, and it exists now.

**What to re-check when week 1 completes:** the league Stats tab and the matchup view, for a
team-level `184/402`. This is a two-minute check and it decides between option 1/2 and option 3
above. Until then no further discovery is possible on the weekly grid, because the data does not
yet exist.

**What this unblocks regardless:** rosters are reachable and parseable now, which is Phase 0a and
what `002` needs for a projection-based week-0 page. The grid half of this feature is calendar-bound;
the roster half is not.

### The league Stats tab is eliminated outright

Per the maintainer: it has **no weekly breakdown** at all. It carries season-to-date totals, so it
cannot serve a per-week grid regardless of when it is read. That is a structural exclusion, not a
"wait for data" — option 2 above is dead, not deferred.

## Recommended design — hybrid, reconstruct only the two categories that need it

With a direct team-level weekly figure unavailable, the remaining path is derivation. It is narrower
than "reconstruct the grid", because seven of the nine categories need no reconstruction at all:

| Category group | Source | Reconstruction? |
|---|---|---|
| `PTS REB AST ST BLK TO 3PTM` | team totals on the matchup view | **none** — read directly |
| `FG% FT%` | summed from per-player `FGM/FGA` on roster views | yes, **and checksummed** |

Only the two ratio categories are derived, and each derivation has an independent verification: the
matchup view's displayed `.609` must equal `sum(FGM)/sum(FGA)` from the roster rows. A mismatch means
the derivation is wrong — a stale lineup read, a bench slot counted, an injured-reserve edge case —
and the run fails loudly under Principle II rather than publishing a plausible wrong number.

This is what makes the approach acceptable where a bare reconstruction was not. The earlier
objection — divergence on mid-week lineup and injured-reserve changes — is not waved away; it is
made *detectable*. The failure mode moves from "quietly wrong ranking" to "loud failure, good page
stays up", which is exactly where the constitution requires ambiguity to resolve.

**Known subtlety the checksum guards.** Only players in active slots count toward a team's weekly
total, so the parser must respect the roster page's position column rather than summing every row.
In a daily-lineup league a player may be active for some games and benched for others in the same
week. The checksum is what turns that from an unquantifiable risk into a test.

**Request cost per week**: 9 matchup views (team totals for the seven counting categories, plus the
two percentages used as checksums) + 18 roster views (per-player makes and attempts) = **27 paced
requests**. At the pacing already configured that is well under a minute, and a backfill multiplies
it by the number of weeks recovered — within the resilience rules, but worth noting as the cost of
this surface versus a single API call.

**One confirmation still needed**, testable once week 1 completes: that a roster view with a
*completed* week selected still reports per-player makes and attempts for that week. Live mid-week
data is confirmed; historical per-week roster data is the thing backfill and the correction window
depend on, and it is the same question as G3 for this surface.

Record the chosen endpoint, the `__ccsv.best()` verdict verbatim, and — for G1 — the confirmed
samples, since a graded `UNVERIFIED` is not a pass. If G6 shows the session is only honored for a
browser-like request identity, note it explicitly: that conflicts with the data-source contract's
"descriptive User-Agent on every request" line and needs recording as a deviation rather than a
quiet change.
