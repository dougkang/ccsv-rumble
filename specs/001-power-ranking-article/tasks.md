# Tasks: Power Ranking Article Generator

**Input**: Design documents from `/specs/001-power-ranking-article/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Test tasks are included and are **not optional**. Constitution v2.0.0 § Development
Workflow & Quality Gates mandates specific tests by name: ranking unit tests over fixture data, a
golden-file render test, a tested failure path, and a replay test proving no nondeterministic stage
is invoked. Those four are constitutional requirements, not a chosen methodology.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3, mapping to spec.md user stories

## Path Conventions

Single project. `src/ccsv_rumble/`, `tests/`, `archive/` at repository root, per plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, dependencies, and the declared-constants module everything reads from

- [X] T001 Create the package tree `src/ccsv_rumble/{fetch,archive,rank,report,article,render}/` with `__init__.py` in each, plus `tests/{unit,integration,fixtures,golden}/`, per plan.md § Project Structure
- [X] T002 Add runtime dependencies `httpx`, `anthropic`, `jinja2` and dev dependency `pytest` to `pyproject.toml`; declare the `ccsv-rumble` console script entry point pointing at `ccsv_rumble.cli:main`
- [X] T003 [P] Configure `ruff` for lint and format in `pyproject.toml`, and add a `pytest` section setting `testpaths = ["tests"]`
- [X] T004 Create `src/ccsv_rumble/config.py` holding **every** declared constant in one module per constitution Principle I: `ALGORITHM_VERSION = "v1"`, `EMW_WEIGHT = 0.65`, `CAW_WEIGHT = 0.35`, `SHRINKAGE_K = 3`, `RECENCY_HALF_LIFE_WEEKS = 4`, `RECHECK_WEEKS = 3`, `LEAGUE_TIMEZONE`, `TEAM_COUNT = 18`, `CATEGORY_COUNT = 9`, `PAGE_WEIGHT_BUDGET_BYTES = 500_000`, the movement-significance threshold, and the standout-performance threshold. No constant may be written as a literal anywhere else in the codebase
- [X] T005 [P] Create `.github/workflows/weekly.yml` triggering on `schedule` (cron, Tuesday) and `workflow_dispatch` **only** — adding a `push` trigger would make the publish step retrigger the workflow indefinitely (research.md § Workflow self-trigger hazard). Grant `contents: write` so the built-in `GITHUB_TOKEN` can push to the `pages` branch
- [X] T006 [P] Add `data/projections.csv` to `.gitignore` and document the optional projections file in `README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Primitives every user story depends on — typed models, the append-only archive, the
Yahoo provider, week scheduling, and notifications

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Define all dataclasses in `src/ccsv_rumble/models.py` per data-model.md: `Snapshot`, `CategoryLine`, `Team`, `Matchup`, `PlayerSlot`, `Transaction`, `PlayerWeek`, `Ranking`, `RankingEntry`, `NotableEvent`, `InternalReport`, `PublishableReport`, `PublishableTeam`, `PublishableEvent`, `Article`, `ArticleContent`, `TeamNote`, `ValidationOutcome`, `PublishedPage`, and the `Movement` / `LuckBand` / `EventType` enums
- [X] T008 In `src/ccsv_rumble/models.py`, define `PublishableTeam` with **no** field capable of holding a ranking-derived number other than `rank`, `previous_rank`, and `rank_change` — `power_score`, `emw`, `caw`, `roster_prior`, `performance_weight`, `category_profile`, and `schedule_luck` must be absent. This is the type-level enforcement of FR-032 (plan.md Constitution Check)
- [X] T009 Add validators to `src/ccsv_rumble/models.py`: `Snapshot` requires `len(teams) == 18` and every team present in `category_totals`; `CategoryLine` requires `fgm <= fga`, `ftm <= fta`, and all values non-negative; `Ranking` requires ranks are exactly `1..18` with no gaps or duplicates; `RankingEntry.movement` is `UNAVAILABLE` if and only if `previous_rank is None`
- [X] T010 Implement the append-only store in `src/ccsv_rumble/archive/store.py` with numbered `entry-NNN` directories per week. Expose **two distinct accessors with no default**: `latest_entry(season, week)` and `entry(season, week, entry_id)`. Writing an `entry_id` that already exists must raise — the store creates, never overwrites (data-model.md § 1)
- [X] T011 [P] Implement `src/ccsv_rumble/archive/scrub.py` to redact credential-shaped values, invoked **on the write path** inside `store.py` so no call site can forget it (constitution Principle V)
- [X] T012 [P] Implement `src/ccsv_rumble/archive/diff.py` comparing a re-fetched week against its latest entry using **normalized** `CategoryLine` values, rosters, and transactions only — never raw bytes. Yahoo responses carry volatile per-request fields, so a byte comparison reports a correction every run and appends a junk entry each time (contracts/data-source.md)
- [X] T013 Define the `LeagueDataProvider` protocol in `src/ccsv_rumble/fetch/provider.py` with `fetch_week`, `fetch_stat_category_map`, `fetch_rosters`, `fetch_transactions`, each returning raw unnormalized provider data
- [X] T014 Implement OAuth2 refresh-token exchange in `src/ccsv_rumble/fetch/yahoo.py`, reading `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, and `YAHOO_REFRESH_TOKEN` from the environment and obtaining a short-lived access token per run. No credential may be read from argv
- [X] T015 Implement `fetch_stat_category_map` in `src/ccsv_rumble/fetch/yahoo.py` reading `GET /fantasy/v2/league/{key}/settings` → `stat_categories`, and **assert all nine expected categories resolve**, failing the run loudly if any is missing. Do not hardcode `stat_id` values — they are not authoritative and change between seasons (research.md § 1)
- [X] T016 Implement `fetch_week` in `src/ccsv_rumble/fetch/yahoo.py` via `GET /fantasy/v2/league/{key}/scoreboard;week={week}`, which returns `team_stats` for every matchup and so yields the full 18-team grid in one request
- [X] T017 Implement composite shooting-stat parsing in `src/ccsv_rumble/fetch/yahoo.py`: Yahoo returns FG and FT as a single `"made/attempted"` string (e.g. `stat_id` `9004003` = `FGM/FGA`), so split on `/` and coerce both halves to `int`. Handle the empty / `"-"` case (a team with no attempts) explicitly rather than letting it raise. A parser assuming numeric stat values fails on exactly the two categories whose data cannot be reconstructed later
- [X] T018 Add explicit per-call timeouts, a bounded retry count, and a descriptive User-Agent to `src/ccsv_rumble/fetch/yahoo.py`. Exhausted retries are a Principle II failure — report and publish nothing. Pace sequential requests so a long-outage backfill does not become a burst that Yahoo rate-limits
- [X] T019 Implement `src/ccsv_rumble/fetch/normalize.py` converting raw Yahoo payloads into `Snapshot` and `CategoryLine`, storing `fgm`/`fga`/`ftm`/`fta` separately and **never** storing a computed percentage
- [X] T020 Implement `src/ccsv_rumble/schedule.py` resolving the target week in `LEAGUE_TIMEZONE` (never the host's local time), detecting archived gaps (FR-037), and returning the correction window of the last `RECHECK_WEEKS` completed weeks (FR-045) as an ordered list of weeks to process
- [X] T021 Implement `src/ccsv_rumble/notify.py` opening or updating a GitHub issue via the Actions `GITHUB_TOKEN`, reporting article failures (FR-030), backfilled weeks (FR-043), and detected corrections (FR-050)
- [X] T022 [P] Create `tests/fixtures/yahoo_week.json` from a captured raw Yahoo response with team and manager names replaced by placeholders, so parser tests run offline and the real league's data is never committed to the test corpus (contracts/data-source.md § Fixture requirement)

**Checkpoint**: Primitives ready — user story implementation can begin

---

## Phase 3: User Story 1 — League member checks where their team stands (Priority: P1) 🎯 MVP

**Goal**: A published per-week page showing the 1–18 rankings, each team's movement, and a factual
notable-events list. No language model involved at any point.

**Independent test**: Run against a league snapshot with `ANTHROPIC_API_KEY` unset and confirm the
rendered page shows a complete 18-team ranking, movement versus the previous published ranking, and
a notable-events list — with no article section present.

### Ranking engine (pure — no imports from `fetch/`, `archive/`, or `publish`)

- [X] T023 [P] [US1] Implement category comparison in `src/ccsv_rumble/rank/allplay.py`: counting categories higher-wins; `to` inverted (lower wins); ratio categories compared as `made/attempted`. **Ties score 0.5 to each side.** Zero attempts in a ratio category is a **loss against any team with ≥1 attempt and a tie against another team with 0** — an explicit branch, not a division-by-zero guard (data-model.md § 2)
- [X] T024 [US1] Implement `caw()` in `src/ccsv_rumble/rank/allplay.py` scoring all 9 × 17 = 153 category comparisons per team per week
- [X] T025 [US1] Implement `emw()` in `src/ccsv_rumble/rank/allplay.py` replaying each team against all 17 opponents, awarding a simulated matchup win at **≥5 of 9** categories
- [X] T026 [US1] Implement recency weighting and shrinkage in `src/ccsv_rumble/rank/score.py`: week `w` of `n` weighted `0.5 ** ((n - w) / RECENCY_HALF_LIFE_WEEKS)`; `w = n / (n + SHRINKAGE_K)`; `Performance = EMW_WEIGHT * emw_rw + CAW_WEIGHT * caw_rw`; `PowerScore = w * Performance + (1 - w) * roster_prior`
- [X] T027 [US1] Implement deterministic ordering in `src/ccsv_rumble/rank/score.py` using a stable sort by `(-power_score, team_id)`. Never sort by dict insertion order. Round only at the display boundary — never mid-computation (research.md § 8)
- [X] T028 [P] [US1] Implement optional `RosterPrior` in `src/ccsv_rumble/rank/prior.py` reading `data/projections.csv` when present. When the file is absent, publish **no ranking** until week 2 and show standings only, per the algorithm doc § 4
- [X] T029 [P] [US1] Implement movement classification in `src/ccsv_rumble/rank/significance.py` labelling each team `SIGNIFICANT`, `WITHIN_NOISE`, or `UNAVAILABLE` against the declared threshold in `config.py` (FR-006)
- [X] T030 [P] [US1] Implement notable-event derivation in `src/ccsv_rumble/rank/events.py` for injury/availability changes, trades, adds, and drops, with `event_id` **deterministically derived from `(week, type, subject)` — never a UUID**, since a changing id breaks the golden-file test and the article's attribution round-trip (data-model.md § 4)
- [X] T031 [US1] Implement standout-performance detection in `src/ccsv_rumble/rank/events.py` by a declared rule: a rostered player's week qualifies when output exceeds their own season-to-date baseline by the `config.py` threshold in at least one category, subject to a minimum games-played floor (FR-009)
- [X] T032 [US1] Implement schedule luck in `src/ccsv_rumble/rank/score.py` as `actual_win_pct - emw`, plus the qualitative `luck_band` mapping that is the only publishable form (FR-033)

### Reports

- [X] T033 [US1] Implement `src/ccsv_rumble/report/internal.py` producing `InternalReport` with full component detail plus the exact `constants` used, for the before/after comparison the constitution requires on algorithm changes
- [X] T034 [US1] Implement `src/ccsv_rumble/report/publishable.py` producing `PublishableReport` carrying rank, movement, significance, record, `luck_band`, qualitative `category_notes`, and events — and **no numeric ranking metric** (FR-014, FR-032)

### Render and publish

- [X] T035 [P] [US1] Create `src/ccsv_rumble/render/templates/page.html.j2` with semantic markup: one `<h1>`, ordered headings, a real `<table>` with `<th scope>` for the rankings, landmark elements, and `<meta name="robots" content="noindex, nofollow, noarchive">` (FR-051, constitution Principle IV)
- [X] T036 [P] [US1] Create `src/ccsv_rumble/render/templates/style.css` meeting a 4.5:1 contrast ratio and readable from 320px upward with no horizontal scrolling of the page body. Inline or local only — no third-party font, script, or stylesheet fetched at page load
- [X] T037 [P] [US1] Create `src/ccsv_rumble/render/templates/robots.txt` containing `User-agent: *` / `Disallow: /` (FR-051)
- [X] T038 [US1] Implement `src/ccsv_rumble/render/html.py` as a pure function rendering one week's page. Sort every iteration explicitly; accept `generated_at` as an explicit parameter — `render/` must never read a clock (research.md § 8)
- [X] T039 [US1] Record provenance in `src/ccsv_rumble/render/html.py` by emitting the `entry_id` and `algorithm_version` as a machine-readable HTML comment, so replay can resolve the exact snapshot entry a page was built from (FR-049, data-model.md § 9)
- [X] T040 [US1] Implement `src/ccsv_rumble/render/index.py` producing the current-week view plus a flat per-week link list, with every week addressable at a stable `/week-NN.html` that never changes once published (FR-040)
- [X] T041 [US1] Implement page validation in `src/ccsv_rumble/render/validate.py` asserting well-formed HTML, every expected section present, no empty-state placeholder where real data was expected, and **per-page** weight under `PAGE_WEIGHT_BUDGET_BYTES` (constitution Principle II, IV)
- [X] T042 [US1] Implement `src/ccsv_rumble/publish.py` to stage **all** weeks, diff against what is published, and push once — a single commit to the `pages` branch of the same repository using the Actions `GITHUB_TOKEN`. No stored PAT (research.md § Repository layout)
- [X] T043 [US1] Implement the no-op path in `src/ccsv_rumble/publish.py`: a run whose staged output is byte-identical to what is published makes **no commit** (constitution Principle II)

### Orchestration

- [X] T044 [US1] Implement the `run` and `dry-run` commands in `src/ccsv_rumble/cli.py` following plan.md § Run sequence, with `--week`, `--season`, `--from-archive`, `--no-backfill`, and `--recheck-weeks` per contracts/cli.md
- [X] T045 [US1] Implement correction handling in `src/ccsv_rumble/cli.py`: acquire the correction window **before any ranking is computed**, archive changed weeks as new entries (FR-046), use corrected data for current and future rankings (FR-047), and **never republish an already-published page** (FR-048). Correction and backfill must be separate code paths — collapsing "changed upstream" and "absent from archive" into one branch implements FR-038 and FR-048 as a contradiction
- [X] T046 [US1] Implement the backfill loop in `src/ccsv_rumble/cli.py` processing missing weeks in **ascending** order so each backfilled week's movement compares against the week immediately preceding it, not against the most recent published ranking (FR-039)
- [X] T047 [US1] Implement exit codes `0`–`5` in `src/ccsv_rumble/cli.py` per contracts/cli.md, where codes 1–4 all leave the previously published site live and untouched

### Tests for US1

- [X] T048 [P] [US1] Write `tests/unit/test_allplay.py` covering the 4-team, 3-category worked example from `docs/rankings-algorithm-v1.md` § 2 with its hand-computed values (D: CAW .667 / EMW 1.000; A: .556 / .667; B: .444 / .333; C: .333 / .000), plus category ties, a zero-FTA week, and TO inversion
- [X] T049 [P] [US1] Write `tests/unit/test_render_deterministic.py` rendering the same fixture snapshot twice in one process and again in a subprocess, comparing bytes — the golden-file test the constitution names as the enforcement mechanism for Principle I
- [X] T050 [P] [US1] Write `tests/unit/test_publishable_has_no_metrics.py` asserting `PublishableReport` exposes no field holding a ranking-derived number beyond rank and movement (FR-032, SC-010)
- [X] T051 [P] [US1] Write `tests/unit/test_architecture.py` asserting `rank/` and `render/` import nothing from `fetch/`, `archive/`, or `publish` — the import rule is what makes "pure function of the snapshot" architectural rather than conventional (plan.md § Structure Decision)
- [X] T052 [P] [US1] Write `tests/unit/test_yahoo_parse.py` against `tests/fixtures/yahoo_week.json` covering composite `FGM/FGA` splitting, the zero-attempt case, and a missing stat category failing loudly
- [X] T053 [P] [US1] Write `tests/unit/test_scrub.py` asserting credential-shaped values are redacted on the archive write path, and that `grep` over `archive/` finds no secret pattern (constitution Principle V)
- [X] T054 [US1] Write `tests/integration/test_noop_publish.py` running the same week twice and asserting the second run creates no commit
- [X] T055 [US1] Write `tests/integration/test_failure_paths.py` simulating a fetch failure and a report-validation failure, asserting neither pushes and the previously published site is untouched (constitution Quality Gates item 3)

**Checkpoint**: US1 is independently shippable — a working weekly rankings page with no LLM dependency

---

## Phase 4: User Story 2 — League member reads the weekly write-up (Priority: P2)

**Goal**: A short written article explaining the week, attributing plausible causes only for
significant movers, never disclosing the ranking method.

**Independent test**: Feed a fixed, hand-written report artifact to the article stage and confirm it
produces prose referencing only facts in that artifact, attributing causes only for significant
movers, and containing no formula, metric name, weight, or constant.

- [X] T056 [US2] Implement `generate_article(report: PublishableReport, client) -> Article` in `src/ccsv_rumble/article/generate.py` accepting **only** `PublishableReport`. `InternalReport` must not be importable from this package path (FR-015)
- [X] T057 [US2] Configure the Claude call in `src/ccsv_rumble/article/generate.py`: model `claude-opus-5`, adaptive thinking, `max_tokens=16000`, `output_config.format` set to the `json_schema` from contracts/article-io.md, and `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`
- [X] T058 [US2] Check `stop_reason` **before** reading `content` in `src/ccsv_rumble/article/generate.py` — a refusal returns HTTP 200 with possibly empty content, so indexing `content[0]` unconditionally crashes the run. A refusal is handled as an article failure, not a crash
- [X] T059 [US2] Write the system prompt in `src/ccsv_rumble/article/prompt.py` covering every constraint in the contracts/article-io.md requirements table: no method disclosure (FR-021), hedged causation (FR-018), no attribution for within-noise teams (FR-019), permission to say there is no clear driver (FR-020), no number absent from the report (FR-022), warm tone that never demeans (FR-023), people referenced only by team or manager display name (FR-024), and the week stated in **past tense** when it is not the current week (FR-041)
- [X] T060 [US2] Implement the pure `validate_article(content, report) -> ValidationOutcome` in `src/ccsv_rumble/article/validate.py` with all eight checks from contracts/article-io.md: `event_traceability`, `noise_attribution`, `team_coverage`, `no_disclosure`, `no_foreign_numbers`, `no_pii`, `tone`, `non_empty` (headline, intro, outro non-empty and `team_notes` covering all 18 teams)
- [X] T061 [US2] In `no_foreign_numbers` within `src/ccsv_rumble/article/validate.py`, **decompose `PublishableTeam.record`** (e.g. `"6-4"`) into its component values when building the set of permitted numbers, along with `rank`, `previous_rank`, `rank_change`, and any numeral inside an event `summary`. Prose will naturally read "at 6-4 they…" and a naive numerals scan would flag it — this false positive is guaranteed, not hypothetical
- [X] T062 [US2] Archive every generated article in `src/ccsv_rumble/cli.py` — **including rejected ones, with their failure list** — before render runs, so the article becomes part of the snapshot and replay can reuse it (FR-027, constitution Principle III)
- [X] T063 [US2] Implement silent omission in `src/ccsv_rumble/render/html.py`: when no article is published the page omits the article section **entirely** — no placeholder, no explanatory note, no carried-forward article from a prior week (FR-030a)
- [X] T064 [US2] Implement degraded publish in `src/ccsv_rumble/cli.py`: an article failure stages rankings-only for that week, exits `0`, and emits a notification. Per-week during backfill — one bad week does not abort the rest (FR-029, FR-044)
- [X] T065 [US2] Implement exit code `5` in `src/ccsv_rumble/cli.py` for a notification failure on a run that had something to report. With silent omission the page carries no signal, so an unreported event is invisible (FR-030b)
- [X] T066 [P] [US2] Write `tests/integration/test_article_rejection.py` feeding an `ArticleContent` containing a fabricated player and an attribution on a within-noise team, asserting both `event_traceability` and `noise_attribution` fail, the article is not published, and the rejected article **is** archived with its reasons
- [X] T067 [P] [US2] Write `tests/integration/test_article_failure_still_publishes.py` simulating the call raising, timing out, and returning `stop_reason: "refusal"` — asserting the rankings-only page publishes with exit `0` in all three cases, and that a notification failure in the same run instead exits `5`
- [X] T068 [US2] Write `tests/integration/test_backfill_multi_week.py` with weeks 1–2 archived, weeks 3–5 missing, and the article stage stubbed to fail on **week 4 only**. Assert ascending processing, that week 4's movement compares against **week 3** rather than week 2's published ranking, that week 4 stages rankings-only while 3 and 5 keep articles, and that **one** commit contains all three weeks plus the index. This exercises FR-039, FR-042, and FR-044 simultaneously — write it first if only one integration test gets written

**Checkpoint**: US2 complete — the page carries commentary, and every failure mode degrades rather than blocks

---

## Phase 5: User Story 3 — Maintainer audits a past week (Priority: P3)

**Goal**: Regenerate any past week from the archive offline and get byte-identical output,
including the article as it ran that week.

**Independent test**: Archive a run, regenerate from that archive with no network access, and
compare byte-for-byte against what was published.

- [X] T069 [US3] Implement the `replay` command in `src/ccsv_rumble/cli.py` reading the archived article and making no network or model call. Default to the entry recorded on the published page; add `--entry <id>` and `--latest`, documenting that `--latest` output is **not** expected to match what was published (contracts/cli.md)
- [X] T070 [US3] Implement the `verify` command in `src/ccsv_rumble/cli.py` resolving the published page's recorded `entry_id` and comparing byte-for-byte, with `--against <path>` for the offline form. `verify` takes no `--entry`/`--latest` — comparing a non-published entry against the published page is not a meaningful check
- [X] T071 [US3] Fail loudly in `src/ccsv_rumble/cli.py` when the archive for a requested week is incomplete, rather than silently falling back to a live fetch
- [X] T072 [P] [US3] Write `tests/integration/test_replay_offline.py` patching the socket layer and the Anthropic client to raise on construction, asserting replay still succeeds. This proves the Principle I regeneration rule and is the test most likely to rot — a stray import constructing a client at module load will fail it
- [X] T073 [P] [US3] Write `tests/integration/test_correction_forward_only.py` asserting a corrected week creates `entry-002` while `entry-001` is untouched, the next week's ranking uses corrected data, the published page is unchanged, `replay` reproduces the published page, `replay --latest` differs, and a re-fetch of an **unchanged** week creates **no** new entry

**Checkpoint**: All three user stories complete and independently verifiable

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T074 [P] Write `README.md` covering one-time setup: Yahoo OAuth consent to obtain a refresh token, the GitHub Actions secrets to create, and enabling Pages on the `pages` branch
- [X] T075 [P] Add run logging in `src/ccsv_rumble/cli.py` sufficient to answer after the fact whether the run ran, what it fetched, whether it published, and why not if it did not (constitution Observability)
- [X] T076 [P] Write `tests/unit/test_noindex.py` asserting every rendered page carries a `noindex` directive, `robots.txt` disallows all crawlers, and no sitemap is emitted (FR-051, FR-053, SC-011)
- [X] T077 [P] Write `tests/unit/test_accessibility.py` asserting one `<h1>` per page, no skipped heading levels, `<th scope>` on ranking tables, and landmark elements present
- [X] T078 Seed `tests/fixtures/archive/2026-27/` with a complete multi-week archive, then run `uv run ccsv-rumble dry-run --from-archive --week 4` against it and confirm it passes validation — the constitution's pre-merge gate 2
- [X] T079 [P] Document the algorithm-change procedure in `docs/rankings-algorithm-v1.md`: bump `ALGORITHM_VERSION`, replay archived weeks under old and new constants, and attach the rank comparison to the PR (constitution Principle I)
- [ ] T080 Enable HTTPS enforcement once GitHub provisions the certificate, and record the command plus its verification step in `README.md`: `gh api -X PUT repos/dougkang/ccsv-rumble/pages -F 'https_enforced=true'`

---

## Dependencies & Execution Order

```
Phase 1 Setup (T001–T006)
        ↓
Phase 2 Foundational (T007–T022)  ⚠️ BLOCKS everything below
        ↓
   ┌────┴─────────────────────────┐
   ↓                              ↓
Phase 3 US1 (T023–T055) 🎯 MVP    │
   ↓                              │
Phase 4 US2 (T056–T068) ──────────┘  depends on US1's PublishableReport
   ↓
Phase 5 US3 (T069–T073)  depends on US1 render + US2 archived article
   ↓
Phase 6 Polish (T074–T080)
```

**Story independence.** US1 is fully independent once Foundational is done and ships alone as the
MVP. US2 depends on US1 only through `PublishableReport`. US3 depends on both, since replaying a
page byte-identically requires that page and its archived article to exist.

**Within US1**, the ranking engine (T023–T032) and the templates (T035–T037) are independent tracks
that can proceed in parallel; both must land before render (T038) and publish (T042).

## Parallel Execution Examples

**Phase 2** — after T007 (models) lands, these touch separate files:
```
T011 scrub.py   T012 diff.py   T022 fixtures/yahoo_week.json
```

**Phase 3 US1** — two independent tracks after T023:
```
Track A (ranking):  T028 prior.py   T029 significance.py   T030 events.py
Track B (presentation): T035 page.html.j2   T036 style.css   T037 robots.txt
```

**US1 tests** — all independent files:
```
T048 test_allplay   T049 test_render_deterministic   T050 test_publishable_has_no_metrics
T051 test_architecture   T052 test_yahoo_parse   T053 test_scrub
```

**Phase 6** — T074, T075, T076, T077, T079 all touch separate files.

## Implementation Strategy

**Ship US1 alone first.** It is a complete, publishable weekly rankings page with no LLM
dependency, no API key, and no open-ended failure mode. Everything after it is commentary layered
on a working product — which is exactly why the spec prioritized it P1.

**Write T068 early.** The multi-week backfill test with a failing article in the middle exercises
FR-039, FR-042, and FR-044 at once, and its ordering assertion (week 4 compares against week 3) is
the subtlest requirement in the feature. Writing it before the backfill loop will shape the loop
correctly.

**Two traps worth re-reading before Phase 3.** Correction and backfill must be separate code paths
(T045), and correction detection must compare normalized data rather than raw bytes (T012). Both
are places where a reasonable implementation turns two requirements into a contradiction.

**Known blocker, outside the code.** HTTPS enforcement (T080) waits on GitHub provisioning a
certificate for `dgkng.io`. Generation, archiving, and publishing all work regardless; only secure
public access is gated.
