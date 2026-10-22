---

description: "Task list for Draft Ranking (Week 0)"
---

# Tasks: Draft Ranking (Week 0)

**Input**: Design documents from `specs/002-draft-ranking-week-0/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **Included, and not optional here.** The constitution's Development Workflow section makes
them mandatory for exactly the surfaces this feature touches: *"Ranking logic MUST have unit tests
over fixture data, including ties and incomplete data"*, *"Rendering MUST have a golden-file test"*,
*"The failure path MUST be tested"*, and *"Replay from an archived snapshot MUST be tested"*. Four of
those four apply.

**Organization**: grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete work)
- **[Story]**: US1–US4, mapping to the spec's user stories
- Exact file paths are given in every task

## Path Conventions

Single project: `src/ccsv_rumble/`, `tests/` at repository root. The existing five-stage separation is
preserved — acquisition in `fetch/`+`archive/`, pure computation in `rank/`, presentation in
`report/`+`render/`, side effects in `publish/`+`notify/`.

---

## Phase 1: Setup

**Purpose**: declared constants and shared fixtures. The project is already initialized — there is no
scaffolding to create, so this phase is deliberately small.

- [X] T001 Add declared constants to `src/ccsv_rumble/config.py`: `DRAFT_ALGORITHM_VERSION = "draft-v1"`, `DRAFT_SHRINK = 0.6`, `ACTIVE_SLOTS = ("G","G","FC","FC","FC","UTIL")`, `BENCH_SLOTS = 4`, `IL_SLOTS = 2`, `DRAFT_ROSTER_SIZE = 10`, `MAX_ROSTER_SIZE = 12`, `DRAFT_MIN_TEAM_COVERAGE = 0.80`, `DRAFT_MIN_LEAGUE_COVERAGE = 0.95`. Reuse `EMW_WEIGHT`/`CAW_WEIGHT` — do NOT redeclare them (research D8)
- [X] T002 [P] Create valid projection fixture `tests/fixtures/projections-valid.csv` with columns `player_id,name,positions,projected_games,pts,reb,ast,stl,blk,tpm,to,fgm,fga,ftm,fta` per `contracts/projection-source.md`, covering 18 teams × 10 players, names as placeholders only
- [X] T003 [P] Create rejection fixture `tests/fixtures/projections-percent-only.csv` carrying `fg_pct`/`ft_pct` columns instead of makes and attempts
- [X] T004 [P] Create sparse fixture `tests/fixtures/projections-sparse-team.csv` where one team can fill only 4 of its 6 active slots
- [X] T005 [P] Create sparse fixture `tests/fixtures/projections-sparse-league.csv` where every team can fill only 5 of 6 active slots (passes per-team 0.833, fails league-wide)
- [X] T006 [P] Create post-draft roster fixture in `tests/conftest.py` with 18 teams × **10** players and **IL empty**, per research D7

**Checkpoint**: constants declared, fixtures available to every later phase.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: lifecycle gate, projection acquisition, archiving, and the purity fix. Every user story's
run path passes through these.

**⚠️ CRITICAL**: no user story work can begin until this phase completes.

### Model additions

- [X] T007 [P] Add `positions: tuple[str, ...] = ()` to `PlayerSlot` in `src/ccsv_rumble/models.py` — raw eligibility, defaulted empty so existing fixtures keep working
- [X] T008 [P] Add `PerGameLine` (FLOAT fields — `CategoryLine` is `int` and truncates `8.6` FGM to `8`) and `PlayerProjection` to `src/ccsv_rumble/models.py` with `player_id: str`, `name: str`, `per_game: PerGameLine`, `projected_games: int`; validation `projected_games >= 0` here, makes/attempts and non-negativity on `PerGameLine`
- [X] T009 [P] Add `ProjectionSnapshot` to `src/ccsv_rumble/models.py` with `source_id: str`, `retrieved_at: datetime`, `target_week: int`, `projections: tuple[PlayerProjection, ...]`, `raw_source: str`
- [X] T010 [P] Add `DraftPick` and `DraftResults` to `src/ccsv_rumble/models.py`; `DraftResults` carries `season: str`, `picks: tuple[DraftPick, ...]`, `is_complete: bool`; `DraftPick` carries `pick_number: int`, `team_id: TeamId`, `player_id: str`, `player_name: str`
- [X] T011 [P] Add `LifecycleState(StrEnum)` to `src/ccsv_rumble/models.py` with members `PRE_DRAFT`, `POST_DRAFT`, `IN_SEASON`, and a companion `LifecycleVerdict` carrying `state` plus `reason: str` — FR-008 requires the reason, and a bare enum cannot distinguish "no rosters" from "two teams drafted short"
- [X] T012 Add `draft_algorithm_version: str = ""` to `Ranking` in `src/ccsv_rumble/models.py` (FR-033 — a rank depending on two algorithms cannot be traced by citing one)
- [X] T013 Add `draft_score: float | None`, `emw_proj: float | None`, `caw_proj: float | None`, `unprojected_count: int = 0` to `RankingEntry` in `src/ccsv_rumble/models.py` — all internal, and confirm `PublishableReport` still has no field able to hold any of them

### Lifecycle gate

- [X] T014 Implement `classify()` in new `src/ccsv_rumble/lifecycle.py` as a **pure** function of the snapshot: `PRE_DRAFT` when any team holds fewer than `DRAFT_ROSTER_SIZE` players or no rosters exist; `POST_DRAFT` when all 18 rosters are at 10+ and zero scored weeks have completed; `IN_SEASON` when at least one scored week has completed. Check completed-scored-weeks FIRST so a mid-season roster dip below 10 classifies as `IN_SEASON`, not pre-draft (research D7)
- [X] T015 Add a completed-scored-weeks count to `Snapshot` in `src/ccsv_rumble/models.py`, populated by acquisition — the pure layer must not infer it, and deriving it from the date would be wrong because a week in progress looks finished to a clock
- [X] T016 [P] Unit-test lifecycle in `tests/unit/test_lifecycle.py`: no rosters → `PRE_DRAFT`; two teams at 9 → `PRE_DRAFT` with a reason naming the count; all at 10 with IL empty → **`POST_DRAFT`**; one scored week complete → `IN_SEASON`; mid-season dip to 9 → `IN_SEASON`
- [X] T017 [P] Add the guard test from quickstart 1a to `tests/unit/test_lifecycle.py`: a fixture built from real post-draft sizes (10 players, IL empty) MUST classify as `POST_DRAFT`. Assert the test fails when `DRAFT_ROSTER_SIZE` is 12 — a test passing at both 10 and 12 proves nothing, and the failure it guards publishes nothing while exiting zero and never notifying

### Projection acquisition

- [X] T018 Define `ProjectionProvider` Protocol and `ProjectionError` in new `src/ccsv_rumble/fetch/projection_provider.py`, mirroring `fetch/provider.py`: raw out, normalization separate and pure (FR-015)
- [X] T019 Implement a local-file provider in new `src/ccsv_rumble/fetch/projections.py` reading the declared schema from `contracts/projection-source.md`, returning raw rows plus a `source_id()`
- [X] T020 Implement validation in `src/ccsv_rumble/fetch/projections.py` that raises `ProjectionError` on: a `fg_pct`/`ft_pct`/`fg%`/`ft%` column present instead of makes and attempts; `fga < fgm` or `fta < ftm`; a missing `projected_games` column; any negative value. **Never infer, derive, or default attempts** (FR-010) — `.458` is consistent with `11/24` and `22/48`, which aggregate differently
- [X] T021 Implement normalization in `src/ccsv_rumble/fetch/normalize.py` from raw rows to `ProjectionSnapshot`, recording `source_id` and `retrieved_at` (FR-011)
- [X] T022 [P] Unit-test ingest in `tests/unit/test_projection_ingest.py`: the percent-only fixture raises with a message naming the missing makes-and-attempts columns; `fga < fgm` raises; missing `projected_games` raises; the valid fixture normalizes with `source_id` and `retrieved_at` set

### Archiving

- [X] T023 Extend `src/ccsv_rumble/archive/store.py` to write and read a projection snapshot at `data/<season>/week-NN/entry-NNN/projections.json`, plus the verbatim pre-parse input at `raw-projections.csv` (Principle III)
- [X] T024 Extend `src/ccsv_rumble/archive/store.py` to write and read draft results at `data/<season>/week-NN/entry-NNN/draft-results.json`
- [X] T025 Route an unparseable projection input to `_quarantine/` via the existing `quarantine_raw()` in `src/ccsv_rumble/archive/store.py` rather than creating an incomplete entry
- [X] T026 [P] Unit-test archiving round-trip in `tests/unit/test_projection_archive.py`: snapshot writes and reads back identically; a corrected snapshot appends `entry-002` rather than overwriting `entry-001` (FR-013)

### Purity fix

- [X] T027 Remove filesystem access from `src/ccsv_rumble/rank/prior.py`: delete `load_player_values()` and its `csv`/`pathlib` imports; `roster_prior()` receives already-parsed values. Principle I requires this package be "free of I/O, network, and filesystem access"
- [X] T028 Move the call site in `src/ccsv_rumble/pipeline.py` so projections are loaded during acquisition and passed into ranking, replacing `load_player_values(projections_path)` at the rank step
- [X] T029 Widen `tests/unit/test_architecture.py` to fail on filesystem and network access inside `rank/`, `render/`, `report/` — AST check for `open`, `Path` I/O methods, and network modules, not only forbidden internal imports. The existing check inspects the import graph against internal package names, so `csv` and `pathlib` passed unnoticed
- [X] T030 Confirm the widened test **fails against the pre-T027 `prior.py`** and passes after. A test green on both versions is not testing anything

### Pipeline gate

- [X] T031 Wire the lifecycle gate into `src/ccsv_rumble/pipeline.py`: `PRE_DRAFT` publishes nothing, exits zero, and sends **no** notification (FR-003, FR-004); the reason is logged every run (FR-008)
- [X] T032 Add a persistence log line in `src/ccsv_rumble/pipeline.py` noting how long a `PRE_DRAFT` classification has held — normal in October, suspicious in December — without a notification, which would undo FR-004
- [X] T033 [P] Integration-test the quiet path in `tests/integration/test_pre_draft_publishes_nothing.py`: exit 0, nothing rendered, no notification, reason recorded. **Also assert the inverse** — a genuine acquisition failure still exits non-zero and notifies. If both paths go quiet the gate is wrong

**Checkpoint**: the gate decides correctly, projections are acquired and archived, ranking is pure, and the architecture test enforces it. User stories can begin.

---

## Phase 3: User Story 1 — Week-0 ranking table (Priority: P1) 🎯 MVP

**Goal**: a member opens the page between draft completion and the first scored games and sees all 18
teams ordered, labelled as projection-based.

**Independent Test**: run against a post-draft snapshot with no completed scored weeks; confirm 18
teams in rank order, the projection label, movement shown as unavailable, no figure from the
computation, and **no model involved at any point**.

### Projected grid

- [X] T034 [US1] Implement `eligible_for(slot, positions)` in new `src/ccsv_rumble/rank/projected.py`: `UTIL` accepts anyone; `G` accepts `{PG, SG, G}`; `FC` accepts `{SF, PF, C, F}`; an empty `positions` tuple is eligible for `UTIL` only (data-model.md)
- [X] T035 [US1] Implement slot filling in `src/ccsv_rumble/rank/projected.py`: iterate `ACTIVE_SLOTS` in declared order `G,G,FC,FC,FC,UTIL` (narrowest eligibility first), each slot taking the best **eligible** unassigned player by projected scalar value, ties by `(value desc, player_id asc)`. Filling `UTIL` first would be strictly worse — it could consume the best guard and leave a `G` slot unfillable (research D4)
- [X] T036 [US1] Exclude players with `projected_games == 0` from contributors entirely in `src/ccsv_rumble/rank/projected.py`, rather than contributing zeros (FR-023) — a zero-game player would otherwise drag ratio categories toward a false floor
- [X] T037 [US1] Accumulate `per_game × projected_games` into **float** accumulators in `src/ccsv_rumble/rank/projected.py` and round **once** at the end into a `CategoryLine`. Never round per player — that biases totals by up to half a unit per contributor (data-model.md)
- [X] T038 [US1] Make unfilled active slots contribute nothing in `src/ccsv_rumble/rank/projected.py` — not a league average, not a replacement level (FR-024)
- [X] T039 [US1] Count rostered players with no projection per team in `src/ccsv_rumble/rank/projected.py` and return it alongside the grid (FR-025), keeping it distinct from slot coverage
- [X] T040 [P] [US1] Unit-test the grid in `tests/unit/test_projected_grid.py`: dual-eligible player placement under the declared slot order; zero-game exclusion; single rounding at the end; unfilled slots contributing nothing; unprojected counts; a team whose players have no `positions` fills `UTIL` only

### Draft score

- [X] T041 [US1] Implement `draft_score()` in new `src/ccsv_rumble/rank/draft_score.py` running the **existing** all-play grid over the projected totals and applying `0.5 + DRAFT_SHRINK * (AllPlay_proj - 0.5)`, where `AllPlay_proj = EMW_WEIGHT * EMW_proj + CAW_WEIGHT * CAW_proj`. Reuse the in-season comparison — FR-019 forbids a second scoring function
- [X] T042 [US1] Route a team with zero attempts in a ratio category into the in-season algorithm's existing zero-attempt rule in `src/ccsv_rumble/rank/allplay.py` rather than adding a new one (FR-027), which is why the grid produces a `CategoryLine`
- [X] T043 [US1] Break ties deterministically in `src/ccsv_rumble/rank/draft_score.py` by `(score desc, team_id asc)`, matching the in-season stable sort (FR-022)
- [X] T044 [P] [US1] Unit-test scoring in `tests/unit/test_draft_score.py` including the design document's **worked example**: a team whose point projections sweep five categories scores `AllPlay_proj ≈ .895` unshrunk and must land at `≈ .737` after shrink — **below** a proven dominant team at `.804`. This makes the constant's justification executable rather than prose
- [X] T045 [P] [US1] Unit-test ties and incomplete data in `tests/unit/test_draft_score.py` per the constitution's explicit requirement

### Coverage refusal

- [X] T046 [US1] Implement coverage checks in `src/ccsv_rumble/rank/projected.py` over **active slots fillable**: per team against `DRAFT_MIN_TEAM_COVERAGE` (0.80 → at most one unfillable slot of six) and league-wide against `DRAFT_MIN_LEAGUE_COVERAGE` (0.95 of 108). Coverage is NOT the FR-025 unprojected count — a team with six projected starters and four unprojected bench players has full coverage (research D5)
- [X] T047 [US1] Refuse to publish below either floor in `src/ccsv_rumble/pipeline.py`: publish nothing, leave the previous page untouched, exit non-zero, notify (FR-026, FR-038)
- [X] T048 [P] [US1] Integration-test both floors separately in `tests/integration/test_coverage_threshold_refuses.py`: one team at 4/6 (per-team binds); every team at 5/6 (league-wide binds at 0.833 < 0.95). Assert the **boundary** — a single team at 5/6 must PASS. Also assert a team with four unprojected bench players still publishes

### Report and page

- [X] T049 [US1] Populate `draft_score`, `emw_proj`, `caw_proj`, `unprojected_count` on `RankingEntry` in `src/ccsv_rumble/report/internal.py` so a maintainer can explain any placement from the report alone (FR-034, SC-010)
- [X] T050 [US1] Record both declared versions on `Ranking` in `src/ccsv_rumble/report/internal.py` — `ALGORITHM_VERSION` and `DRAFT_ALGORITHM_VERSION` (FR-001, FR-033)
- [X] T051 [US1] Emit both versions into the page's provenance comment in `src/ccsv_rumble/render/html.py` — permitted because a provenance comment is not a ranking-derived figure
- [X] T052 [US1] Render rank movement as **unavailable, not zero**, for the first ranking of a season in `src/ccsv_rumble/render/html.py` (FR-006) — zero asserts "unchanged", a different and false claim
- [X] T053 [US1] Add the projection label in `src/ccsv_rumble/render/html.py` stating the ranking reflects draft projections rather than played games, **without describing the mechanism** by which projections give way to results (FR-030)
- [X] T054 [US1] Publish the unprojected count as **prose only**, never a table figure, in `src/ccsv_rumble/render/html.py` (research D6 — it is an input-coverage fact, so FR-028 does not reach it)
- [X] T055 [US1] Extend the disclosure screen in `src/ccsv_rumble/render/validate.py` to reject `draft_score`, `emw_proj`, `caw_proj` and the shrink constant in any form — figures, rounded values, alt text, tooltips, data attributes, markup comments (FR-029)
- [X] T056 [US1] Review new draft vocabulary against `DISCLOSURE_TERMS` in `src/ccsv_rumble/config.py` and add any term that would disclose the method (FR-031)
- [X] T057 [P] [US1] Integration-test the page in `tests/integration/test_week0_page.py`: 18 teams in rank order; movement unavailable; projection label present; both versions in provenance; **no model call made**
- [X] T058 [P] [US1] Golden-file test for the week-0 page in `tests/golden/week-00.html` asserting byte-identical rendering for a fixed snapshot, per the constitution's rendering requirement

**Checkpoint**: User Story 1 is complete and independently shippable. This is the MVP — a week-0 page with no article.

---

## Phase 4: User Story 2 — Draft recap article (Priority: P2)

**Goal**: one league-wide article covering how the draft went, published with the week-0 rankings.

**Independent Test**: generate from an archived week-0 internal report plus archived draft results;
confirm it references concrete draft facts, names no forbidden method vocabulary, and passes the tone
screen — all without publishing.

- [ ] T059 [US2] Add `fetch_draft_results(season)` to the `LeagueDataProvider` Protocol in `src/ccsv_rumble/fetch/provider.py` — this is league data, from the same provider as rosters, so it extends the existing seam rather than adding one
- [ ] T060 [US2] Implement draft-results acquisition and normalization in new `src/ccsv_rumble/fetch/draft.py`, setting `is_complete` true **only** when every pick of a finished draft is present — a partial board is treated as unavailable (FR-049)
- [ ] T061 [US2] Build the recap prompt in `src/ccsv_rumble/article/prompt.py` from the week-0 internal report **plus** archived draft results only (FR-043), with the report fully determined before any prose is generated
- [ ] T062 [US2] Steer the prompt in `src/ccsv_rumble/article/prompt.py` toward the roster and the picks as subject, never the manager — the genuinely funny draft story is usually someone's mistake and the audience is a congregation that includes that person (FR-046)
- [ ] T063 [US2] In `src/ccsv_rumble/article/prompt.py`, give the prompt the decomposition as context for what is **true** while instructing that the mechanism is unpublishable (FR-045) — a recap is more accurate if it explains the ranking, and strict disclosure forbids that
- [ ] T064 [US2] Enforce exactly one league-wide article in `src/ccsv_rumble/article/generate.py`, not one per team (FR-041)
- [ ] T065 [US2] Screen the article against `DISCLOSURE_TERMS` and `DISALLOWED_TONE_TERMS` in `src/ccsv_rumble/article/validate.py` before publication (FR-045, FR-046)
- [ ] T066 [US2] Archive the generated article and replay it on subsequent runs in `src/ccsv_rumble/pipeline.py`, making no new model call on a repeat run (FR-044)
- [ ] T067 [US2] On article failure or a failed screen, publish the page with the complete ranking table and **omit the article section entirely** — no placeholder, no explanation — and notify, in `src/ccsv_rumble/pipeline.py` (FR-048)
- [ ] T068 [US2] On draft results unavailable or incomplete, publish the ranking and omit the article in `src/ccsv_rumble/pipeline.py`, rather than generating a recap from rosters alone (FR-049)
- [ ] T069 [P] [US2] Integration-test the recap in `tests/integration/test_draft_recap.py`: single league-wide piece; references a concrete pick/team/player for a majority of the 18 teams (SC-005); repeat run makes no model call; failure still publishes complete rankings and notifies
- [ ] T070 [P] [US2] Unit-test the screens in `tests/unit/test_recap_screens.py`: method vocabulary rejected; language disparaging an identifiable member rejected; humour aimed at a pick permitted

**Checkpoint**: week 0 publishes with a recap, and degrades to rankings-only on any article failure.

---

## Phase 5: User Story 3 — Rankings react to roster change (Priority: P3)

**Goal**: an injury or lopsided trade shows up in the next published ranking rather than waiting for
weeks of results.

**Independent Test**: two in-season snapshots differing only by one team losing its highest-projected
player; the affected team ranks no higher in the second.

- [ ] T071 [US3] Recompute the roster prior from **current** rosters on every in-season run in `src/ccsv_rumble/pipeline.py`, never reusing the draft-night value (FR-035) — otherwise the only forward-looking term in the in-season ranking is frozen at draft night
- [ ] T072 [US3] Consume the prior as the forward-looking term using the blend already declared by the in-season algorithm in `src/ccsv_rumble/rank/score.py`, with no second definition of roster strength (FR-036)
- [ ] T073 [US3] Switch the headline ranking to the in-season algorithm in `src/ccsv_rumble/pipeline.py` once at least one scored week has completed, with the draft score continuing only as the prior (FR-007)
- [ ] T074 [P] [US3] Unit-test prior responsiveness in `tests/unit/test_roster_prior_reacts.py`: two snapshots differing only by one team losing its highest-projected player; that team ranks no higher in the second and nothing else moves for any other reason
- [ ] T075 [P] [US3] Unit-test in `tests/unit/test_roster_prior_reacts.py` that the prior is recomputed rather than read from the draft-week archive entry

**Checkpoint**: the prior is live all season and reacts to roster churn.

---

## Phase 6: User Story 4 — Maintainer reproduces a past draft ranking (Priority: P4)

**Goal**: a disputed ranking can be re-run offline weeks later and produce the identical ordering.

**Independent Test**: replay an archived post-draft snapshot with no network and confirm the ordering
and rendered page match what was published.

- [ ] T076 [US4] Make replay read projections from the **archived snapshot** rather than the live file in `src/ccsv_rumble/cli.py`, so a source revision cannot change a past result (FR-013)
- [ ] T077 [US4] Confirm `replay --week 0` and `verify --week 0 --against PATH` work without a new mode in `src/ccsv_rumble/cli.py` — week 0 uses the same entry structure as any other week
- [ ] T078 [P] [US4] Integration-test replay in `tests/integration/test_week0_replay.py`: replay twice, **edit `data/projections.csv` between runs**, and assert byte-identical output both times. Assert the archived snapshot path is the one opened — this currently fails, and it is the regression test for the defect FR-011/FR-012 exist to close
- [ ] T079 [P] [US4] Integration-test in `tests/integration/test_week0_replay.py` that replay invokes no nondeterministic stage, per the constitution's explicit replay requirement

**Checkpoint**: every published week-0 page is reproducible from its archive.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T080 [P] Update the `data/projections.csv` section of `README.md` to the new nine-category schema — the documented `player_id,value` format is now **rejected at ingest**, and leaving it would send the next reader to a format the code refuses
- [X] T081 [P] Add the new constants and their rationale to the configuration notes in `README.md`, including that `DRAFT_ROSTER_SIZE` excludes IL and why
- [ ] T082 [P] Change the status line of `docs/draft-rankings-algorithm-v1.md` from "proposed design, not yet implemented" to implemented, and resolve its Open Questions that this feature settled (slot-filling rule, tier decision)
- [ ] T083 [P] Record in `docs/draft-rankings-algorithm-v1.md` §6 that the 1–18 ordering was adopted over tiers, per research D11
- [ ] T084 Run the full `quickstart.md` validation sequence end to end and record any divergence
- [ ] T085 Confirm the pre-merge gates pass: `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run ccsv-rumble dry-run --from-archive --week 0`
- [ ] T086 Review the golden-file diff for `tests/golden/week-00.html` as intentional, per the pre-merge gate that an unexplained rendering diff blocks merge

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: depends on Foundational. No dependency on other stories
- **US2 (Phase 4)**: depends on Foundational and on US1's internal report existing (FR-043 derives the article from it)
- **US3 (Phase 5)**: depends on Foundational and on US1's `draft_score` (the prior *is* the draft score recomputed)
- **US4 (Phase 6)**: depends on Foundational's archiving; verifies US1's output
- **Polish (Phase 7)**: depends on all desired stories

### Honest note on story independence

US1 is genuinely independent and shippable alone. US2, US3, and US4 are **not** fully independent of
US1, and the template's usual claim would be wrong here: the recap is derived from US1's report, the
prior is US1's score recomputed, and US4 verifies US1's page. That is a property of the feature rather
than a planning defect — the design document is explicit that `RosterPrior` *is* `DraftScore`, with no
second definition anywhere. Each remains independently *testable*, which is what the gates assert.

### Within each story

- Models before the pure functions that consume them
- Pure computation before report, report before render
- Acquisition before archiving before replay
- Tests for a surface alongside that surface, and the constitution requires the failure path and
  replay be tested rather than assumed

### Parallel opportunities

- T002–T006 (fixtures) all parallel
- T007–T011 (model additions) all parallel — different classes in one file, so coordinate the single
  edit or sequence them if the same file is contended
- T016, T017 parallel with each other once T014 lands
- T040, T044, T045 parallel
- T057, T058 parallel
- T069, T070 parallel
- T074, T075 parallel
- T078, T079 parallel
- T080–T083 (docs) all parallel

---

## Parallel Example: User Story 1

```bash
# Once the projected grid and scoring exist, these tests are independent:
Task: "Unit-test the grid in tests/unit/test_projected_grid.py"
Task: "Unit-test scoring incl. the worked example in tests/unit/test_draft_score.py"
Task: "Unit-test ties and incomplete data in tests/unit/test_draft_score.py"

# Page-level verification, also independent of each other:
Task: "Integration-test the page in tests/integration/test_week0_page.py"
Task: "Golden-file test in tests/golden/week-00.html"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup — constants and fixtures
2. Phase 2 Foundational — **the gate, ingest, archiving, purity fix.** Do not shortcut T017 or T030;
   each guards a failure that is silent by construction
3. Phase 3 US1 — the week-0 ranking table
4. **Stop and validate** against quickstart scenarios 1, 1a, 2, 3, 4, 6, 7, 8, 10
5. Ship. A rankings-only week-0 page is a complete page by FR-048's definition

### Incremental delivery

1. Setup + Foundational → the gate is correct and inputs are archived
2. US1 → **publishable week-0 page (MVP)**
3. US2 → recap added; page degrades to rankings-only on any failure
4. US3 → prior live all season, reacting to roster churn
5. US4 → reproducibility verified, closing the replay defect

### Sequencing note

US2 depends on league-data acquisition for draft results, which is the subject of
`004-browser-session-provider` and whose gates are unresolved. FR-049 was written so this does not
block: **US1 ships without it**, and the recap arrives when draft results can be read. Do not hold the
MVP for US2.

---

## Notes

- `[P]` tasks touch different files with no incomplete dependencies
- Commit after each task or logical group
- Every task above names a file path, per the required checklist format
- Two tasks exist specifically to prove a test can fail: **T030** (widened architecture test fails
  pre-fix) and **T017** (lifecycle test fails at `DRAFT_ROSTER_SIZE = 12`). A test that passes before
  and after the change it guards is not a test
- Changing `DRAFT_SHRINK`, the slot-filling rule, or either coverage threshold bumps
  `DRAFT_ALGORITHM_VERSION` and requires a before/after rank comparison over archived weeks (FR-037),
  because this algorithm affects in-season published ranks and not only the week-0 page
