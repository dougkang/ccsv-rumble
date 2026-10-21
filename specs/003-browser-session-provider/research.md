# Research — Browser-Session Data Source

**Feature**: [`003-browser-session-provider`](spec.md)

**Status**: Options assessed and a recommendation made. The discovery gates G1–G6 in the spec are
unresolved — record their verdicts here once the maintainer has run discovery against the live
league.

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
2. **All 18 teams in one response**, not only your own matchup. Requirement 1, and the
   contract names it "the first thing to verify against any new provider."
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
| **G1** | Shooting as makes and attempts, not a percentage? | *unrecorded* | |
| **G2** | All 18 teams in one response? | *unrecorded* | |
| G3 | Historical weeks addressable? | *unrecorded* | |
| G4 | Structured response, or markup only? | *unrecorded* | |
| G5 | Minimum credential set | *unrecorded* | |
| G6 | Request identity required | *unrecorded* | |

Record the chosen endpoint, the `__ccsv.best()` verdict verbatim, and — for G1 — the confirmed
samples, since a graded `UNVERIFIED` is not a pass. If G6 shows the session is only honored for a
browser-like request identity, note it explicitly: that conflicts with the data-source contract's
"descriptive User-Agent on every request" line and needs recording as a deviation rather than a
quiet change.
