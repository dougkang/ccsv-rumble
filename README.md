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
uv run pytest                              # 121 tests, all offline
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

   **The app must be granted Fantasy Sports → Read, and Yahoo reviews every
   application for that access.** So this is usually a *pending approval*, not a
   setting to toggle — if an application has been submitted, the answer is to wait for
   it. Do not go hunting through the app settings for a switch; there isn't one.

   It does not look like a permission problem either way: every fantasy endpoint
   returns `403 Forbidden` with *"This application is not authorized to perform this
   action"* — including `game/nba`, which involves no league at all. The token refresh
   still succeeds with `200 OK`, so auth appears healthy right up until the first real
   request.

   Two tells that the permission is missing: the token response carries no `scope`
   field and no `xoauth_yahoo_guid`.

   **Approval does not upgrade existing tokens.** Once the application is approved,
   re-run the consent flow to mint a *new* refresh token; a token issued before
   approval keeps its original (empty) grant forever and will keep returning 403.

   Because approval has no committed timeline, acquisition via a browser session is
   specified as the path that does not depend on it — see
   [`specs/003-browser-session-provider/`](specs/003-browser-session-provider/spec.md).

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

### Optional: `data/projections.csv`

Only used for the cold-start weeks, before enough games have been played for results to
carry the ranking. Format:

```csv
player_id,value
nba.p.1234,2.41
```

`value` is a per-game 9-category z-score total from any source you have rights to.
The file is gitignored.

**When it is absent**, week 1 publishes with a **provisional** badge and a note saying a
single week moves the numbers a long way. The ranking is still computed — by week 1 there
are real results, and 153 category comparisons per team is not nothing — but the page says
plainly that it is thin. Before any games are played there is no page at all, because
there is nothing to rank.

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

## Development

```bash
uv run pytest                                        # full suite
uv run ruff check src/ tests/                        # lint
uv run ccsv-rumble dry-run --from-archive --week 4   # pre-merge gate
```

Changing a ranking constant in `config.py` means bumping `ALGORITHM_VERSION` and
attaching a before/after rank comparison on archived weeks to the PR. Replay the
affected weeks under both sets of constants and diff the result.
