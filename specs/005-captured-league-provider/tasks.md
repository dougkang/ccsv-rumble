---

description: "Task list for Captured-Data League Provider"
---

# Tasks: Captured-Data League Provider

**Input**: Design documents from `specs/005-captured-league-provider/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **Included, and not optional.** The constitution's Development Workflow requires tests
for the failure path and for replay from an archived snapshot, and this feature changes both. It
also changes what the ranking is *given* (R13), so the ranking tests over fixture data must cover
the new history rule.

**Organization**: Tasks are grouped by user story. Phase 2 holds three source-agnostic fixes that
every story needs: week 0 history, the calendar, and the acquisition seam.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete work)
- **[Story]**: US1–US3, mapping to the spec's user stories
- Exact file paths are given in every task

## Path Conventions

Single project: `src/ccsv_rumble/`, `tests/`, `tools/` at the repository root. Acquisition stays in
`fetch/` and `archive/`. The pure packages `rank/`, `render/` and `report/` are **not modified**,
and `tests/unit/test_architecture.py` must stay green.

---

## Phase 1: Setup

**Purpose**: shared fixtures. The project is initialized and needs no new dependencies (plan,
Technical Context).

- [X] T001 [P] Create `tests/fixtures/matchups-week1.csv` in the new 22-column format (contracts/matchups-capture.md). Take the 18 rows of the committed `data/matchups.csv` and add `captured_at=2026-10-26T09:00:00-07:00`, `week_start=2026-10-20`, `week_end=2026-10-25`. These rows already pass the FR-008 checksum (research R2)
- [X] T002 [P] Add a `write_matchups_csv(path, rows, *, captured_at, week_start, week_end)` helper to `tests/conftest.py`, next to `write_rosters_csv`, so defect tests can build files by editing row dicts. Add a `capture_rosters_csv` fixture that writes a roster file whose team ids are exactly `t.01`–`t.18`, matching T001

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: three changes every story depends on. None of them depends on the capture source.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Week 0 is not a played week (FR-019–FR-022, research R13)

- [X] T003 Write a failing integration test in `tests/integration/test_week1_after_week0.py`. Archive a real week 0 entry, by running the week 0 path as `test_week0_page.py` does, then publish week 1 via `FakeProvider`/`fake_snapshot_builder` (`tests/integration/conftest.py`). Assert all four:
  - (a) week 1's ranking equals `build_ranking([week1_snapshot], ...)`, with `completed == 1` and `performance_weight == 0.25`;
  - (b) week 1's movement is computed against the ranks stored in week 0's `publishable.json`;
  - (c) the week 1 page's projection/provisional labels match a history of one played week;
  - (d) `ccsv-rumble replay --week 1` produces the same page (FR-022).
- [X] T004 In `src/ccsv_rumble/pipeline.py`, add `_played(history) -> list[Snapshot]`, returning the snapshots with `week > 0`. In `build_week_page`:
  - pass `_played(history)` to `build_ranking`;
  - compute `is_projection`/`is_provisional` from `len(_played(history)) <= 1`, not `len(history)`.

  `derive_events(current, ...)` receives the prior *played* weeks. Do not modify `rank/score.py`.
- [X] T005 In `src/ccsv_rumble/pipeline.py`, change `execute`'s carry-forward branch, the `if week not in publish_weeks:` block that calls `build_ranking(history, ...)`. For week 0, set `previous_ranks` from the archived week 0 entry's published ranking: add `ArchiveStore.read_publishable_ranks(season, week, entry_id) -> dict[TeamId, int]` in `src/ccsv_rumble/archive/store.py`, built on the existing `read_publishable_raw`. If week 0 has no `publishable.json`, log a warning and set `previous_ranks = None`. For weeks > 0, keep `build_ranking(_played(history), ...)`
- [X] T006 In `src/ccsv_rumble/cli.py` `_render_archived`, apply the same `_played` history and week 0 previous-ranks rule, importing the helpers from `pipeline.py` rather than duplicating them, so replay matches a live run (FR-022). T003 must now pass, and the existing golden tests (`tests/golden/week-01.html`) must still pass. Their fixture has no week 0
- [X] T007 Record in `specs/005-captured-league-provider/research.md` R13, and in the eventual PR description, that `ALGORITHM_VERSION` stays `v1` and that the before/after comparison is empty because no week ≥ 1 has ever been archived

### League calendar (research R10)

- [X] T008 [P] Write failing tests in `tests/unit/test_schedule_calendar.py`:
  - `week_for_date(2026-10-20 … 2026-10-25) == 1`;
  - `2026-10-26 … 2026-11-01 == 2`;
  - `2026-11-02 == 3`;
  - `build_plan` with the clock at Monday 2026-10-26 09:00 PT targets `current_week == 1`;
  - `week_range(SEASON_START, 1) == (2026-10-20, 2026-10-25)` and `week_range(SEASON_START, 2) == (2026-10-26, 2026-11-01)`.

  The existing `tests/unit/test_schedule_week_zero.py` cases must still hold.
- [X] T009 In `src/ccsv_rumble/schedule.py`, reimplement `week_for_date(season_start, when)`. Week 1 runs from `season_start` through the first Sunday on or after it, and each later week runs Monday–Sunday. Add `week_range(season_start, week) -> tuple[date, date]` as its inverse. Update the docstrings to name the All-Star long week as a known break that the capture cross-check will surface (R10). T008 must pass

### Acquisition seam (research R1, R3, R4)

- [X] T010 [P] In `src/ccsv_rumble/fetch/provider.py`, add `class WeekNotCaptured(ProviderError)` with a `week: int` attribute. Its message must name the command `uv run python tools/chrome_capture.py matchups --week N` (R4)
- [X] T011 [P] In `src/ccsv_rumble/archive/store.py`:
  - add `EntryPaths.raw_matchups` returning `root / "raw-matchups.csv"`;
  - add `write_raw_text(paths, path, text)`, which writes verbatim after `scrub.scrub_text`;
  - add a `quarantine_text(season, week, acquired_at, text, suffix=".csv")` mirroring `quarantine_raw`.

  Add unit cases to `tests/unit/test_projection_archive.py`, or to a new `tests/unit/test_archive_raw_text.py`.
- [X] T012 In `src/ccsv_rumble/pipeline.py`, give `acquire_week` a keyword `build=None` parameter. When it is None, resolve the module-level `build_snapshot` **at call time**, so the existing `monkeypatch.setattr("ccsv_rumble.pipeline.build_snapshot", ...)` in `tests/integration/conftest.py` keeps working. Pass `existing` (the latest archived entry, or None) to `build` alongside the current arguments, so the capture builder can carry archived rosters forward (R5). Let the builder choose the raw write: Yahoo uses `write_raw`, capture uses `write_raw_text` with `raw_matchups`, and quarantine uses the matching method. Every existing test in `tests/integration/` must pass unchanged
- [X] T013 In `src/ccsv_rumble/pipeline.py` `execute`, accept `source: LeagueSource | None` in place of the bare `provider`. `LeagueSource` is a small frozen dataclass with `name`, `provider` and `build`, defined in `pipeline.py`. In the recheck loop only, catch `WeekNotCaptured`, log `week N not re-checked: not in capture`, and keep the archived entry. Everywhere else it propagates (R4). Update the existing `cli.py` call site to wrap `YahooProvider` with the Yahoo builder

**Checkpoint**: The week 0 fix, the calendar and the seam are in place. The full test suite is green, and the Yahoo path behaves as before.

---

## Phase 3: User Story 1 - Week 1 publishes from the committed capture (Priority: P1) 🎯 MVP

**Goal**: A complete post-week capture plus rosters publishes week 1 with no Yahoo credentials and
no API request.

**Independent Test**: With `YAHOO_*` unset, `dry-run --archive <scratch> --week 1 --no-article`
using `tests/fixtures/matchups-week1.csv` exits 0 and writes a week 1 page ranking 18 teams. A
second run creates no archive entry. Replay matches.

### Tests for User Story 1 ⚠️ write first, confirm they fail

- [X] T014 [P] [US1] Write `tests/unit/test_captured_load.py` (happy path). `captured.load_week(text, week=1, team_ids=..., tz=LEAGUE_TIMEZONE, calendar=week_range-bound callable)` on `tests/fixtures/matchups-week1.csv` returns a `WeekCapture` with 18 rows. The result has `week_start=2026-10-20`, `week_end=2026-10-25` and an aware `captured_at`. `raw_text` re-emits the header plus exactly week 1's rows
- [X] T015 [P] [US1] Write `tests/unit/test_capture_snapshot.py`. `build_capture_snapshot` maps per data-model.md "Mapping to Snapshot":
  - `teams` are sorted by id, use the week's `team_name`, and take managers from rosters, blank if unknown;
  - `category_totals` have `games_played=0`;
  - `matchups` are `Matchup(week, min(id, opp), max(id, opp))`, deduplicated and sorted (R7);
  - `stat_category_map == {}` and `raw_source == "matchups.csv"`;
  - `rosters` are the roster capture when `existing is None`, and **`existing.rosters` when an archived entry exists**, even if `rosters.csv` differs (R5).
- [X] T016 [P] [US1] Write `tests/integration/test_capture_no_credentials.py`. Unset `YAHOO_*` with `monkeypatch.delenv`, and monkeypatch `httpx.Client.send` to fail the test on any call. Run `cli.main(["dry-run", "--week", "1", "--no-article", "--matchups", <fixture>, "--rosters", <roster fixture>, "--archive", tmp, "--out", tmp])`. Expect exit 0, a log containing `league source: capture`, a week 1 page in the output directory, and `archive/.../week-01/entry-001/raw-matchups.csv` equal to the week's rows (FR-001, FR-004, FR-014)
- [X] T017 [P] [US1] Write `tests/integration/test_capture_idempotent_replay.py`. Run twice on the same capture: the second run creates no `entry-002` (FR-016, SC-004). Then delete the data files and run `replay --week 1`, which must match the first run's page byte for byte (FR-015, SC-003). Edit one team's `pts` and run again: `entry-002` is created with `supersedes=entry-001`, and a correction is reported
- [X] T018 [P] [US1] Write `tests/integration/test_capture_parity.py` (FR-017, research R12). Convert `tests/fixtures/yahoo_week.json` into an equivalent capture CSV inside the test, mapping Yahoo team keys to `t.NN`. Assert that the normalized snapshots (ids mapped; `rosters`, managers and `stat_category_map` dropped) have equal `category_totals`, `matchups` and team order. With **no projections**, assert the rendered page matches `tests/golden/week-01.html`

### Implementation for User Story 1

- [X] T019 [US1] Create `src/ccsv_rumble/fetch/captured.py`, in the style of `fetch/rosters.py`.
  - Add frozen dataclasses `CaptureRow` and `WeekCapture` with the fields in data-model.md: "`captured_at` | aware datetime | required (FR-009); one value per week" and "`rows` | exactly `TEAM_COUNT` rows (FR-005)".
  - Add `load_week(text, *, week, team_ids, tz, calendar, rows_required=config.TEAM_COUNT)`. It parses with `csv.DictReader`, selects the week's rows, and raises `WeekNotCaptured` if there are none. For now, run validation steps 1, 2 and 4 from data-model.md "Validation order"; US2 adds the rest.
  - `raw_text` is the original header line plus the week's original lines, unchanged.
- [X] T020 [US1] In `src/ccsv_rumble/fetch/captured.py`, add `build_capture_snapshot(*, entry_id, acquired_at, season, week, capture: WeekCapture, roster_capture, existing: Snapshot | None, supersedes) -> Snapshot`, following data-model.md "Mapping to Snapshot". T015 must pass
- [X] T021 [US1] In `src/ccsv_rumble/fetch/captured.py`, add `CapturedProvider(matchups_path, rosters_path, *, tz, season_start, clock=None)`, which implements `LeagueDataProvider`:
  - `fetch_stat_category_map` returns `{}`;
  - `fetch_week` returns `{"source": "matchups.csv", "week": N, "text": raw_text, "capture": WeekCapture}`;
  - `fetch_rosters` and `fetch_transactions` return `{}`.

  Also add `capture_league_source(...) -> LeagueSource`, whose `build` adapts `build_capture_snapshot` to the T012 signature and archives `raw_text` to `raw_matchups`. If `rosters.csv` is absent, raise `ProviderError` naming the file (contracts/cli.md). T014 must pass
- [X] T022 [US1] In `src/ccsv_rumble/cli.py`:
  - add `--source {capture,yahoo}` (default `capture`) and `--matchups` (default `data/matchups.csv`) to `run` and `dry-run` via `common()`, or per-parser if `replay` must not get them;
  - in `cmd_run`, build the `LeagueSource` once, for weeks ≥ 1 only. `capture` never calls `_provider_from_env`; `yahoo` keeps today's path;
  - log `league source: capture (<path>), weeks [..]` (FR-004).

  T016 must pass.
- [X] T023 [US1] Update `tools/chrome_capture.py` per contracts/matchups-capture.md "Writer obligations":
  - append `captured_at`, `week_start` and `week_end` to `MATCHUP_FIELDS`;
  - stamp `captured_at` as `datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="seconds")`;
  - add `--matchup-start`/`--matchup-end` as an explicit source of week dates for `matchups` (R9 fallback). These are separate from the projections' `--week-start/--week-end`, whose window is the week ahead. The capture refuses to write if neither these nor scraped dates are available;
  - add `_merge_matchups(existing_text, new_rows, week)`: drop the old rows for `week`, keep the others even in the old 19-column format (writing blanks for missing columns), and sort by `(week, matchup, team_id)` (FR-012);
  - write atomically: a temp file in the same directory, then `os.replace`;
  - with no `--week`, default to the most recent **ended** week by the R10 calendar, not the scoreboard's current week (R11).
- [X] T024 [P] [US1] Add `tests/unit/test_chrome_capture_merge.py`. `_merge_matchups` replaces only the target week, preserves another week's rows byte for byte, and sorts. The default-week helper returns 1 on 2026-10-26 and on 2026-11-01, and 2 on 2026-11-02. Import from `tools/chrome_capture.py` the same way any existing test does; if none does, by path
- [ ] T025 [US1] **Maintainer-in-browser discovery (R9).** On the league scoreboard (`…/nba/<league>?matchup_week=1&module=matchups`), find the element that shows the week's date range. If one exists, add `__matchup.weekDates()` to `tools/yahoo_matchup_capture.js`, returning `{start, end}` as ISO dates, and use it in `capture_matchups` when `--week-start`/`--week-end` are not given. If none exists, record that in research.md R9 and keep the flags as the documented path. Either way, update `specs/004-browser-session-provider/spec.md` gate G7 with what a completed week's matchup page shows

**Checkpoint**: US1 is complete. Week 1 publishes from a capture with no credentials. This is the MVP.

---

## Phase 4: User Story 2 - A bad capture fails loudly (Priority: P1)

**Goal**: Each defect class refuses to publish, exits `EXIT_ACQUIRE`, sends a notification, and
names the defect (SC-002).

**Independent Test**: `tests/integration/test_capture_defects.py` passes. Each case leaves the
output directory empty and the archive with no new entry.

### Tests for User Story 2 ⚠️ write first, confirm they fail

- [X] T026 [P] [US2] Extend `tests/unit/test_captured_load.py` with one case per row of contracts/matchups-capture.md "Reader guarantees". Each asserts `ProviderError` and checks that the message names the cause:
  - a missing row names the team (FR-005);
  - a duplicated team is caught (FR-005);
  - a blank `fga` names the team and `fga`, and `fga="12.5"` is non-integer (FR-006);
  - non-mutual opponents name both teams (FR-007);
  - an unknown `t.99` is caught (FR-011);
  - an altered `cat_wins` names both teams and both counts (FR-008);
  - `captured_at=2026-10-25T20:43:00-07:00` reports "captured before it ended" (FR-009);
  - `week_end=2026-10-26` names both ranges (R10);
  - differing `captured_at` within a week is caught;
  - rows missing the three new columns fail with a timing or missing-metadata message (old-format rows).

  Plus two **pass** cases. A near-tie where the exact FG% differs (`.4412` vs `.4408`) while the displayed values tie (`.441`/`.441`) passes when `cat_wins` reflects either a tie or a win (R2). A team with `fga=0` and `fg_pct_display="-"` passes.
- [X] T027 [P] [US2] Write `tests/integration/test_capture_defects.py`, parametrized over the FR-005, FR-006, FR-008, FR-009 and FR-010 cases (FR-010 is `--week 2` with only week 1 captured). Run `cli.main(["run", ...])` with a recording notifier patched in, as `tests/integration/test_failure_paths.py` does. Expect exit `EXIT_ACQUIRE`, no publish call, one failure notification, no new archive entry, and the defect named in the log
- [X] T028 [P] [US2] Write `tests/integration/test_capture_recheck.py` (R4, R5):
  - (a) week 1 is archived and the capture holds only week 2; a run that rechecks week 1 logs `not re-checked` and keeps `entry-001`;
  - (b) a **gap** week missing from the capture fails with `WeekNotCaptured`, naming the week;
  - (c) `rosters.csv` changes between two runs while the totals don't; this creates no new entry, for both a recheck and a same-week retry where the week is both rechecked and published.

### Implementation for User Story 2

- [X] T029 [US2] In `src/ccsv_rumble/fetch/captured.py` `load_week`, add the remaining validation steps in data-model.md "Validation order" (3, 5, 6, 7, 8, 9), each raising `ProviderError` with the message given in contracts/matchups-capture.md:
  - step 3: integer parsing, `made <= attempted`, non-negative;
  - step 5: coverage (exactly `TEAM_COUNT` teams, each once, in `TEAM_COUNT / 2` matchups) and mutual opponents;
  - step 6: team ids present in the roster capture;
  - step 7: the strict-wins checksum, which does NOT reuse `allplay.category_wins` (it scores ties as half). Count `config.CATEGORIES` with `to` inverted, and accept the ratio categories under either exact `made/attempted` or the displayed 3-decimal value (R2);
  - step 8: `captured_at.astimezone(tz).date() > week_end` (FR-009);
  - step 9: `(week_start, week_end) == calendar(week)` (R10).

  T026 must pass.
- [X] T030 [US2] Confirm that the `ProviderError` path in `src/ccsv_rumble/cli.py` `cmd_run` sends a failure notification through `_notify_failure`. Today it only logs and returns `EXIT_ACQUIRE`, while `ProjectionError` notifies. Add the `_notify_failure` call so capture defects notify, as User Story 2 requires. T027 and T028 must pass

**Checkpoint**: US1 and US2 are complete. Bad captures cannot publish.

---

## Phase 5: User Story 3 - The Yahoo API path keeps working (Priority: P3)

**Goal**: `--source yahoo` behaves exactly as before (FR-018). The default never touches it.

**Independent Test**: The existing integration suite passes when run through `--source yahoo`, and
the default run never calls `_provider_from_env`.

- [X] T031 [P] [US3] Write `tests/integration/test_source_selection.py`:
  - (a) `--source yahoo` with `YAHOO_*` unset fails with the existing "missing required environment variables" error. This proves the path is still wired;
  - (b) `--source yahoo` with `FakeProvider` patched in for `_provider_from_env` publishes week 1 via the Yahoo builder;
  - (c) the default source with `_provider_from_env` patched to raise never raises (FR-002);
  - (d) a week 0-only plan constructs neither source.
- [X] T032 [US3] Make whatever minimal change in `src/ccsv_rumble/cli.py` is needed for T031 to pass. Do not change the Yahoo behaviour itself

**Checkpoint**: All three stories are complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T033 [P] Update the weekly chore in `README.md`:
  - capture with `chrome_capture.py dailies`, on Monday or later, which defaults to the last ended week;
  - the run defaults to `--source capture`;
  - fix the example `--week-end 20261026` to `20261025`;
  - document `--source`/`--matchups`;
  - add a note that week dates come from the league, with the All-Star caveat.
- [X] T034 [P] In `specs/004-browser-session-provider/spec.md`, mark "Phase 3 — Provider" as delivered by `005-captured-league-provider`, with a link, in the same "superseded in place" style 004 already uses
- [X] T035 [P] Add a `--source` note to `.github/workflows/weekly.yml`'s comment block. The `YAHOO_*` env can stay, since it is unused on the default path; leave removing it to a later cleanup (research R11)
- [X] T036 Run `uv run pytest tests/` (the full suite, including `tests/unit/test_architecture.py`) and fix any failure
- [ ] T037 Run [quickstart.md](quickstart.md) steps 1–4 against a real Monday-or-later recapture of week 1, using a scratch `--archive`. Record the result in the PR. Do **not** commit the scratch archive

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: depends on Setup. T003→T004→T005→T006→T007 run in sequence because they share `pipeline.py`. T008→T009 can run in parallel with the week 0 chain. T010 and T011 can run in parallel with both chains. T012→T013 need T010 and T011, and follow T004–T005 because they share `pipeline.py`.
- **US1 (Phase 3)**: depends on Phase 2.
- **US2 (Phase 4)**: depends on T019 (the loader exists). It can start alongside T020–T025.
- **US3 (Phase 5)**: depends on T022.
- **Polish (Phase 6)**: depends on all stories. T037 also needs week 1 to have ended and to have been recaptured.

### Within User Story 1

- T014–T018 (tests) are written first and fail.
- Then T019 → T020 → T021 → T022. T023 and T024 are independent of these, in `tools/`.
- T025 needs a browser and the maintainer. It must not block the rest, because the `--matchup-start/--matchup-end` fallback in T023 covers it.

### Parallel Opportunities

- T001 ∥ T002.
- Phase 2: the {T003…T007} chain ∥ {T008, T009} ∥ T010 ∥ T011.
- US1 tests T014 ∥ T015 ∥ T016 ∥ T017 ∥ T018; and T023 + T024 ∥ T019–T022.
- US2 tests T026 ∥ T027 ∥ T028.
- Polish T033 ∥ T034 ∥ T035.

## Parallel Example: User Story 1

```text
# Tests first, together:
T014 tests/unit/test_captured_load.py
T015 tests/unit/test_capture_snapshot.py
T016 tests/integration/test_capture_no_credentials.py
T017 tests/integration/test_capture_idempotent_replay.py
T018 tests/integration/test_capture_parity.py

# Then, in parallel tracks:
Track A: T019 → T020 → T021 → T022   (src/ccsv_rumble/fetch/captured.py, cli.py)
Track B: T023 → T024                 (tools/chrome_capture.py)
```

## Implementation Strategy

### MVP first

1. Phases 1–2. The week 0 fix and the calendar fix are worth shipping alone: they correct the
   first week 1 page, whatever the data source.
2. Phase 3 (US1). Week 1 can now publish from a capture.
3. **Do not publish a real week 1 before Phase 4.** US1 alone would rank a defective capture
   without complaint, and US2 is what makes the capture path safe to run unattended. In practice,
   the MVP to deploy is US1 + US2.

### Timing against the real season

- Week 1 ends Sunday 2026-10-25. The next scheduled run is Tuesday 2026-10-27, 16:00 UTC.
- For that run to publish week 1, Phases 1–4 must be merged, and week 1 must be recaptured on
  Monday 2026-10-26 or later and committed before the run.
- If that run is missed, nothing is lost. The next run backfills week 1 as a gap week, provided
  week 1 is in the capture (R4).
