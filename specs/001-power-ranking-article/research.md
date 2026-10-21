# Phase 0 Research — Power Ranking Article Generator

Resolves every `NEEDS CLARIFICATION` in the Technical Context plus the four constitution TODOs.

---

## 1. Data source — `TODO(DATA_SOURCE)`

**Decision: Yahoo Fantasy Sports API v2.**

**Rationale.** The league is on Yahoo, and Yahoo is also the best of the three candidates on the
one axis that matters: the all-play algorithm needs per-week, per-category totals for **all 18
teams**, not just the user's own matchup.

- `GET /fantasy/v2/league/{league_key}/scoreboard;week={week}` returns matchups for the week, each
  with both teams as sub-resources, **and includes `team_stats` by default** — so one request per
  week yields the complete 18-team grid.
- `GET /fantasy/v2/team/{team_key}/stats;type=week;week={week}` is the per-team fallback if the
  scoreboard shape disappoints.
- Historical weeks are addressable by `week={n}`, so **backfill is possible** — unlike the
  mid-season ESPN scenario flagged in the algorithm doc. This materially de-risks the project.
- It is an officially documented, supported API with OAuth 2.0, rather than a reverse-engineered
  endpoint with no SLA.

**Critical finding — FG and FT come back as combined strings, not numbers.** Yahoo returns stats
keyed by `stat_id`, and the shooting categories are *composite*: `9004003` is `FGM/FGA` and
`9007006` is `FTM/FTA`, delivered as a `"made/attempted"` value. This is good news for the
algorithm doc's §6 requirement (makes and attempts, never percentages — Yahoo gives us exactly
that) but it means the parser must **split the composite field**, not read a numeric. A parser that
assumes numeric stat values will fail on precisely the two categories that cannot be reconstructed
later.

**`stat_id` values must be resolved at runtime, not hardcoded.** The specific IDs above are from
community sources and are not authoritative. `GET /league/{key}/settings` returns the league's own
`stat_categories` with IDs, names, and which are enabled. The fetch layer MUST read the mapping
from the league and assert that all nine expected categories are present, failing loudly if not.
Hardcoding IDs is how this breaks silently in a future season.

**Alternatives considered.** *ESPN* — the v3 API (`mMatchupScore` / `mBoxscore` views) does expose
the grid, but it is undocumented with no support commitment, and private leagues need
`SWID`/`espn_s2` cookie auth. *Sleeper* — public and auth-free, but NBA support is newer than their
NFL product and the weekly category grid would need verification first.

**Auth.** OAuth 2.0 with a refresh token. The refresh token is the stored secret; access tokens are
short-lived and fetched per run. This is a one-time interactive consent to obtain the refresh token,
then fully unattended — consistent with the constitution's no-interactive-input rule.

**Terms compliance.** The constitution requires access to comply with the provider's terms. Usage
here is one authenticated league owner reading their own league's data, roughly 20 requests per
week — well within normal use. Fetches must set a descriptive User-Agent and respect rate limits.

---

## 2. Scheduler — `TODO(SCHEDULER)`, and the Claude-scheduler question

**Decision: GitHub Actions scheduled workflow.** The Claude scheduler is a real option and the
question was a good one, so here is the actual comparison rather than a flat answer.

Two Claude-side mechanisms could run this:

- **Managed Agents scheduled deployments** — `POST /v1/deployments` with
  `schedule: {type: "cron", expression, timezone}` plus `initial_events`. Anthropic runs the agent
  loop and hosts a per-session sandbox; each firing creates a session, writes a `deployment_run`
  record, and can notify by webhook. It supports mounting a GitHub repo and injecting secrets via
  vault credentials, so it genuinely could run this end to end.
- **Scheduled cloud agents (routines)** — the same idea from the Claude Code side.

**Why not, for this project specifically:** the thing being scheduled is a deterministic script,
and this project's governing principle is determinism. A scheduled *agent* puts a model in the
orchestration path, where its job would be to invoke one command and not improvise. That is both a
waste of a capable model and a live risk against Principle II — an agent with bash access that
encounters a half-failed run may retry differently, edit a file, or work around the failure, which
is exactly the behavior "never publish a broken page" exists to prevent. A cron trigger cannot
improvise. Three secondary strikes: Managed Agents is beta; scheduled firings are **jittered by up
to 15% of the interval, capped at 9 minutes**, which is harmless weekly but is added variance for
nothing; and it is unavailable on Bedrock/Vertex/Foundry if the project ever moves.

**The Claude scheduler is the right tool when the scheduled work needs judgment.** Here exactly one
step needs judgment — writing the article — and that is a single `messages.create` call, not an
agent loop. So Claude is in the design, at the one place it earns its keep.

Worth revisiting if the scope grows toward work that genuinely needs an agent: investigating *why*
a fetch broke, adapting to a Yahoo schema change, or researching injury context beyond league data.

**GitHub Actions specifics.** `schedule: - cron: '0 16 * * 2'` (Tuesday, after Monday-night games
settle and Yahoo finalizes the week), with the timezone handled in code rather than relying on
cron's UTC. Cron must be paired with `workflow_dispatch` for manual runs. Note GitHub's documented
caveat that scheduled workflows can be delayed under load — harmless at weekly cadence, and the
job is idempotent per Principle II.

---

## 3. Alert channel — `TODO(ALERT_CHANNEL)`

**Decision: a GitHub issue in this repository, opened or updated by the failing workflow.**

**Rationale.** It satisfies Principle II's "configured channel, not only stdout or a log file" with
no new secret (the workflow's own `GITHUB_TOKEN` suffices), no SMTP dependency, and a durable
record that is hard to ignore and easy to close. Reusing one issue per failure mode avoids a pile
of duplicates on a repeated failure.

This also covers spec FR-030 — article-generation failures that still publish a rankings-only page
get recorded the same way, so silent degradation stays visible.

**Alternatives.** *Email* needs an SMTP or mail-API secret for no added reliability. *Nothing but
the red X on the Actions run* fails the Principle II requirement outright, since nobody is watching.

---

## 4. Article generation — model and call shape

**Decision: Claude via the Anthropic Python SDK, model `claude-opus-5`, with structured output.**

| Setting | Value | Why |
|---|---|---|
| Model | `claude-opus-5` | Current default Opus. The whole job is one short call a week, so cost is negligible and prose quality is the only axis that matters. |
| `output_config.format` | `json_schema` | **The key decision — see below.** |
| `thinking` | adaptive (on by default on this model) | Attributing causes across 18 teams is a reasoning task. |
| `max_tokens` | 16000 | Non-streaming ceiling guidance; the article is ~2–3K tokens but thinking shares the budget. |
| `fallbacks` | `"default"` (beta `server-side-fallback-2026-07-01`) | Opus 5's safety classifiers can decline a request and return `stop_reason: "refusal"`. Vanishingly unlikely for a basketball recap, but a refused run would otherwise degrade the page for no reason, and enabling it costs nothing. |

**Structured output is what makes validation possible.** Asking for prose and then checking it for
fabricated facts means parsing prose — unreliable. Instead the model returns a JSON object: an
intro, a per-team entry carrying `movement_note` plus `attributed_event_ids`, and an outro. Then
spec FR-022 traceability becomes a set-membership check (`attributed_event_ids ⊆ report event ids`)
and FR-019 becomes a lookup (no attribution permitted for teams flagged within-noise). Both are
mechanical, deterministic, and unit-testable. The prose still has to be scanned for leaked
internals and tone, but the factual claims most likely to be invented are structurally constrained.

**Not used, deliberately:** *prompt caching* — the style-guide system prompt is stable, but with one
call per week the 5-minute TTL has expired long before the next run, so a cache write would never
be read. *Managed Agents / Tool Runner* — no tools are needed; this is a single call. *Batches* —
nothing to batch.

**Note on the API surface:** assistant-turn prefill is rejected on this model, so forcing output
shape via a prefilled `{` is not available — `output_config.format` is the supported mechanism,
which is the route taken anyway.

---

## 5. Publish target — RESOLVED 2026-10-21

**Repository: `github.com/dougkang/ccsv-rumble`.** Pages will serve at
`https://dougkang.github.io/ccsv-rumble/`. Push with a fine-grained PAT scoped to that one
repository, stored as an Actions secret.

**State as found** (verified 2026-10-21): public, empty with no default branch, Pages not enabled,
description "CCSV Fantasy Basketball League Website". Three setup consequences:

- The first push must **create** the default branch; the publish stage cannot assume `main` exists.
- **Pages must be enabled** as a one-time setup step, pointing at the default branch root.
- The repo **description is public and names the league** — relevant to the open issue below.

### Open issue: the public repo defeats much of FR-051/052

FR-051 applies `noindex` to the Pages site. It does not and cannot cover
`github.com/dougkang/ccsv-rumble`, which is a **separate, public, crawlable page**. Once populated,
the rendered HTML containing manager display names is browsable and indexable on github.com no
matter what the Pages site says. The repo is effectively an un-noindexed mirror of the content.

On the **Free** plan this is structural: GitHub Pages requires a public repository. **GitHub Pro**
(~$4/mo) permits Pages from a *private* repository while the served site stays publicly readable —
which is exactly the desired shape. Login-gated Pages is **Enterprise Cloud only** and would also
break link-sharing for league members without GitHub accounts.

**FR-052 is additionally over-specified.** It requires the URL not be derivable from the league,
church, or any member's name. A personal-account Pages URL *always* contains the username, so
`dougkang.github.io/...` cannot satisfy it without a neutrally-named GitHub org or a custom domain.
As written, FR-052 is unsatisfiable on this hosting.

Three ways forward, pending the maintainer's decision:

| Option | Closes the repo-mirror gap | Satisfies FR-052 | Cost |
|---|---|---|---|
| Keep public repo; amend FR-051/052 to match reality | No | No | Free |
| GitHub Pro, repo private, same name | **Yes** | No (URL unchanged) | ~$4/mo |
| Pro + neutral org or custom domain | Yes | Yes | ~$4/mo + domain |

The substantive risk is "member names are searchable", and the public repo — not the URL string —
is the dominant exposure. Whichever is chosen, **FR-052 should be rewritten to state an achievable
requirement** rather than left as a permanently unmet one.

**Rationale.** Principle V requires the push credential be scoped to only the publish repository
and rotatable without code changes — a fine-grained PAT with `Contents: Read and write` on exactly
one repo satisfies both. `GITHUB_TOKEN` cannot be used because it is scoped to the *source*
repository.

**Still unrecorded:** the publish repository's name. This is a naming decision, not a technical
one, and blocks nothing until the publish stage is implemented. Carried forward as
`TODO(PUBLISH_TARGET)` with the auth mechanism now resolved.

**Deploy keys** were considered as an alternative — equally scoped, but rotation means touching repo
settings in two places rather than one secret.

---

## 6. Player projections for `RosterPrior`

**Decision: optional, file-based, and absent in the first implementation slice.**

The algorithm doc §4 needs per-player 9-cat z-score projections for the cold-start weeks, and names
Hashtag Basketball / Dribble Grid as candidate sources. Neither offers a licensed API, and scraping
a site to power a public page is both fragile and a terms question.

So: `RosterPrior` reads an **optional local CSV** (`data/projections.csv`) that can be populated
by hand or pasted from a source the user has rights to. When the file is absent, the rule from the
algorithm doc §4 applies directly — **publish no ranking until week 2 and show standings only** —
which is already the honest behavior for a league that has not drafted. This converts a hard
external dependency into a graceful degradation and removes projections from the critical path.

---

## 7. Dependency justification

The constitution requires each runtime dependency be justified against a named requirement the
standard library cannot meet.

| Dependency | Requirement it meets | Why not stdlib |
|---|---|---|
| `httpx` | Yahoo REST calls with OAuth2 token refresh, explicit timeouts, connection reuse | `urllib.request` has no ergonomic timeout-per-phase or retry story; writing one is more code to test than the dependency is worth |
| `anthropic` | Article generation | Official SDK; hand-rolling the Messages API, structured outputs, and the fallbacks beta over raw HTTP is strictly worse |
| `Jinja2` | HTML templating with autoescaping | `string.Template` has no loops or conditionals; `str.format` on HTML invites injection and is unreadable at page scale |

`pytest` is dev-only and does not count against the runtime budget. **No `pydantic`** — dataclasses
plus a hand-written validator cover the schema needs here, and keeping the count at three leaves
the restraint rule meaningful.

**Explicitly rejected:** a Yahoo API wrapper library (`yahoo_fantasy_api`, `yfpy`). They are
convenient, but the fetch layer must be isolated behind our own provider interface anyway
(constitution: "the fetch layer MUST be isolated behind an interface so the provider can be
replaced"), and these wrappers return loosely-typed nested dicts that still need normalizing. The
raw calls are few enough that the wrapper mostly adds an unmaintained layer between us and a schema
we must understand regardless.

---

## 8. Determinism mechanics

Concrete answers to the edge cases the algorithm doc §7 flagged, since each is a place output could
vary run to run:

| Case | Decision |
|---|---|
| Category tie | 0.5 to each side, in both EMW and CAW |
| PowerScore tie | Stable sort by `(-power_score, team_id)` |
| Zero attempts in a ratio category | Loss against any team with ≥1 attempt; tie against another team with 0. Explicit branch, not a division-by-zero guard |
| Float rounding | Full precision throughout; round only in the Jinja filter at render |
| Dict iteration | Every serialization sorts keys; every loop over teams sorts by `team_id` |
| `generated_at` | Injected as an explicit parameter from the CLI layer; `render/` never reads a clock |
| Unplayed / bye weeks | Excluded from all-play, never counted as zeros |

The golden-file test is the enforcement mechanism: it renders a fixture snapshot twice in one
process and across processes, and compares bytes.

---

## 9. Decisions from the 2026-10-20 clarification round

Three values the new requirements left as "declared constants" without saying what they are.

**Correction re-check window (`RECHECK_WEEKS`) = 3.** FR-045 requires a bounded window. Fantasy
stat corrections land within days of the games, so three weeks is generous, and the cost is three
extra scoreboard calls per run regardless of season length. The accepted tradeoff — recorded as an
edge case in the spec — is that a correction to a week older than three weeks is never detected;
by then it cannot move recency-weighted current rankings meaningfully.

**Per-week page addressing: `/week-NN.html`, with `/index.html` as the current-week view.** Flat,
sortable, guessable *within* the site, and stable forever — a week's URL never changes once
published, which is what FR-040 and FR-049 need. Rejected: a date-based path (the league week, not
the calendar, is the unit) and a slug-per-week scheme (nothing to slug, and it would break the
stable-address guarantee if a week were relabeled).

**Publish repository naming (FR-052).** The name must not derive from the league, church, or any
member's name. The recommendation is a neutral two-word name unrelated to the project's subject,
with the GitHub Pages URL inheriting it. Note the constraint is on *derivability*, not entropy — a
name that is merely unusual but still references the church fails the requirement, while a bland
unrelated name satisfies it. The specific name remains `TODO(PUBLISH_TARGET)`, now constrained.

### Alternative reconsidered and still rejected

The clarifications made the job meaningfully bigger — multi-week backfill loops, correction
detection, per-week pages — which is the kind of growth that would justify revisiting the
**Claude scheduler** decision from §2. It still does not apply: every added responsibility is
deterministic bookkeeping (compare two normalized structures, iterate weeks in order, buffer and
push once), which is exactly what code does better than an agent. The §2 revisit trigger stands
unchanged — it would take work needing *judgment*, such as diagnosing why a fetch broke or adapting
to a Yahoo schema change.

## Sources

- [Yahoo Fantasy Sports API Documentation](https://sports.yahoo.com/developer/docs/) — OAuth 2.0 flow, league/team/scoreboard resources
- [Yahoo scoreboard & team stats resources](https://y-fantasy-node-docs.vercel.app/resource/team/stats) — `scoreboard;week=`, `stats;type=week;week=` shapes
- [Scoring categories in Fantasy Basketball — Yahoo Help](https://help.yahoo.com/kb/SLN6928.html) — category abbreviations incl. FGM/FGA
- [Yahoo Fantasy Basketball Data Project](https://medium.com/@seansportsstats/yahoo-fantasy-basketball-data-project-a94246d509cc) — composite `stat_id` behavior (`9004003` FGM/FGA, `9007006` FTM/FTA); community source, verify against league settings
- [yahoo_fantasy_api docs](https://yahoo-fantasy-api.readthedocs.io/en/latest/yahoo_fantasy_api.html) — `League.matchups(week)`, `League.settings()`, `League.stat_categories()` as a shape reference
- [ESPN Fantasy API v3 notes](https://stmorse.github.io/journal/espn-fantasy-v3.html) and [Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API) — the rejected alternative; no official docs or SLA
- [Hashtag Basketball](https://hashtagbasketball.com/fantasy-basketball-rankings) / [Dribble Grid](https://www.dribblegrid.com/) — candidate `RosterPrior` z-score inputs, no licensed API
